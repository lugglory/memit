#!/usr/bin/env python3
"""squash-history: 삼각부등식 기반 git 히스토리 정리 도구.

사용법:
  squash-history [--base HASH] [--dry-run] [-v]

원리:
  A = 기준 커밋, B = 중간 커밋, C = 다음 커밋
  d(A,B) + d(B,C) == d(A,C)  →  B는 중간 단계  →  A에 흡수 (fixup)
  otherwise                  →  방향 전환      →  보존 (pick)
"""

import argparse
import os
import subprocess
import sys
import tempfile


# ── Triangle Inequality Engine ────────────────────────────────────────────────

def lcs_length(a: str, b: str) -> int:
    if len(a) < len(b):
        a, b = b, a
    m, n = len(a), len(b)
    prev = [0] * (n + 1)
    curr = [0] * (n + 1)
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            if a[i - 1] == b[j - 1]:
                curr[j] = prev[j - 1] + 1
            else:
                curr[j] = max(prev[j], curr[j - 1])
        prev, curr = curr, prev
    return prev[n]


def edit_distance(a: str, b: str) -> int:
    return len(a) + len(b) - 2 * lcs_length(a, b)


# ── Git Helpers ───────────────────────────────────────────────────────────────

def git(*args) -> subprocess.CompletedProcess:
    return subprocess.run(['git'] + list(args), capture_output=True, text=True)


# ── 캐시: blob hash 기반 파일 내용·edit distance 메모이제이션 ─────────────────
# A 고정 시 d(A,C) → 다음 스텝 d(A,B)로 재사용
# A 이동 시 d(B,C) → 다음 스텝 d(A,B)로 재사용

_blob_cache: dict[str, str] = {}
_dist_cache: dict[tuple[str, str], int] = {}


def blob_hash_at(ref: str, path: str) -> str:
    r = git('ls-tree', ref, path)
    parts = r.stdout.split()
    return parts[2] if len(parts) >= 3 else ''


def file_content(ref: str, path: str) -> str:
    blob = blob_hash_at(ref, path)
    if blob:
        if blob not in _blob_cache:
            r = git('cat-file', 'blob', blob)
            _blob_cache[blob] = r.stdout if r.returncode == 0 else ''
        return _blob_cache[blob]
    r = git('show', f'{ref}:{path}')
    return r.stdout if r.returncode == 0 else ''


def cached_distance(ref_a: str, path: str, content_a: str,
                    ref_b: str, content_b: str) -> int:
    blob_a = blob_hash_at(ref_a, path) or f'raw:{hash(content_a)}'
    blob_b = blob_hash_at(ref_b, path) or f'raw:{hash(content_b)}'
    key = (min(blob_a, blob_b), max(blob_a, blob_b))
    if key not in _dist_cache:
        _dist_cache[key] = edit_distance(content_a, content_b)
    return _dist_cache[key]


def is_binary(content: str) -> bool:
    return '\x00' in content[:8192]


def files_between(a: str, b: str) -> list[str]:
    r = git('diff', '--name-only', a, b)
    return [f for f in r.stdout.strip().split('\n') if f]


def is_merge_commit(h: str) -> bool:
    r = git('show', '--no-patch', '--format=%P', h)
    return ' ' in r.stdout.strip()


def current_branch() -> str:
    return git('rev-parse', '--abbrev-ref', 'HEAD').stdout.strip()


def refs_pointing_to(h: str, exclude: str) -> list[str]:
    r = git('branch', '--points-at', h, '--format=%(refname:short)')
    branches = [b for b in r.stdout.strip().split('\n') if b and b != exclude]
    tags = [t for t in git('tag', '--points-at', h).stdout.strip().split('\n') if t]
    return branches + tags


def find_safe_base() -> str | None:
    """다른 브랜치/태그와의 가장 최근 merge-base 반환. 없으면 None."""
    branch = current_branch()
    r = git('for-each-ref', '--format=%(refname:short)', 'refs/heads', 'refs/tags')
    other_refs = [ref for ref in r.stdout.strip().split('\n')
                  if ref and ref != branch]
    if not other_refs:
        return None

    bases = []
    for ref in other_refs:
        r = git('merge-base', 'HEAD', ref)
        if r.returncode == 0:
            bases.append(r.stdout.strip())
    if not bases:
        return None

    best = bases[0]
    for b in bases[1:]:
        if git('merge-base', '--is-ancestor', best, b).returncode == 0:
            best = b
    return best


def get_commits(base: str = None) -> list[tuple[str, str]]:
    """오래된 순으로 (hash, subject) 목록."""
    args = ['log', '--reverse', '--format=%H\t%s']
    if base:
        args.append(f'{base}..HEAD')
    result = []
    for line in git(*args).stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split('\t', 1)
        result.append((parts[0], parts[1] if len(parts) > 1 else ''))
    return result


# ── Core ──────────────────────────────────────────────────────────────────────

