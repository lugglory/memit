"""
document.py: Single-file .memit document management.

All version history is stored in one JSON file instead of a directory structure.
"""
import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import List, Optional, Tuple

from .amend_check import check_amend_safe


@dataclass
class MemitSnapshot:
    """A single snapshot stored inside a .memit document."""
    id: int
    message: str
    timestamp: str
    content: str
    parent: Optional[int]
    amended: bool = False
    amend_count: int = 0


class MemitDocument:
    """Manages a single .memit file containing all version history."""

    FORMAT_VERSION = 1

    def __init__(self, path: Path):
        self.path = Path(path)
        self.format_version = self.FORMAT_VERSION
        self.next_id = 1
        self.snapshots: List[MemitSnapshot] = []

    @classmethod
    def load(cls, path: Path) -> 'MemitDocument':
        """Load an existing .memit file."""
        doc = cls(path)
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        doc.format_version = data.get('format_version', 1)
        doc.next_id = data.get('next_id', 1)
        doc.snapshots = [
            MemitSnapshot(
                id=s['id'],
                message=s['message'],
                timestamp=s['timestamp'],
                content=s['content'],
                parent=s.get('parent'),
                amended=s.get('amended', False),
                amend_count=s.get('amend_count', 0),
            )
            for s in data.get('snapshots', [])
        ]
        return doc

    @classmethod
    def create(cls, path: Path) -> 'MemitDocument':
        """Create a new empty .memit file."""
        doc = cls(path)
        doc.save()
        return doc

    def save(self):
        """Serialize and write the document to disk."""
        data = {
            'format_version': self.format_version,
            'next_id': self.next_id,
            'snapshots': [
                {
                    'id': s.id,
                    'message': s.message,
                    'timestamp': s.timestamp,
                    'content': s.content,
                    'parent': s.parent,
                    'amended': s.amended,
                    'amend_count': s.amend_count,
                }
                for s in self.snapshots
            ],
        }
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_content(self) -> str:
        """Return the content of the latest snapshot (empty string if none)."""
        if not self.snapshots:
            return ''
        return self.snapshots[-1].content

    def get_snapshots(self) -> List[MemitSnapshot]:
        """Return snapshots in chronological order (oldest first)."""
        return self.snapshots

    def commit(self, content: str, message: str) -> Tuple[bool, str]:
        """
        Save a new version with smart amend logic.

        - If no snapshots exist: create first snapshot.
        - If content unchanged: do nothing.
        - If only one snapshot: always create a new one.
        - Otherwise: check triangle inequality and amend or create accordingly.

        Returns:
            (success, human-readable message)
        """
        last = self.snapshots[-1] if self.snapshots else None
        second_last = self.snapshots[-2] if len(self.snapshots) >= 2 else None

        # Case 1: First snapshot ever
        if last is None:
            snap = MemitSnapshot(
                id=self.next_id,
                message=message,
                timestamp=datetime.now().isoformat(),
                content=content,
                parent=None,
            )
            self.next_id += 1
            self.snapshots.append(snap)
            self.save()
            return True, f"Created snapshot {snap.id}"

        # Nothing changed
        if content == last.content:
            return False, "nothing to commit, content unchanged"

        # Case 2: Only one snapshot — always create new
        if second_last is None:
            snap = MemitSnapshot(
                id=self.next_id,
                message=message,
                timestamp=datetime.now().isoformat(),
                content=content,
                parent=last.id,
            )
            self.next_id += 1
            self.snapshots.append(snap)
            self.save()
            return True, f"Created snapshot {snap.id}"

        # Case 3: Smart amend via triangle inequality
        is_safe, reason = check_amend_safe(
            A_files={"memo": second_last.content},
            B_files={"memo": last.content},
            C_files={"memo": content},
        )

        if is_safe:
            last.content = content
            last.message = message
            last.timestamp = datetime.now().isoformat()
            last.amended = True
            last.amend_count += 1
            self.save()
            return True, f"Amended snapshot {last.id} ({reason})"
        else:
            snap = MemitSnapshot(
                id=self.next_id,
                message=message,
                timestamp=datetime.now().isoformat(),
                content=content,
                parent=last.id,
            )
            self.next_id += 1
            self.snapshots.append(snap)
            self.save()
            return True, f"Created snapshot {snap.id} (amend unsafe: {reason})"

    def export_txt(self, path: Path):
        """Write the current content to a plain-text file."""
        Path(path).write_text(self.get_content(), encoding='utf-8')
