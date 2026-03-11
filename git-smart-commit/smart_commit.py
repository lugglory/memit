#!/usr/bin/env python3
"""smart-commit: 삼각부등식 기반 자동 스쿼시 git 도구.

사용법:
  smart-commit [-m MSG] [-a] [--dry-run] [-v]   # 커밋 (자동 amend)
  smart-commit squash-history [--base HASH] [--dry-run] [-v]  # 기존 히스토리 정리

원리:
  A = 할아버지 상태, B = 직전 커밋 상태, C = 현재 상태
  d(A,B) + d(B,C) == d(A,C)  →  B는 중간 단계 → 스쿼시 가능
  otherwise                  →  방향 전환 → 별도 커밋 보존
"""

import argparse
import os
import subprocess
import sys
import tempfile
from datetime import datetime


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


def is_squashable(a: str, b: str, c: str) -> bool:
    """B가 A→C 최단경로 위에 있으면 True."""
    return edit_distance(a, b) + edit_distance(b, c) == edit_distance(a, c)


# ── Git Helpers ───────────────────────────────────────────────────────────────

def git(*args, check=False) -> subprocess.CompletedProcess:
    return subprocess.run(['git'] + list(args), capture_output=True, text=True, check=check)


def commit_count() -> int:
    r = git('rev-list', '--count', 'HEAD')
    return int(r.stdout.strip()) if r.returncode == 0 else 0


def staged_files() -> list[str]:
    r = git('diff', '--cached', '--name-only')
    return [f for f in r.stdout.strip().split('\n') if f]


def file_at_commit(ref: str, path: str) -> str:
    r = git('show', f'{ref}:{path}')
    return r.stdout if r.returncode == 0 else ''


def staged_content(path: str) -> str:
    r = git('show', f':{path}')
    return r.stdout if r.returncode == 0 else ''


def is_binary(content: str) -> bool:
    return '\x00' in content[:8192]


def files_between(a_hash: str, b_hash: str) -> list[str]:
    """두 커밋 사이에서 달라진 파일 목록."""
    r = git('diff', '--name-only', a_hash, b_hash)
    return [f for f in r.stdout.strip().split('\n') if f]


def is_merge_commit(h: str) -> bool:
    """부모가 2개 이상인 merge 커밋 여부."""
    r = git('show', '--no-patch', '--format=%P', h)
    return ' ' in r.stdout.strip()


def refs_pointing_to(h: str, current_branch: str) -> list[str]:
    """이 커밋을 직접 가리키는 다른 브랜치/태그 목록."""
    r = git('branch', '--points-at', h, '--format=%(refname:short)')
    branches = [b for b in r.stdout.strip().split('\n') if b and b != current_branch]
    r2 = git('tag', '--points-at', h)
    tags = [t for t in r2.stdout.strip().split('\n') if t]
    return branches + tags


def current_branch_name() -> str:
    r = git('rev-parse', '--abbrev-ref', 'HEAD')
    return r.stdout.strip()


def find_safe_base() -> str | None:
    """
    현재 브랜치에서 안전하게 squash할 수 있는 시작점(merge-base) 반환.
    다른 브랜치/태그가 없으면 None (전체 처리 가능).

    여러 브랜치가 있으면 가장 최근 merge-base 선택:
    → 그 이전 커밋들은 다른 브랜치와 공유 중이라 건드리면 안 됨.
    """
    current = current_branch_name()

    # 다른 모든 로컬 브랜치와 태그
    r = git('for-each-ref', '--format=%(refname:short)', 'refs/heads', 'refs/tags')
    other_refs = [ref for ref in r.stdout.strip().split('\n')
                  if ref and ref != current]

    if not other_refs:
        return None  # 혼자뿐 → --root부터 전체 처리

    # 각 ref와의 merge-base 수집
    bases = []
    for ref in other_refs:
        r = git('merge-base', 'HEAD', ref)
        if r.returncode == 0:
            bases.append(r.stdout.strip())

    if not bases:
        return None

    # 가장 최근 merge-base 선택 (현재 브랜치 HEAD에서 가장 가까운 것)
    # = 다른 base들을 조상으로 가지는 base
    best = bases[0]
    for b in bases[1:]:
        # b가 best보다 newer인지 (best가 b의 조상이면 b가 더 최근)
        r = git('merge-base', '--is-ancestor', best, b)
        if r.returncode == 0:
            best = b
    return best


