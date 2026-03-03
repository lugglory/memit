"""
display.py: Terminal output formatting with colors.
"""
from typing import List, Dict, Optional
from .snapshot import Snapshot
from .diff_engine import get_character_diff


# ANSI color codes
class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'


def colorize(text: str, color: str) -> str:
    """Apply color to text."""
    return f"{color}{text}{Colors.RESET}"


def display_diff(old_content: str, new_content: str, file_path: str):
    """
    Display character-level diff with colors.

    Args:
        old_content: Original content
        new_content: Modified content
        file_path: Path to the file being diffed
    """
    print(f"\n{colorize(f'diff {file_path}', Colors.BOLD)}")

    diff = get_character_diff(old_content, new_content)

    for operation, text in diff:
        if operation == 'delete':
            print(colorize(text, Colors.RED), end='')
        elif operation == 'insert':
            print(colorize(text, Colors.GREEN), end='')
        else:  # equal
            print(text, end='')

    print()  # Final newline


def display_log(snapshots: List[Snapshot]):
    """
    Display commit log.

    Args:
        snapshots: List of snapshots in reverse chronological order
    """
    if not snapshots:
        print("No commits yet")
        return

    for i, snapshot in enumerate(snapshots):
        # Header
        amend_marker = ""
        if snapshot.amended and snapshot.amend_count > 0:
            amend_marker = colorize(f" (amended {snapshot.amend_count}x)", Colors.YELLOW)

        print(f"{colorize(f'snapshot {snapshot.id[:7]}', Colors.YELLOW)}{amend_marker}")

        # Parent info
        if snapshot.parent is not None:
            print(f"Parent:  {snapshot.parent[:7]}")

        # Timestamp
        print(f"Date:    {snapshot.timestamp}")

        # Message
        print(f"\n    {snapshot.message}\n")

        # Separator (except for last entry)
        if i < len(snapshots) - 1:
            print()


def display_status(last_snapshot: Optional[Snapshot], changes: Dict[str, List[str]]):
    """
    Display repository status.

    Args:
        last_snapshot: Most recent snapshot (or None)
        changes: Dict with 'modified', 'added', 'deleted' lists
    """
    if last_snapshot:
        print(f"On snapshot {last_snapshot.id[:7]}")
    else:
        print("No commits yet")

    # Check if there are any changes
    has_changes = any(changes.values())

    if not has_changes:
        print(colorize("\nnothing to commit, working directory clean", Colors.GREEN))
        return

    print("\nChanges to be committed:")

    if changes['added']:
        print(f"\n  {colorize('New files:', Colors.GREEN)}")
        for path in sorted(changes['added']):
            print(f"    {colorize('+ ', Colors.GREEN)}{path}")

    if changes['modified']:
        print(f"\n  {colorize('Modified:', Colors.YELLOW)}")
        for path in sorted(changes['modified']):
            print(f"    {colorize('M ', Colors.YELLOW)}{path}")

    if changes['deleted']:
        print(f"\n  {colorize('Deleted:', Colors.RED)}")
        for path in sorted(changes['deleted']):
            print(f"    {colorize('- ', Colors.RED)}{path}")

    print()


def display_commit_result(success: bool, message: str):
    """
    Display commit result.

    Args:
        success: Whether the commit succeeded
        message: Result message
    """
    if success:
        print(colorize(f"✓ {message}", Colors.GREEN))
    else:
        print(colorize(f"✗ {message}", Colors.RED))


def display_file_diff(
    file_path: str,
    old_content: Optional[str],
    new_content: Optional[str]
):
    """
    Display diff for a single file.

    Args:
        file_path: Relative path to the file
        old_content: Content in old snapshot (None if file didn't exist)
        new_content: Content in new snapshot (None if file was deleted)
    """
    if old_content is None and new_content is None:
        return  # No change

    if old_content is None:
        # File added
        print(f"\n{colorize(f'+++ {file_path} (new file)', Colors.GREEN)}")
        if new_content:
            print(colorize(new_content, Colors.GREEN))
    elif new_content is None:
        # File deleted
        print(f"\n{colorize(f'--- {file_path} (deleted)', Colors.RED)}")
        if old_content:
            print(colorize(old_content, Colors.RED))
    else:
        # File modified
        if old_content != new_content:
            display_diff(old_content, new_content, file_path)


def display_snapshot_diff(snapshot_a: Snapshot, snapshot_b: Snapshot):
    """
    Display diff between two snapshots.

    Args:
        snapshot_a: Older snapshot
        snapshot_b: Newer snapshot
    """
    all_files = set(snapshot_a.files.keys()) | set(snapshot_b.files.keys())

    for file_path in sorted(all_files):
        old_content = snapshot_a.files.get(file_path)
        new_content = snapshot_b.files.get(file_path)

        # Skip binary files
        if old_content is None or new_content is None:
            if old_content != new_content:
                if old_content is None:
                    print(f"\n{colorize(f'{file_path} (binary, added)', Colors.GREEN)}")
                elif new_content is None:
                    print(f"\n{colorize(f'{file_path} (binary, deleted)', Colors.RED)}")
                else:
                    print(f"\n{colorize(f'{file_path} (binary, modified)', Colors.YELLOW)}")
            continue

        display_file_diff(file_path, old_content, new_content)
