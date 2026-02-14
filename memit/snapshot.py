"""
snapshot.py: Snapshot creation, loading, and file collection.
"""
import json
import shutil
from pathlib import Path
from typing import Dict, Optional
from datetime import datetime


def is_binary_file(file_path: Path) -> bool:
    """
    Check if a file is binary by looking for null bytes in the first 8KB.

    Args:
        file_path: Path to the file

    Returns:
        True if the file appears to be binary
    """
    try:
        with open(file_path, 'rb') as f:
            chunk = f.read(8192)
            return b'\x00' in chunk
    except Exception:
        return True  # Conservative: treat unreadable files as binary


def read_file_content(file_path: Path) -> Optional[str]:
    """
    Read file content as text, with fallback encoding.

    Args:
        file_path: Path to the file

    Returns:
        File content as string, or None if it's binary or unreadable
    """
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
    """Represents a single snapshot in the repository."""

    def __init__(
        self,
        snapshot_id: int,
        message: str,
        timestamp: str,
        parent: Optional[int],
        files: Dict[str, str],
        amended: bool = False,
        amend_count: int = 0
    ):
        """
        Initialize a snapshot.

        Args:
            snapshot_id: Unique snapshot ID
            message: Commit message
            timestamp: ISO format timestamp
            parent: Parent snapshot ID (None for first snapshot)
            files: Dict mapping relative path to file content
            amended: Whether this snapshot was created by amending
            amend_count: Number of times this snapshot has been amended
        """
        self.id = snapshot_id
        self.message = message
        self.timestamp = timestamp
        self.parent = parent
        self.files = files  # {rel_path_str: content}
        self.amended = amended
        self.amend_count = amend_count

    @classmethod
    def from_working_directory(
        cls,
        repo_root: Path,
        snapshot_id: int,
        message: str,
        parent: Optional[int],
        tracked_files: set[Path],
        amended: bool = False,
        amend_count: int = 0
    ) -> 'Snapshot':
        """
        Create a snapshot from the current working directory.

        Args:
            repo_root: Repository root directory
            snapshot_id: ID for this snapshot
            message: Commit message
            parent: Parent snapshot ID
            tracked_files: Set of absolute paths to track
            amended: Whether this is an amend operation
            amend_count: Number of times amended

        Returns:
            New Snapshot instance
        """
        files = {}

        for file_path in tracked_files:
            try:
                rel_path = file_path.relative_to(repo_root)
                content = read_file_content(file_path)

                # Store even binary files, but with None content
                # (for tracking their existence)
                if content is not None:
                    files[str(rel_path)] = content
                else:
                    files[str(rel_path)] = None  # Binary marker

            except Exception:
                # Skip files that can't be processed
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

    def save(self, memit_dir: Path):
        """
        Save snapshot to disk.

        Args:
            memit_dir: .memit directory path
        """
        snapshot_dir = memit_dir / 'snapshots' / str(self.id)
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        # Save metadata
        meta = {
            'id': self.id,
            'message': self.message,
            'timestamp': self.timestamp,
            'parent': self.parent,
            'files': list(self.files.keys()),
            'amended': self.amended,
            'amend_count': self.amend_count
        }

        with open(snapshot_dir / 'meta.json', 'w', encoding='utf-8') as f:
            json.dump(meta, f, indent=2)

        # Save files
        files_dir = snapshot_dir / 'files'
        files_dir.mkdir(exist_ok=True)

        for rel_path, content in self.files.items():
            if content is None:
                # Binary file marker
                continue

            file_path = files_dir / rel_path
            file_path.parent.mkdir(parents=True, exist_ok=True)

            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)

    @classmethod
    def load(cls, memit_dir: Path, snapshot_id: int) -> 'Snapshot':
        """
        Load snapshot from disk.

        Args:
            memit_dir: .memit directory path
            snapshot_id: ID of snapshot to load

        Returns:
            Loaded Snapshot instance
        """
        snapshot_dir = memit_dir / 'snapshots' / str(snapshot_id)

        # Load metadata
        with open(snapshot_dir / 'meta.json', 'r', encoding='utf-8') as f:
            meta = json.load(f)

        # Load files
        files = {}
        files_dir = snapshot_dir / 'files'

        if files_dir.exists():
            for rel_path in meta['files']:
                file_path = files_dir / rel_path

                if file_path.exists():
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            files[rel_path] = f.read()
                    except Exception:
                        files[rel_path] = None  # Binary or unreadable
                else:
                    files[rel_path] = None  # Binary file

        return cls(
            snapshot_id=meta['id'],
            message=meta['message'],
            timestamp=meta['timestamp'],
            parent=meta.get('parent'),
            files=files,
            amended=meta.get('amended', False),
            amend_count=meta.get('amend_count', 0)
        )

    def delete(self, memit_dir: Path):
        """
        Delete snapshot from disk.

        Args:
            memit_dir: .memit directory path
        """
        snapshot_dir = memit_dir / 'snapshots' / str(self.id)
        if snapshot_dir.exists():
            shutil.rmtree(snapshot_dir)
