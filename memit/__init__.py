"""
memit: Smart version control with character-level diff.

Prevents excessive commit fragmentation by automatically amending safe commits.
Uses triangle inequality on edit distance to detect information loss.
"""

__version__ = '0.1.0'

from .repository import Repository
from .snapshot import Snapshot

__all__ = ['Repository', 'Snapshot']
