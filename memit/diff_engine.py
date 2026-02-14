"""
diff_engine.py: LCS and edit distance calculation with performance optimization.
"""
from typing import Optional
import difflib


def lcs_length(a: str, b: str) -> int:
    """
    Calculate the length of the Longest Common Subsequence using dynamic programming.
    Uses O(min(n,m)) space optimization.

    Args:
        a: First string
        b: Second string

    Returns:
        Length of LCS
    """
    if len(a) < len(b):
        a, b = b, a  # Ensure a is the longer string

    m, n = len(a), len(b)

    # Use only two rows for space optimization
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
    """
    Calculate character-level indel (insert/delete) distance.

    Formula: d(a,b) = |a| + |b| - 2 * lcs_length(a,b)

    Args:
        a: First string
        b: Second string

    Returns:
        Edit distance (number of insertions + deletions)
    """
    return len(a) + len(b) - 2 * lcs_length(a, b)


def efficient_edit_distance(a: str, b: str, max_hunk_size: int = 10000) -> Optional[int]:
    """
    Calculate edit distance efficiently using line-level diff followed by character-level LCS.

    Strategy:
    1. Use line-level diff to find changed regions (hunks)
    2. Apply character-level LCS only within changed hunks
    3. Return None if any hunk exceeds max_hunk_size (conservative fallback)

    Args:
        a: First string
        b: Second string
        max_hunk_size: Maximum characters in a hunk (default 10,000)

    Returns:
        Edit distance, or None if computation is too expensive
    """
    # Split into lines
    a_lines = a.splitlines(keepends=True)
    b_lines = b.splitlines(keepends=True)

    # Get line-level diff
    matcher = difflib.SequenceMatcher(None, a_lines, b_lines)

    total_distance = 0

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            # No changes in this region
            continue

        # Extract the changed hunk
        a_hunk = ''.join(a_lines[i1:i2])
        b_hunk = ''.join(b_lines[j1:j2])

        # Check hunk size limit
        if len(a_hunk) + len(b_hunk) > max_hunk_size:
            return None  # Too expensive, be conservative

        # Calculate character-level edit distance for this hunk
        total_distance += edit_distance(a_hunk, b_hunk)

    return total_distance


def get_character_diff(a: str, b: str) -> list[tuple[str, str]]:
    """
    Generate character-level diff for display purposes.

    Returns list of (operation, text) tuples where operation is:
    - 'equal': unchanged text
    - 'delete': text removed from a
    - 'insert': text added to b

    Args:
        a: Original string
        b: Modified string

    Returns:
        List of (operation, text) tuples
    """
    matcher = difflib.SequenceMatcher(None, a, b)
    diff = []

    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == 'equal':
            diff.append(('equal', a[i1:i2]))
        elif tag == 'delete':
            diff.append(('delete', a[i1:i2]))
        elif tag == 'insert':
            diff.append(('insert', b[j1:j2]))
        elif tag == 'replace':
            diff.append(('delete', a[i1:i2]))
            diff.append(('insert', b[j1:j2]))

    return diff
