"""
ignore.py: .memitignore pattern matching.
"""
import fnmatch
from pathlib import Path
from typing import Set


DEFAULT_IGNORE_PATTERNS = [
    '.memit',
    '.memit/**',
    '__pycache__',
    '__pycache__/**',
    '*.pyc',
    '*.pyo',
    '*.pyd',
    '.Python',
    '*.so',
    '*.egg',
    '*.egg-info',
    'dist',
    'build',
    '.git',
    '.git/**',
    '.svn',
    '.hg',
    '.DS_Store',
    'Thumbs.db',
    '*.swp',
    '*.swo',
    '*~',
    '.vscode',
    '.idea',
]


class IgnoreHandler:
    """Handles .memitignore pattern matching."""

    def __init__(self, repo_root: Path):
        """
        Initialize ignore handler.

        Args:
            repo_root: Root directory of the repository
        """
        self.repo_root = repo_root
        self.patterns = set(DEFAULT_IGNORE_PATTERNS)
        self._load_memitignore()

    def _load_memitignore(self):
        """Load patterns from .memitignore file if it exists."""
        ignore_file = self.repo_root / '.memitignore'
        if ignore_file.exists():
            try:
                with open(ignore_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        # Skip empty lines and comments
                        if line and not line.startswith('#'):
                            self.patterns.add(line)
            except Exception:
                # If we can't read the file, just use default patterns
                pass

    def should_ignore(self, path: Path) -> bool:
        """
        Check if a path should be ignored.

        Args:
            path: Path relative to repository root

        Returns:
            True if the path should be ignored
        """
        # Convert to relative path string
        try:
            rel_path = path.relative_to(self.repo_root)
        except ValueError:
            # Path is not relative to repo_root
            return True

        path_str = str(rel_path)

        # Check against all patterns
        for pattern in self.patterns:
            # Match against the full path
            if fnmatch.fnmatch(path_str, pattern):
                return True

            # Match against the filename only
            if fnmatch.fnmatch(path.name, pattern):
                return True

            # Match against any parent directory component
            parts = path_str.split('/')
            for i in range(len(parts)):
                partial = '/'.join(parts[:i + 1])
                if fnmatch.fnmatch(partial, pattern):
                    return True

        return False

    def get_tracked_files(self) -> Set[Path]:
        """
        Get all files that should be tracked (not ignored).

        Returns:
            Set of absolute paths to tracked files
        """
        tracked = set()

        for path in self.repo_root.rglob('*'):
            # Skip directories
            if path.is_dir():
                continue

            # Skip ignored files
            if self.should_ignore(path):
                continue

            tracked.add(path)

        return tracked
