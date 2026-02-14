"""
test_repository.py: Tests for repository operations.
"""
import pytest
import tempfile
import shutil
from pathlib import Path
from memit.repository import Repository


class TestRepository:
    """Test repository operations."""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary repository for testing."""
        temp_dir = tempfile.mkdtemp()
        repo = Repository(Path(temp_dir))
        yield repo, Path(temp_dir)
        # Cleanup
        shutil.rmtree(temp_dir)

    def test_init(self, temp_repo):
        """Test repository initialization."""
        repo, repo_dir = temp_repo

        assert not repo.is_initialized()

        message = repo.init()
        assert "Initialized" in message
        assert repo.is_initialized()

        # Check directory structure
        assert (repo_dir / '.memit').exists()
        assert (repo_dir / '.memit' / 'config.json').exists()
        assert (repo_dir / '.memit' / 'snapshots').exists()

    def test_init_twice(self, temp_repo):
        """Test that initializing twice is safe."""
        repo, repo_dir = temp_repo

        repo.init()
        message = repo.init()
        assert "already initialized" in message

    def test_first_commit(self, temp_repo):
        """Test creating the first commit."""
        repo, repo_dir = temp_repo
        repo.init()

        # Create a file
        test_file = repo_dir / "test.txt"
        test_file.write_text("Hello World")

        # First commit
        success, message = repo.commit("Initial commit")
        assert success
        assert "snapshot 1" in message.lower()

        # Verify snapshot exists
        snapshots = repo.get_snapshots()
        assert len(snapshots) == 1
        assert snapshots[0].id == 1
        assert snapshots[0].message == "Initial commit"
        assert "test.txt" in snapshots[0].files

    def test_second_commit_creates_new_snapshot(self, temp_repo):
        """Test that second commit always creates new snapshot."""
        repo, repo_dir = temp_repo
        repo.init()

        # First commit
        test_file = repo_dir / "test.txt"
        test_file.write_text("Hello World")
        repo.commit("First commit")

        # Second commit
        test_file.write_text("Hello")
        success, message = repo.commit("Second commit")
        assert success
        assert "snapshot 2" in message.lower()

        # Verify two snapshots exist
        snapshots = repo.get_snapshots()
        assert len(snapshots) == 2

    def test_amend_safe_commit(self, temp_repo):
        """Test that safe progressive changes trigger amend."""
        repo, repo_dir = temp_repo
        repo.init()

        test_file = repo_dir / "test.txt"

        # Commit 1
        test_file.write_text("Hello World")
        repo.commit("First")

        # Commit 2
        test_file.write_text("Hello")
        repo.commit("Second")

        # Commit 3 (should amend commit 2)
        test_file.write_text("Hel")
        success, message = repo.commit("Third")

        assert success
        # Should have amended snapshot 2
        assert "amended snapshot 2" in message.lower() or "amend" in message.lower()

        # Should still have only 2 snapshots
        snapshots = repo.get_snapshots()
        assert len(snapshots) == 2

    def test_amend_unsafe_commit(self, temp_repo):
        """Test that unsafe changes create new snapshot."""
        repo, repo_dir = temp_repo
        repo.init()

        test_file = repo_dir / "test.txt"

        # Commit 1
        test_file.write_text("abc")
        repo.commit("First")

        # Commit 2
        test_file.write_text("abXc")
        repo.commit("Second")

        # Commit 3 (should NOT amend - reverting the X)
        test_file.write_text("abc")
        success, message = repo.commit("Third")

        assert success
        # Should have created new snapshot
        assert "snapshot 3" in message.lower()

        # Should have 3 snapshots
        snapshots = repo.get_snapshots()
        assert len(snapshots) == 3

    def test_no_changes_commit(self, temp_repo):
        """Test committing with no changes."""
        repo, repo_dir = temp_repo
        repo.init()

        test_file = repo_dir / "test.txt"
        test_file.write_text("Hello")
        repo.commit("First")

        # Try to commit again without changes
        success, message = repo.commit("Second")
        assert not success
        assert "nothing to commit" in message.lower()

    def test_force_new_flag(self, temp_repo):
        """Test --force-new flag."""
        repo, repo_dir = temp_repo
        repo.init()

        test_file = repo_dir / "test.txt"

        # Three commits with progressive deletion (normally would amend)
        test_file.write_text("Hello World")
        repo.commit("First")

        test_file.write_text("Hello")
        repo.commit("Second")

        test_file.write_text("Hel")
        success, message = repo.commit("Third", force_new=True)

        assert success
        assert "snapshot 3" in message.lower()

        # Should have 3 snapshots (force_new prevented amend)
        snapshots = repo.get_snapshots()
        assert len(snapshots) == 3

    def test_force_amend_flag(self, temp_repo):
        """Test --force-amend flag."""
        repo, repo_dir = temp_repo
        repo.init()

        test_file = repo_dir / "test.txt"

        # Commits that would normally create new snapshot
        test_file.write_text("abc")
        repo.commit("First")

        test_file.write_text("abXc")
        repo.commit("Second")

        test_file.write_text("abc")  # Revert X
        success, message = repo.commit("Third", force_amend=True)

        assert success
        assert "amended" in message.lower()
        assert "forced" in message.lower()

        # Should have 2 snapshots (force_amend overrode safety check)
        snapshots = repo.get_snapshots()
        assert len(snapshots) == 2

    def test_status_no_commits(self, temp_repo):
        """Test status with no commits."""
        repo, repo_dir = temp_repo
        repo.init()

        test_file = repo_dir / "test.txt"
        test_file.write_text("Hello")

        last_snapshot, changes = repo.get_status()
        assert last_snapshot is None
        assert "test.txt" in changes['added']

    def test_status_with_changes(self, temp_repo):
        """Test status with various changes."""
        repo, repo_dir = temp_repo
        repo.init()

        # Create initial files
        file1 = repo_dir / "file1.txt"
        file2 = repo_dir / "file2.txt"
        file1.write_text("content1")
        file2.write_text("content2")
        repo.commit("Initial")

        # Modify file1, delete file2, add file3
        file1.write_text("modified")
        file2.unlink()
        file3 = repo_dir / "file3.txt"
        file3.write_text("new")

        last_snapshot, changes = repo.get_status()
        assert last_snapshot.id == 1
        assert "file1.txt" in changes['modified']
        assert "file2.txt" in changes['deleted']
        assert "file3.txt" in changes['added']

    def test_multiple_amends(self, temp_repo):
        """Test that amend count increments correctly."""
        repo, repo_dir = temp_repo
        repo.init()

        test_file = repo_dir / "test.txt"

        # Commit 1
        test_file.write_text("Hello World")
        repo.commit("First")

        # Commit 2
        test_file.write_text("Hello")
        repo.commit("Second")

        # Multiple safe progressive changes
        test_file.write_text("Hell")
        repo.commit("Third")

        test_file.write_text("Hel")
        repo.commit("Fourth")

        test_file.write_text("He")
        repo.commit("Fifth")

        # Should have 2 snapshots, with snapshot 2 amended multiple times
        snapshots = repo.get_snapshots()
        assert len(snapshots) == 2
        assert snapshots[0].amend_count > 0
