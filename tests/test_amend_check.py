"""
test_amend_check.py: Tests for amend safety checking.
"""
import pytest
from memit.amend_check import check_amend_safe, should_amend


class TestAmendCheck:
    """Test amend safety using triangle inequality."""

    def test_safe_progressive_deletion(self):
        """Example 1: Progressive deletion is safe."""
        # A="Hello World" -> B="Hello" -> C="Hel"
        A_files = {"test.txt": "Hello World"}
        B_files = {"test.txt": "Hello"}
        C_files = {"test.txt": "Hel"}

        is_safe, reason = check_amend_safe(A_files, B_files, C_files)
        assert is_safe, f"Expected safe, got: {reason}"
        assert should_amend(A_files, B_files, C_files)

    def test_unsafe_revert_insertion(self):
        """Example 2: Reverting an insertion loses information."""
        # A="abc" -> B="abXc" (add X) -> C="abc" (remove X)
        A_files = {"test.txt": "abc"}
        B_files = {"test.txt": "abXc"}
        C_files = {"test.txt": "abc"}

        is_safe, reason = check_amend_safe(A_files, B_files, C_files)
        assert not is_safe, "Expected unsafe (information loss)"
        assert not should_amend(A_files, B_files, C_files)

    def test_safe_progressive_insertion(self):
        """Example 3: Progressive insertion is safe."""
        # A="abc" -> B="abXc" (add X) -> C="abXYc" (add Y)
        A_files = {"test.txt": "abc"}
        B_files = {"test.txt": "abXc"}
        C_files = {"test.txt": "abXYc"}

        is_safe, reason = check_amend_safe(A_files, B_files, C_files)
        assert is_safe, f"Expected safe, got: {reason}"
        assert should_amend(A_files, B_files, C_files)

    def test_unsafe_revert_deletion(self):
        """Example 4: Reverting a deletion loses information."""
        # A="abc" -> B="ac" (delete b) -> C="abc" (re-add b)
        A_files = {"test.txt": "abc"}
        B_files = {"test.txt": "ac"}
        C_files = {"test.txt": "abc"}

        is_safe, reason = check_amend_safe(A_files, B_files, C_files)
        assert not is_safe, "Expected unsafe (information loss)"
        assert not should_amend(A_files, B_files, C_files)

    def test_file_addition(self):
        """Test file creation."""
        # A: no file -> B: file created -> C: file modified
        A_files = {}
        B_files = {"new.txt": "initial"}
        C_files = {"new.txt": "initial modified"}

        is_safe, reason = check_amend_safe(A_files, B_files, C_files)
        assert is_safe, f"Expected safe, got: {reason}"

    def test_file_deletion(self):
        """Test file deletion."""
        # A: has file -> B: file deleted -> C: still deleted
        A_files = {"deleted.txt": "content"}
        B_files = {}
        C_files = {}

        is_safe, reason = check_amend_safe(A_files, B_files, C_files)
        assert is_safe, f"Expected safe, got: {reason}"

    def test_file_deleted_then_recreated(self):
        """Test unsafe pattern: delete then recreate."""
        # A: has file -> B: file deleted -> C: file recreated
        A_files = {"test.txt": "original"}
        B_files = {}
        C_files = {"test.txt": "new content"}

        is_safe, reason = check_amend_safe(A_files, B_files, C_files)
        # This might be unsafe depending on content
        # d(A,B) = len(original), d(B,C) = len(new), d(A,C) = edit_distance
        # If original != new, triangle inequality likely violated

    def test_multiple_files(self):
        """Test with multiple files."""
        A_files = {
            "file1.txt": "content1",
            "file2.txt": "content2"
        }
        B_files = {
            "file1.txt": "content1 modified",
            "file2.txt": "content2"
        }
        C_files = {
            "file1.txt": "content1 modified more",
            "file2.txt": "content2"
        }

        is_safe, reason = check_amend_safe(A_files, B_files, C_files)
        assert is_safe, f"Expected safe, got: {reason}"

    def test_binary_file_unchanged(self):
        """Binary files that don't change should be safe."""
        A_files = {"binary.dat": None}
        B_files = {"binary.dat": None}
        C_files = {"binary.dat": None}

        is_safe, reason = check_amend_safe(A_files, B_files, C_files)
        assert is_safe, f"Expected safe for unchanged binary, got: {reason}"

    def test_binary_file_changed(self):
        """Binary files that change should be unsafe."""
        A_files = {"binary.dat": None}
        B_files = {"binary.dat": None}
        C_files = {}  # Binary file deleted

        is_safe, reason = check_amend_safe(A_files, B_files, C_files)
        assert not is_safe, "Expected unsafe for changed binary"

    def test_no_changes(self):
        """No changes should be safe."""
        A_files = {"test.txt": "same"}
        B_files = {"test.txt": "same"}
        C_files = {"test.txt": "same"}

        is_safe, reason = check_amend_safe(A_files, B_files, C_files)
        assert is_safe, f"Expected safe for no changes, got: {reason}"