def can_squash(a_hash: str, b_hash: str, c_hash: str, verbose: bool) -> bool:
    """B가 A→C 최단경로 위에 있는지 (모든 파일에 대해)."""
    files = files_between(a_hash, c_hash)
    if not files:
        return True

    for path in files:
        a = file_content(a_hash, path)
        b = file_content(b_hash, path)
        c = file_content(c_hash, path)

        if is_binary(a) or is_binary(b) or is_binary(c):
            if verbose:
                print(f"    binary  {path}")
            return False

        d_ab = cached_distance(a_hash, path, a, b_hash, b)
        d_bc = cached_distance(b_hash, path, b, c_hash, c)
        d_ac = cached_distance(a_hash, path, a, c_hash, c)

        if d_ab + d_bc != d_ac:
            if verbose:
                print(f"    unsafe  {path}  {d_ab}+{d_bc}≠{d_ac}")
            return False

    return True


def plan(commits: list[tuple[str, str]], verbose: bool) -> list[tuple[str, str]]:
    """보존할 커밋 목록 반환 (그리디)."""
    if len(commits) < 3:
        return commits

    branch = current_branch()
    kept = [commits[0]]

    for i in range(1, len(commits) - 1):
        A, B, C = kept[-1], commits[i], commits[i + 1]

        if is_merge_commit(B[0]):
            if verbose:
                print(f"  keep  {B[0][:7]}  {B[1]!r}  [merge]")
            kept.append(B)
            continue

        refs = refs_pointing_to(B[0], branch)
        if refs:
            if verbose:
                print(f"  keep  {B[0][:7]}  {B[1]!r}  [ref: {', '.join(refs)}]")
            kept.append(B)
            continue

        squashable = can_squash(A[0], B[0], C[0], verbose)
        if verbose:
            print(f"  {'drop' if squashable else 'keep'}  {B[0][:7]}  {B[1]!r}")
        if not squashable:
            kept.append(B)

    kept.append(commits[-1])
    return kept


def make_rebase_plan(commits: list[tuple[str, str]], kept: set[str]) -> str:
    lines = []
    for h, msg in commits:
        action = "pick " if h in kept else "fixup"
        lines.append(f"{action} {h} {msg}")
    return '\n'.join(lines) + '\n'


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='삼각부등식 기반 git 히스토리 정리',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  squash-history                  # 자동으로 안전 범위 탐지 후 정리
  squash-history --dry-run -v     # 결과 미리 보기
  squash-history --base abc1234   # 특정 커밋 이후만
        """
    )
    parser.add_argument('--base', help='이 커밋 이후부터만 처리 (기본: 다른 브랜치와의 분기점)')
    parser.add_argument('--dry-run', action='store_true', help='실행 없이 계획만 출력')
    parser.add_argument('-v', '--verbose', action='store_true', help='파일별 거리값 출력')
    args = parser.parse_args()

    if git('rev-parse', '--git-dir').returncode != 0:
        print("오류: git 레포지토리가 아닙니다.", file=sys.stderr)
        sys.exit(1)

    base = args.base
    if base is None:
        base = find_safe_base()
        if base:
            print(f"안전 기준점: {git('log', '--oneline', '-1', base).stdout.strip()}")
        else:
            print("다른 브랜치 없음 — 전체 히스토리 처리")

    commits = get_commits(base)
    if len(commits) < 3:
        print(f"커밋 {len(commits)}개 — 스쿼시할 게 없습니다.")
        return

    print(f"커밋 {len(commits)}개 분석 중...")
    kept_list = plan(commits, args.verbose)
    dropped = len(commits) - len(kept_list)

    print(f"\n결과: {len(commits)}개 → {len(kept_list)}개 (제거 {dropped}개)")

    if dropped == 0:
        print("스쿼시할 커밋이 없습니다.")
        return

    kept_hashes = {h for h, _ in kept_list}
    rebase_plan = make_rebase_plan(commits, kept_hashes)

    if args.dry_run:
        print()
        for line in rebase_plan.splitlines():
            print(f"  {line}")
        return

    editor = tempfile.NamedTemporaryFile(mode='w', suffix='.py', delete=False)
    editor.write(f"""#!/usr/bin/env python3
import sys
with open(sys.argv[1], 'w') as f:
    f.write({rebase_plan!r})
""")
    editor.close()
    os.chmod(editor.name, 0o755)

    try:
        env = os.environ.copy()
        env['GIT_SEQUENCE_EDITOR'] = f'python3 {editor.name}'
        cmd = ['git', 'rebase', '-i', '--root'] if not base else ['git', 'rebase', '-i', base]
        result = subprocess.run(cmd, env=env)
        if result.returncode == 0:
            print(f"\n완료: {len(commits)}개 → {len(kept_list)}개")
        else:
            print("\nrebase 실패. 취소하려면: git rebase --abort")
    finally:
        os.unlink(editor.name)


if __name__ == '__main__':
    main()