def get_commits(base: str = None) -> list[tuple[str, str]]:
    """오래된 순으로 (hash, subject) 목록 반환."""
    args = ['log', '--reverse', '--format=%H\t%s']
    if base:
        args.append(f'{base}..HEAD')
    r = git(*args)
    result = []
    for line in r.stdout.strip().split('\n'):
        if not line:
            continue
        parts = line.split('\t', 1)
        result.append((parts[0], parts[1] if len(parts) > 1 else ''))
    return result


# ── Core: 커밋 시 판단 ─────────────────────────────────────────────────────────

def check_squash(verbose: bool = False) -> tuple[bool, str]:
    n = commit_count()
    if n < 2:
        return False, f"커밋 {n}개 (최소 2개 필요)"

    files = staged_files()
    if not files:
        return False, "staged 변경사항 없음"

    for path in files:
        a = file_at_commit('HEAD~1', path)
        b = file_at_commit('HEAD', path)
        c = staged_content(path)

        if is_binary(a) or is_binary(b) or is_binary(c):
            if verbose:
                print(f"  binary  {path}")
            return False, f"바이너리: {path}"

        squashable = is_squashable(a, b, c)

        if verbose:
            d_ab = edit_distance(a, b)
            d_bc = edit_distance(b, c)
            d_ac = edit_distance(a, c)
            eq = "=" if squashable else "≠"
            status = "safe  " if squashable else "unsafe"
            print(f"  {status}  {path}  {d_ab}+{d_bc}{eq}{d_ac}")

        if not squashable:
            return False, f"방향 전환: {path}"

    return True, "ok"


# ── Core: 히스토리 스쿼시 판단 ────────────────────────────────────────────────

def can_squash_commits(a_hash: str, b_hash: str, c_hash: str, verbose: bool = False) -> bool:
    """커밋 B를 DROP해도 되는지 (A와 C 사이에서 B가 중간 단계인지) 검사."""
    files = files_between(a_hash, c_hash)
    if not files:
        return True

    for path in files:
        a = file_at_commit(a_hash, path)
        b = file_at_commit(b_hash, path)
        c = file_at_commit(c_hash, path)

        if is_binary(a) or is_binary(b) or is_binary(c):
            if verbose:
                print(f"    binary  {path}")
            return False

        if not is_squashable(a, b, c):
            if verbose:
                d_ab = edit_distance(a, b)
                d_bc = edit_distance(b, c)
                d_ac = edit_distance(a, c)
                print(f"    unsafe  {path}  {d_ab}+{d_bc}≠{d_ac}")
            return False

    return True


def plan_squash_history(
    commits: list[tuple[str, str]], verbose: bool = False
) -> list[tuple[str, str]]:
    """
    보존할 커밋 목록 반환 (그리디).

    B가 last_kept → C 최단경로 위에 있으면 fixup, 아니면 KEEP.
    단, merge 커밋이나 다른 브랜치가 가리키는 커밋은 항상 KEEP (경계점).
    """
    if len(commits) < 3:
        return commits

    branch = current_branch_name()
    kept = [commits[0]]

    for i in range(1, len(commits) - 1):
        A = kept[-1]
        B = commits[i]
        C = commits[i + 1]

        # merge 커밋: 항상 보존 (부모가 2개라 삼각부등식 적용 불가)
        if is_merge_commit(B[0]):
            if verbose:
                print(f"  keep   {B[0][:7]}  {B[1]!r}  [merge commit]")
            kept.append(B)
            continue

        # 다른 브랜치/태그가 이 커밋을 직접 가리킴: 보존
        refs = refs_pointing_to(B[0], branch)
        if refs:
            if verbose:
                print(f"  keep   {B[0][:7]}  {B[1]!r}  [ref: {', '.join(refs)}]")
            kept.append(B)
            continue

        squashable = can_squash_commits(A[0], B[0], C[0], verbose=verbose)

        if verbose:
            action = "drop  " if squashable else "keep  "
            print(f"  {action} {B[0][:7]}  {B[1]!r}")

        if not squashable:
            kept.append(B)

    kept.append(commits[-1])
    return kept


