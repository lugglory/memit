"""
test_diff_engine.py: Tests for LCS and edit distance calculations.
"""
import pytest
from memit.diff_engine import lcs_length, edit_distance, efficient_edit_distance


class TestLCS:
    """Test LCS length calculation."""

    def test_identical_strings(self):
        assert lcs_length("abc", "abc") == 3
        assert lcs_length("", "") == 0

    def test_completely_different(self):
        assert lcs_length("abc", "xyz") == 0

    def test_partial_match(self):
        assert lcs_length("ABCDGH", "AEDFHR") == 3  # ADH

    def test_substring(self):
        assert lcs_length("abc", "aXbXc") == 3
        assert lcs_length("Hello", "Hello World") == 5

    def test_empty_strings(self):
        assert lcs_length("", "abc") == 0
        assert lcs_length("abc", "") == 0


class TestEditDistance:
    """Test edit distance calculation."""

    def test_identical_strings(self):
        assert edit_distance("abc", "abc") == 0

    def test_pure_insertions(self):
        # "abc" -> "abXc" requires 1 insertion
        assert edit_distance("abc", "abXc") == 1

    def test_pure_deletions(self):
        # "abXc" -> "abc" requires 1 deletion
        assert edit_distance("abXc", "abc") == 1

    def test_complex_edits(self):
        # "Hello World" -> "Hello" requires 6 deletions
        assert edit_distance("Hello World", "Hello") == 6
        # "Hello" -> "Hel" requires 2 deletions
        assert edit_distance("Hello", "Hel") == 2

    def test_triangle_inequality_examples(self):
        """Test the examples from the plan."""
        # Example 1: A="Hello World", B="Hello", C="Hel"
        # d(A,B)=6, d(B,C)=2, d(A,C)=8
        # Should satisfy: 6 + 2 == 8
        A, B, C = "Hello World", "Hello", "Hel"
        d_AB = edit_distance(A, B)
        d_BC = edit_distance(B, C)
        d_AC = edit_distance(A, C)
        assert d_AB == 6
        assert d_BC == 2
        assert d_AC == 8
        assert d_AB + d_BC == d_AC  # Triangle equality - SAFE

        # Example 2: A="abc", B="abXc", C="abc"
        # d(A,B)=1, d(B,C)=1, d(A,C)=0
        # Should NOT satisfy: 1 + 1 != 0
        A, B, C = "abc", "abXc", "abc"
        d_AB = edit_distance(A, B)
        d_BC = edit_distance(B, C)
        d_AC = edit_distance(A, C)
        assert d_AB == 1
        assert d_BC == 1
        assert d_AC == 0
        assert d_AB + d_BC != d_AC  # Triangle inequality violated - UNSAFE

        # Example 3: A="abc", B="abXc", C="abXYc"
        # d(A,B)=1, d(B,C)=1, d(A,C)=2
        # Should satisfy: 1 + 1 == 2
        A, B, C = "abc", "abXc", "abXYc"
        d_AB = edit_distance(A, B)
        d_BC = edit_distance(B, C)
        d_AC = edit_distance(A, C)
        assert d_AB == 1
        assert d_BC == 1
        assert d_AC == 2
        assert d_AB + d_BC == d_AC  # Triangle equality - SAFE

        # Example 4: A="abc", B="ac", C="abc"
        # d(A,B)=1, d(B,C)=1, d(A,C)=0
        # Should NOT satisfy: 1 + 1 != 0
        A, B, C = "abc", "ac", "abc"
        d_AB = edit_distance(A, B)
        d_BC = edit_distance(B, C)
        d_AC = edit_distance(A, C)
        assert d_AB == 1
        assert d_BC == 1
        assert d_AC == 0
        assert d_AB + d_BC != d_AC  # Triangle inequality violated - UNSAFE


class TestEfficientEditDistance:
    """Test efficient edit distance with line-level optimization."""

    def test_same_result_as_naive(self):
        """Efficient version should match naive version for small inputs."""
        test_cases = [
            ("Hello World", "Hello"),
            ("abc\ndef\nghi", "abc\nXYZ\nghi"),
            ("line1\nline2\nline3", "line1\nline3"),
        ]

        for a, b in test_cases:
            assert efficient_edit_distance(a, b) == edit_distance(a, b)

    def test_no_changes(self):
        text = "No changes\nAt all\nHere"
        assert efficient_edit_distance(text, text) == 0

    def test_multiline_changes(self):
        a = "line1\nline2\nline3"
        b = "line1\nMODIFIED\nline3"
        # Should calculate distance only for changed lines
        result = efficient_edit_distance(a, b)
        assert result is not None
        assert result > 0
