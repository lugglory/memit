"""
repository.py: Repository management (init, commit, log, status).
"""
import json
from pathlib import Path
from typing import List, Optional, Tuple
from .snapshot import Snapshot
from .ignore import IgnoreHandler
from .amend_check import check_amend_safe


class Repository:
    """Manages a memit repository."""

    def __init__(self, root: Path):
        """
        Initialize repository manager.

        Args:
            root: Root directory of the repository
        """
        self.root = Path(root).resolve()
        self.memit_dir = self.root / '.memit'
        self.config_file = self.memit_dir / 'config.json'
        self.snapshots_dir = self.memit_dir / 'snapshots'

    def is_initialized(self) -> bool:
        """Check if this is a valid memit repository."""
        return self.memit_dir.exists() and self.config_file.exists()

    def init(self) -> str:
        """
        Initialize a new memit repository.

        Returns:
            Success message
        """
        if self.is_initialized():
            return "Repository already initialized"

        # Create directory structure
        self.memit_dir.mkdir(exist_ok=True)
        self.snapshots_dir.mkdir(exist_ok=True)

        # Create config
        config = {
            'version': 1,
            'next_id': 1
        }

        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)

        return f"Initialized memit repository in {self.memit_dir}"

    def _load_config(self) -> dict:
        """Load repository configuration."""
        with open(self.config_file, 'r', encoding='utf-8') as f:
            return json.load(f)

    def _save_config(self, config: dict):
        """Save repository configuration."""
        with open(self.config_file, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2)

    def _get_next_id(self) -> int:
        """Get and increment the next snapshot ID."""
        config = self._load_config()
        snapshot_id = config['next_id']
        config['next_id'] = snapshot_id + 1
        self._save_config(config)
        return snapshot_id

    def _get_snapshot_ids(self) -> List[int]:
        """Get all snapshot IDs in chronological order."""
        if not self.snapshots_dir.exists():
            return []

        ids = []
        for snapshot_dir in self.snapshots_dir.iterdir():
            if snapshot_dir.is_dir():
                try:
                    ids.append(int(snapshot_dir.name))
                except ValueError:
                    continue

        return sorted(ids)

    def get_snapshots(self, limit: Optional[int] = None) -> List[Snapshot]:
        """
        Get snapshots in reverse chronological order.

        Args:
            limit: Maximum number of snapshots to return

        Returns:
            List of Snapshot objects
        """
        ids = self._get_snapshot_ids()

        if limit:
            ids = ids[-limit:]

        snapshots = []
        for snapshot_id in reversed(ids):
            try:
                snapshot = Snapshot.load(self.memit_dir, snapshot_id)
                snapshots.append(snapshot)
            except Exception:
                continue

        return snapshots

    def get_last_snapshot(self) -> Optional[Snapshot]:
        """Get the most recent snapshot."""
        ids = self._get_snapshot_ids()
        if not ids:
            return None

        return Snapshot.load(self.memit_dir, ids[-1])

    def get_second_last_snapshot(self) -> Optional[Snapshot]:
        """Get the second most recent snapshot."""
        ids = self._get_snapshot_ids()
        if len(ids) < 2:
            return None

        return Snapshot.load(self.memit_dir, ids[-2])

    def commit(
        self,
        message: str,
        force_new: bool = False,
        force_amend: bool = False
    ) -> Tuple[bool, str]:
        """
        Create a new commit or amend the last one.

        Args:
            message: Commit message
            force_new: Force creation of new snapshot (ignore amend logic)
            force_amend: Force amend of last snapshot (dangerous!)

        Returns:
            Tuple of (success, message)
        """
        if not self.is_initialized():
            return False, "Not a memit repository (run 'memit init')"

        # Collect tracked files
        ignore_handler = IgnoreHandler(self.root)
        tracked_files = ignore_handler.get_tracked_files()

        # Get current working directory state
        current_snapshot = Snapshot.from_working_directory(
            repo_root=self.root,
            snapshot_id=0,  # Temporary ID
            message=message,
            parent=None,  # Will be set later
            tracked_files=tracked_files
        )

        # Get existing snapshots
        last_snapshot = self.get_last_snapshot()
        second_last_snapshot = self.get_second_last_snapshot()

        # Case 1: No snapshots yet - create first snapshot
        if last_snapshot is None:
            snapshot_id = self._get_next_id()
            snapshot = Snapshot.from_working_directory(
                repo_root=self.root,
                snapshot_id=snapshot_id,
                message=message,
                parent=None,
                tracked_files=tracked_files
            )
            snapshot.save(self.memit_dir)
            return True, f"Created snapshot {snapshot_id}"

        # Case 2: Only one snapshot exists - always create new snapshot
        if second_last_snapshot is None:
            # Check if there are any changes
            if current_snapshot.files == last_snapshot.files:
                return False, "nothing to commit, working directory clean"

            snapshot_id = self._get_next_id()
            snapshot = Snapshot.from_working_directory(
                repo_root=self.root,
                snapshot_id=snapshot_id,
                message=message,
                parent=last_snapshot.id,
                tracked_files=tracked_files
            )
            snapshot.save(self.memit_dir)
            return True, f"Created snapshot {snapshot_id}"

        # Case 3: Two or more snapshots exist - smart amend logic
        # Check if there are any changes
        if current_snapshot.files == last_snapshot.files:
            return False, "nothing to commit, working directory clean"

        # Force flags override logic
        if force_new and force_amend:
            return False, "Cannot use both --force-new and --force-amend"

        if force_new:
            # Force create new snapshot
            snapshot_id = self._get_next_id()
            snapshot = Snapshot.from_working_directory(
                repo_root=self.root,
                snapshot_id=snapshot_id,
                message=message,
                parent=last_snapshot.id,
                tracked_files=tracked_files
            )
            snapshot.save(self.memit_dir)
            return True, f"Created snapshot {snapshot_id}"

        if force_amend:
            # Force amend (dangerous!)
            snapshot = Snapshot.from_working_directory(
                repo_root=self.root,
                snapshot_id=last_snapshot.id,
                message=message,
                parent=last_snapshot.parent,
                tracked_files=tracked_files,
                amended=True,
                amend_count=last_snapshot.amend_count + 1
            )
            snapshot.save(self.memit_dir)
            return True, f"Amended snapshot {last_snapshot.id} (forced)"

        # Smart amend logic: check triangle inequality
        is_safe, reason = check_amend_safe(
            A_files=second_last_snapshot.files,
            B_files=last_snapshot.files,
            C_files=current_snapshot.files
        )

        if is_safe:
            # Safe to amend - overwrite last snapshot
            snapshot = Snapshot.from_working_directory(
                repo_root=self.root,
                snapshot_id=last_snapshot.id,
                message=message,
                parent=last_snapshot.parent,
                tracked_files=tracked_files,
                amended=True,
                amend_count=last_snapshot.amend_count + 1
            )
            snapshot.save(self.memit_dir)
            return True, f"Amended snapshot {last_snapshot.id} ({reason})"
        else:
            # Not safe to amend - create new snapshot
            snapshot_id = self._get_next_id()
            snapshot = Snapshot.from_working_directory(
                repo_root=self.root,
                snapshot_id=snapshot_id,
                message=message,
                parent=last_snapshot.id,
                tracked_files=tracked_files
            )
            snapshot.save(self.memit_dir)
            return True, f"Created snapshot {snapshot_id} (amend unsafe: {reason})"

    def get_status(self) -> Tuple[Optional[Snapshot], dict]:
        """
        Get current repository status.

        Returns:
            Tuple of (last_snapshot, changes)
            - changes: dict with keys 'modified', 'added', 'deleted'
        """
        last_snapshot = self.get_last_snapshot()

        # Collect current files
        ignore_handler = IgnoreHandler(self.root)
        tracked_files = ignore_handler.get_tracked_files()

        current_files = {}
        for file_path in tracked_files:
            try:
                rel_path = file_path.relative_to(self.root)
                from .snapshot import read_file_content
                content = read_file_content(file_path)
                current_files[str(rel_path)] = content
            except Exception:
                continue

        # Compare with last snapshot
        changes = {
            'modified': [],
            'added': [],
            'deleted': []
        }

        if last_snapshot is None:
            # All current files are "added"
            changes['added'] = list(current_files.keys())
        else:
            # Find changes
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