def run_squash_history(base: str = None, dry_run: bool = False, verbose: bool = False):
    # base 미지정 시: 다른 브랜치와의 merge-base를 자동 탐색
    if base is None:
        base = find_safe_base()
        if base:
            r = git('log', '--oneline', '-1', base)
            print(f"안전 기준점: {r.stdout.strip()}")
        else:
            print("다른 브랜치 없음 — 전체 히스토리 처리")

    commits = get_commits(base)

    if len(commits) < 3:
        print(f"커밋 {len(commits)}개 — 스쿼시할 게 없습니다.")
        return

    print(f"커밋 {len(commits)}개 분석 중...")
    kept = plan_squash_history(commits, verbose=verbose)
    dropped = len(commits) - len(kept)

    print(f"\n결과: {len(commits)}개 → {len(kept)}개 (제거 {dropped}개)")

    if dropped == 0:
        print("스쿼시할 커밋이 없습니다.")
        return

    kept_hashes = {h for h, _ in kept}

    # drop 대신 fixup: 직전 pick에 흡수시켜서 diff 충돌 없이 적용
    # pick A / fixup B = B의 변경사항을 A에 합침 (A의 메시지 유지, B내용 반영)
    def make_plan():
        lines = []
        for h, msg in commits:
            action = "pick " if h in kept_hashes else "fixup"
            lines.append(f"{action} {h} {msg}")
        return '\n'.join(lines) + '\n'

    if dry_run:
        print()
        for line in make_plan().splitlines():
            print(f"  {line}")
        return

    rebase_plan = make_plan()

    # GIT_SEQUENCE_EDITOR로 주입할 임시 스크립트
    editor = tempfile.NamedTemporaryFile(
        mode='w', suffix='.py', delete=False, prefix='smart_rebase_editor_'
    )
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
            print(f"\n완료: {len(commits)}개 → {len(kept)}개")
        else:
            print("\nrebase 실패. 취소하려면: git rebase --abort")
    finally:
        os.unlink(editor.name)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description='삼각부등식 기반 자동 스쿼시 git 도구',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
예시:
  smart-commit -a -m "메모 저장"              # add + 자동 amend or 새 커밋
  smart-commit -a --dry-run -v               # 판단만 확인

  smart-commit squash-history --dry-run -v   # 전체 히스토리 분석
  smart-commit squash-history                # 실제 정리 실행
  smart-commit squash-history --base abc123  # 특정 커밋 이후만
        """
    )

    subparsers = parser.add_subparsers(dest='command')

    # squash-history 서브커맨드
    sh = subparsers.add_parser('squash-history', help='기존 커밋 히스토리 소급 정리')
    sh.add_argument('--base', help='이 커밋 이후부터만 처리 (없으면 전체)')
    sh.add_argument('--dry-run', action='store_true', help='실행 없이 pick/drop 계획만 출력')
    sh.add_argument('-v', '--verbose', action='store_true', help='파일별 거리값 출력')

    # 기본 커밋 옵션
    parser.add_argument('-m', '--message', help='커밋 메시지 (없으면 타임스탬프)')
    parser.add_argument('-a', '--all', action='store_true', help='git add -A 먼저 실행')
    parser.add_argument('--dry-run', action='store_true', help='판단만 출력, 실제 커밋 안 함')
    parser.add_argument('-v', '--verbose', action='store_true', help='파일별 거리값 출력')

    args = parser.parse_args()

    if git('rev-parse', '--git-dir').returncode != 0:
        print("오류: git 레포지토리가 아닙니다.", file=sys.stderr)
        sys.exit(1)

    # squash-history 서브커맨드
    if args.command == 'squash-history':
        run_squash_history(
            base=args.base,
            dry_run=args.dry_run,
            verbose=args.verbose,
        )
        return

    # 기본: smart commit
    if args.all:
        subprocess.run(['git', 'add', '-A'])

    message = args.message or datetime.now().strftime('%Y-%m-%d %H:%M:%S')

    if args.verbose:
        print(f"메시지: {message!r}")

    squashable, reason = check_squash(verbose=args.verbose)

    if args.dry_run:
        action = "amend (스쿼시)" if squashable else "new commit"
        print(f"[dry-run] → {action}  ({reason})")
        return

    if squashable:
        subprocess.run(['git', 'commit', '--amend', '-m', message])
        print("[squashed] HEAD에 합쳤습니다")
    else:
        subprocess.run(['git', 'commit', '-m', message])
        print(f"[new commit] ({reason})")


if __name__ == '__main__':
    main()
