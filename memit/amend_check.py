"""
amend_check.py: Triangle inequality check for safe amend detection.
"""
from typing import Dict, Optional, Tuple
from .diff_engine import efficient_edit_distance


def check_amend_safe(
    A_files: Dict[str, Optional[str]],
    B_files: Dict[str, Optional[str]],
    C_files: Dict[str, Optional[str]]
) -> Tuple[bool, str]:
    """
    Check if amending B with C is safe (no information loss).

    Uses triangle inequality: d(A,B) + d(B,C) == d(A,C)
    This means B is on the shortest edit path from A to C.

    Args:
        A_files: Files in snapshot S[-2] (grandparent)
        B_files: Files in snapshot S[-1] (current last snapshot)
        C_files: Files in working directory

    Returns:
        Tuple of (is_safe, reason)
        - is_safe: True if amend is safe
        - reason: Human-readable explanation
    """
    # Collect all file paths across all three versions
    all_files = set(A_files.keys()) | set(B_files.keys()) | set(C_files.keys())

    for file_path in all_files:
        # Get content for each version (treat missing files as empty string)
        a_content = A_files.get(file_path, "")
        b_content = B_files.get(file_path, "")
        c_content = C_files.get(file_path, "")

        # Handle binary files (None content)
        if a_content is None or b_content is None or c_content is None:
            # Binary files: be conservative
            # If binary content changed, don't amend
            if a_content != b_content or b_content != c_content:
                return False, f"Binary file changed: {file_path}"
            # If binary file unchanged across all versions, it's safe
            continue

        # Skip if all three versions are identical
        if a_content == b_content == c_content:
            continue

        # Calculate edit distances
        d_AB = efficient_edit_distance(a_content, b_content)
        d_BC = efficient_edit_distance(b_content, c_content)
        d_AC = efficient_edit_distance(a_content, c_content)

        # If any distance calculation failed (too large), be conservative
        if d_AB is None or d_BC is None or d_AC is None:
            return False, f"File too large for diff: {file_path}"

        # Check triangle inequality: d(A,B) + d(B,C) == d(A,C)
        if d_AB + d_BC != d_AC:
            return False, (
                f"Information loss detected in {file_path}: "
                f"d(A,B)={d_AB} + d(B,C)={d_BC} != d(A,C)={d_AC}"
            )

    # All files passed the triangle inequality test
    return True, "All changes are on the shortest edit path"


def should_amend(
    A_files: Dict[str, Optional[str]],
    B_files: Dict[str, Optional[str]],
    C_files: Dict[str, Optional[str]]
) -> bool:
    """
    Simplified check for whether to amend.

    Args:
        A_files: Files in snapshot S[-2]
        B_files: Files in snapshot S[-1]
        C_files: Files in working directory

    Returns:
        True if amend should be performed
    """
    is_safe, _ = check_amend_safe(A_files, B_files, C_files)
    return is_safe
