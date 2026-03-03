"""
snapshot.py: Snapshot creation and git-based loading.
"""
import re
import subprocess
from pathlib import Path
from typing import Dict, Optional, Set
from datetime import datetime


def is_binary_file(file_path: Path) -> bool:
    """Check if a file is binary by looking for null bytes in the first 8KB."""
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(8192)
            return b'\x00' in chunk
    except Exception:
        return True


def read_file_content(file_path: Path) -> Optional[str]:
    """Read file content as text, with fallback encoding."""
    if is_binary_file(file_path):
        return None

    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except UnicodeDecodeError:
        try:
            with open(file_path, 'r', encoding='latin-1') as f:
                return f.read()
        except Exception:
            return None
    except Exception:
        return None


class Snapshot:
    """Represents a single snapshot (git commit) in the repository."""

    def __init__(
        self,
        snapshot_id: str,
        message: str,
        timestamp: str,
        parent: Optional[str],
        files: Dict[str, Optional[str]],
        amended: bool = False,
        amend_count: int = 0
    ):
        self.id = snapshot_id
        self.message = message
        self.timestamp = timestamp
        self.parent = parent
        self.files = files
        self.amended = amended
        self.amend_count = amend_count

    @classmethod
    def from_working_directory(
        cls,
        repo_root: Path,
        snapshot_id: str,
        message: str,
        parent: Optional[str],
        tracked_files: Set[Path],
        amended: bool = False,
        amend_count: int = 0
    ) -> 'Snapshot':
        """Create a snapshot from the current working directory."""
        files: Dict[str, Optional[str]] = {}

        for file_path in tracked_files:
            try:
                rel_path = file_path.relative_to(repo_root)
                # Normalize to forward slashes for cross-platform consistency
                rel_key = str(rel_path).replace('\\', '/')
                content = read_file_content(file_path)
                files[rel_key] = content
            except Exception:
                continue

        return cls(
            snapshot_id=snapshot_id,
            message=message,
            timestamp=datetime.now().isoformat(),
            parent=parent,
            files=files,
            amended=amended,
            amend_count=amend_count
        )

    @classmethod
    def from_git_ref(cls, repo_root: Path, ref: str) -> Optional['Snapshot']:
        """Load a snapshot from a git commit reference (hash, HEAD, HEAD~1, etc.)."""

        def _run_text(args):
            return subprocess.run(
                ['git'] + args,
                cwd=str(repo_root),
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace'
            )

        # Get commit metadata: hash, parent hashes, subject, body, author date
        meta = _run_text(['log', '-1', '--format=%H%x00%P%x00%s%x00%b%x00%ai', ref])
        if meta.returncode != 0 or not meta.stdout.strip():
            return None

        # Split on null bytes (used as field separator in format string)
        raw = meta.stdout.rstrip('\n')
        parts = raw.split('\x00')
        while len(parts) < 5:
            parts.append('')

        commit_hash = parts[0].strip()
        parent_hashes = parts[1].strip().split()
        parent_hash = parent_hashes[0] if parent_hashes else None
        subject = parts[2].strip()
        body = parts[3]
        timestamp = parts[4].strip()

        if not commit_hash:
            return None

        # Parse memit metadata from commit body
        amended = bool(re.search(r'memit-amended:\s*true', body))
        amend_match = re.search(r'memit-amend-count:\s*(\d+)', body)
        amend_count = int(amend_match.group(1)) if amend_match else 0

        # Get file list for this ref
        ls = _run_text(['ls-tree', '-r', '--name-only', ref])
        file_paths = [p for p in ls.stdout.strip().split('\n') if p] if ls.stdout.strip() else []

        # Get file contents (run without text mode to detect binary files)
        files: Dict[str, Optional[str]] = {}
        for path in file_paths:
            show_result = subprocess.run(
                ['git', 'show', f'{ref}:{path}'],
                cwd=str(repo_root),
                capture_output=True
            )
            if show_result.returncode != 0:
                files[path] = None
                continue

            content_bytes = show_result.stdout
            # Detect binary by checking for null bytes in first 8KB
            if b'\x00' in content_bytes[:8192]:
                files[path] = None
            else:
                try:
                    files[path] = content_bytes.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        files[path] = content_bytes.decode('latin-1')
                    except Exception:
                        files[path] = None

        return cls(
            snapshot_id=commit_hash,
            message=subject,
            timestamp=timestamp,
            parent=parent_hash,
            files=files,
            amended=amended,
            amend_count=amend_count
        )
