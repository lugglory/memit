"""
repository.py: Repository management using git as backend.
"""
import subprocess
from pathlib import Path
from typing import List, Optional, Tuple
from .snapshot import Snapshot, read_file_content
from .ignore import IgnoreHandler
from .amend_check import check_amend_safe


class Repository:
    """Manages a memit repository backed by git."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        self.git_dir = self.root / '.git'

    def is_initialized(self) -> bool:
        """Check if this is a valid memit repository (git repo exists)."""
        return self.git_dir.exists()

    def init(self) -> str:
        """Initialize a new git-backed memit repository."""
        if self.is_initialized():
            return "Repository already initialized"

        result = self._run_git(['init'])
        if result.returncode != 0:
            return f"Failed to initialize: {result.stderr}"

        # Configure a local git identity so commits work without user config
        self._run_git(['config', 'user.name', 'memit'])
        self._run_git(['config', 'user.email', 'memit@local'])

        # Create .gitignore to exclude old .memit snapshot directory
        gitignore = self.root / '.gitignore'
        if not gitignore.exists():
            gitignore.write_text('.memit/\n', encoding='utf-8')

        return f"Initialized memit repository in {self.git_dir}"

    def _run_git(self, args: list) -> subprocess.CompletedProcess:
        """Run a git command in the repository root."""
        return subprocess.run(
            ['git'] + args,
            cwd=str(self.root),
            capture_output=True,
            text=True,
            encoding='utf-8'
        )

    def _get_commit_hashes(self, limit: Optional[int] = None) -> List[str]:
        """Get commit hashes in reverse chronological order (newest first)."""
        args = ['log', '--format=%H']
        if limit:
            args += ['-n', str(limit)]
        result = self._run_git(args)
        if result.returncode != 0 or not result.stdout.strip():
            return []
        return [h.strip() for h in result.stdout.strip().split('\n') if h.strip()]

    def get_snapshots(self, limit: Optional[int] = None) -> List[Snapshot]:
        """Get snapshots in reverse chronological order (newest first)."""
        hashes = self._get_commit_hashes(limit=limit)
        snapshots = []
        for h in hashes:
            snap = Snapshot.from_git_ref(self.root, h)
            if snap:
                snapshots.append(snap)
        return snapshots

    def get_last_snapshot(self) -> Optional[Snapshot]:
        """Get the most recent snapshot (HEAD)."""
        return Snapshot.from_git_ref(self.root, 'HEAD')

    def get_second_last_snapshot(self) -> Optional[Snapshot]:
        """Get the second most recent snapshot (HEAD~1)."""
        return Snapshot.from_git_ref(self.root, 'HEAD~1')

    def commit(
        self,
        message: str,
        force_new: bool = False,
        force_amend: bool = False
    ) -> Tuple[bool, str]:
        """Create a new commit or amend the last one using smart amend logic."""
        if not self.is_initialized():
            return False, "Not a memit repository (run 'memit init')"

        # Collect tracked files from working directory
        ignore_handler = IgnoreHandler(self.root)
        tracked_files = ignore_handler.get_tracked_files()

        # Build working directory snapshot for comparison
        current_snapshot = Snapshot.from_working_directory(
            repo_root=self.root,
            snapshot_id='',
            message=message,
            parent=None,
            tracked_files=tracked_files
        )

        last_snapshot = self.get_last_snapshot()
        second_last_snapshot = self.get_second_last_snapshot()

        # Case 1: No commits yet — create first commit
        if last_snapshot is None:
            return self._do_commit(message)

        # Case 2: No changes from last commit
        if current_snapshot.files == last_snapshot.files:
            return False, "nothing to commit, working directory clean"

        # Force flags override
        if force_new and force_amend:
            return False, "Cannot use both --force-new and --force-amend"

        if force_new:
            return self._do_commit(message)

        if force_amend:
            return self._do_amend(message, last_snapshot.amend_count + 1)

        # Case 3: Only one commit exists — always create new
        if second_last_snapshot is None:
            return self._do_commit(message)

        # Smart amend logic: check triangle inequality
        is_safe, reason = check_amend_safe(
            A_files=second_last_snapshot.files,
            B_files=last_snapshot.files,
            C_files=current_snapshot.files
        )

        # Amend only if safe AND last commit hasn't been pushed
        if is_safe and not self._is_last_commit_pushed():
            return self._do_amend(message, last_snapshot.amend_count + 1)
        else:
            if is_safe and self._is_last_commit_pushed():
                reason = "commit already pushed to remote"
            return self._do_commit(message)

    def _do_commit(self, message: str) -> Tuple[bool, str]:
        """Stage all changes and create a new git commit."""
        stage = self._run_git(['add', '.'])
        if stage.returncode != 0:
            return False, f"Failed to stage files: {stage.stderr.strip()}"

        result = self._run_git(['commit', '-m', message])
        if result.returncode != 0:
            output = result.stdout + result.stderr
            if 'nothing to commit' in output:
                return False, "nothing to commit, working directory clean"
            return False, f"Commit failed: {result.stderr.strip()}"

        head = self._run_git(['rev-parse', '--short', 'HEAD'])
        short_hash = head.stdout.strip() if head.returncode == 0 else '?'
        return True, f"Created snapshot {short_hash}"

    def _do_amend(self, message: str, amend_count: int) -> Tuple[bool, str]:
        """Stage all changes and amend the last git commit."""
        stage = self._run_git(['add', '.'])
        if stage.returncode != 0:
            return False, f"Failed to stage files: {stage.stderr.strip()}"

        # Embed memit metadata in commit body
        full_message = (
            f"{message}\n\n"
            f"memit-amended: true\n"
            f"memit-amend-count: {amend_count}"
        )

        result = self._run_git(['commit', '--amend', '-m', full_message])
        if result.returncode != 0:
            return False, f"Amend failed: {result.stderr.strip()}"

        head = self._run_git(['rev-parse', '--short', 'HEAD'])
        short_hash = head.stdout.strip() if head.returncode == 0 else '?'
        return True, f"Amended snapshot {short_hash}"

    def _is_last_commit_pushed(self) -> bool:
        """
        Check if HEAD has already been pushed to upstream.

        Returns False (safe to amend) when:
        - No upstream is configured
        - There are unpushed commits ahead of upstream

        Returns True (do NOT amend) when:
        - An upstream exists AND HEAD is already there
        """
        result = self._run_git(['log', '@{upstream}..HEAD', '--oneline'])
        if result.returncode != 0:
            # No upstream configured → treat HEAD as not pushed (safe to amend)
            return False
        return result.stdout.strip() == ''

    def push(self) -> Tuple[bool, str]:
        """Push current branch to origin."""
        if not self.get_remote_url():
            return False, "no remote"

        # Use -u to set upstream tracking on first push
        result = self._run_git(['push', '-u', 'origin', 'HEAD'])
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, result.stdout.strip() or "Push successful"

    def pull(self) -> Tuple[bool, str]:
        """Pull from origin using fast-forward only."""
        if not self.get_remote_url():
            return True, "skipped (no remote)"

        result = self._run_git(['pull', '--ff-only'])
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, result.stdout.strip() or "Already up to date"

    def get_remote_url(self) -> Optional[str]:
        """Get the URL of the origin remote, or None if not set."""
        result = self._run_git(['remote', 'get-url', 'origin'])
        if result.returncode != 0:
            return None
        url = result.stdout.strip()
        return url or None

    def set_remote_url(self, url: str) -> bool:
        """Add or update the origin remote URL."""
        if self.get_remote_url():
            result = self._run_git(['remote', 'set-url', 'origin', url])
        else:
            result = self._run_git(['remote', 'add', 'origin', url])
        return result.returncode == 0

    def update_commit_message(self, commit_hash: str, new_message: str) -> Tuple[bool, str]:
        """
        Update the message of the most recent commit (HEAD only, unpushed only).

        Args:
            commit_hash: The full hash of the commit to update (must be HEAD)
            new_message: New commit message

        Returns:
            Tuple of (success, message)
        """
        head = self._run_git(['rev-parse', 'HEAD'])
        if head.returncode != 0:
            return False, "No commits"

        head_full = head.stdout.strip()

        # Resolve the provided hash to full form for comparison
        ref_resolve = self._run_git(['rev-parse', commit_hash])
        if ref_resolve.returncode != 0:
            return False, f"Cannot resolve commit {commit_hash[:7]}"

        commit_full = ref_resolve.stdout.strip()
        if head_full != commit_full:
            return False, "커밋 메시지는 가장 최근 스냅샷만 수정할 수 있습니다"

        if self._is_last_commit_pushed():
            return False, "이미 push된 커밋의 메시지는 수정할 수 없습니다"

        result = self._run_git(['commit', '--amend', '-m', new_message])
        if result.returncode != 0:
            return False, result.stderr.strip()
        return True, "Message updated"

    def get_status(self) -> Tuple[Optional[Snapshot], dict]:
        """
        Get current repository status.

        Returns:
            Tuple of (last_snapshot, changes)
            where changes has keys 'modified', 'added', 'deleted'
        """
        last_snapshot = self.get_last_snapshot()

        ignore_handler = IgnoreHandler(self.root)
        tracked_files = ignore_handler.get_tracked_files()

        current_files: dict = {}
        for file_path in tracked_files:
            try:
                rel_path = file_path.relative_to(self.root)
                rel_key = str(rel_path).replace('\\', '/')
                content = read_file_content(file_path)
                current_files[rel_key] = content
            except Exception:
                continue

        changes = {'modified': [], 'added': [], 'deleted': []}

        if last_snapshot is None:
            changes['added'] = list(current_files.keys())
        else:
            last_files = last_snapshot.files

            for path in current_files:
                if path not in last_files:
                    changes['added'].append(path)
                elif current_files[path] != last_files[path]:
                    changes['modified'].append(path)

            for path in last_files:
                if path not in current_files:
                    changes['deleted'].append(path)

        return last_snapshot, changes

    def get_unpushed_count(self) -> Optional[int]:
        """
        Get number of unpushed commits.

        Returns None if no upstream is configured.
        """
        result = self._run_git(['rev-list', '@{upstream}..HEAD', '--count'])
        if result.returncode != 0:
            return None
        try:
            return int(result.stdout.strip())
        except ValueError:
            return None

    def is_gh_available(self) -> bool:
        """gh CLI가 설치되어 있고 인증된 상태인지 확인."""
        try:
            result = subprocess.run(['gh', 'auth', 'status'], capture_output=True)
            return result.returncode == 0
        except FileNotFoundError:
            return False

    def get_gh_username(self) -> Optional[str]:
        """인증된 GitHub 계정명 반환."""
        try:
            result = subprocess.run(
                ['gh', 'api', 'user', '--jq', '.login'],
                capture_output=True, text=True, encoding='utf-8'
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except FileNotFoundError:
            return None

    def create_github_repo(self, name: str, private: bool = True) -> Tuple[bool, str]:
        """
        GitHub 저장소를 생성하고 현재 커밋을 push.
        성공 시 (True, remote_url), 실패 시 (False, error_message) 반환.
        """
        visibility = '--private' if private else '--public'
        try:
            result = subprocess.run(
                ['gh', 'repo', 'create', name, visibility,
                 '--source', str(self.root),
                 '--remote', 'origin',
                 '--push'],
                capture_output=True, text=True, encoding='utf-8'
            )
        except FileNotFoundError:
            return False, "GitHub CLI(gh)가 설치되어 있지 않습니다."

        if result.returncode != 0:
            return False, result.stderr.strip()

        url = self.get_remote_url()
        return True, url or f"github.com/.../{name}"
