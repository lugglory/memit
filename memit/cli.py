"""
cli.py: Command-line interface for memit.
"""
import argparse
import sys
from pathlib import Path
from .repository import Repository
from .display import (
    display_log,
    display_status,
    display_commit_result,
    display_snapshot_diff
)


def cmd_init(args):
    """Initialize a new repository."""
    repo = Repository(Path.cwd())
    message = repo.init()
    print(message)


def cmd_commit(args):
    """Create a commit."""
    repo = Repository(Path.cwd())

    if not repo.is_initialized():
        print("Not a memit repository (run 'memit init')")
        sys.exit(1)

    message = args.message
    if not message:
        print("Error: commit message required (use -m)")
        sys.exit(1)

    success, result_message = repo.commit(
        message=message,
        force_new=args.force_new,
        force_amend=args.force_amend
    )

    display_commit_result(success, result_message)

    if not success:
        sys.exit(1)


def cmd_log(args):
    """Display commit log."""
    repo = Repository(Path.cwd())

    if not repo.is_initialized():
        print("Not a memit repository (run 'memit init')")
        sys.exit(1)

    snapshots = repo.get_snapshots(limit=args.n)
    display_log(snapshots)


def cmd_status(args):
    """Display repository status."""
    repo = Repository(Path.cwd())

    if not repo.is_initialized():
        print("Not a memit repository (run 'memit init')")
        sys.exit(1)

    last_snapshot, changes = repo.get_status()
    display_status(last_snapshot, changes)


def cmd_diff(args):
    """Display diff between snapshots or working directory."""
    repo = Repository(Path.cwd())

    if not repo.is_initialized():
        print("Not a memit repository (run 'memit init')")
        sys.exit(1)

    # Get snapshots to compare
    if args.snapshot_id:
        # Diff specific snapshot against its parent
        try:
            from .snapshot import Snapshot
            snapshot_b = Snapshot.load(repo.memit_dir, args.snapshot_id)

            if snapshot_b.parent is None:
                print(f"Snapshot {args.snapshot_id} has no parent")
                sys.exit(1)

            snapshot_a = Snapshot.load(repo.memit_dir, snapshot_b.parent)
            display_snapshot_diff(snapshot_a, snapshot_b)
        except Exception as e:
            print(f"Error loading snapshot: {e}")
            sys.exit(1)
    else:
        # Diff working directory against last snapshot
        last_snapshot = repo.get_last_snapshot()

        if last_snapshot is None:
            print("No commits yet")
            sys.exit(1)

        # Create temporary snapshot for current working directory
        from .ignore import IgnoreHandler
        from .snapshot import Snapshot

        ignore_handler = IgnoreHandler(repo.root)
        tracked_files = ignore_handler.get_tracked_files()

        current_snapshot = Snapshot.from_working_directory(
            repo_root=repo.root,
            snapshot_id=0,
            message="(working directory)",
            parent=None,
            tracked_files=tracked_files
        )

        display_snapshot_diff(last_snapshot, current_snapshot)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        prog='memit',
        description='Smart version control with character-level diff'
    )

    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # init command
    parser_init = subparsers.add_parser('init', help='Initialize a new repository')
    parser_init.set_defaults(func=cmd_init)

    # commit command
    parser_commit = subparsers.add_parser('commit', help='Create a commit')
    parser_commit.add_argument('-m', '--message', help='Commit message')
    parser_commit.add_argument(
        '--force-new',
        action='store_true',
        help='Force creation of new snapshot (ignore amend logic)'
    )
    parser_commit.add_argument(
        '--force-amend',
        action='store_true',
        help='Force amend of last snapshot (dangerous!)'
    )
    parser_commit.set_defaults(func=cmd_commit)

    # log command
    parser_log = subparsers.add_parser('log', help='Display commit log')
    parser_log.add_argument('-n', type=int, help='Limit number of commits to show')
    parser_log.set_defaults(func=cmd_log)

    # status command
    parser_status = subparsers.add_parser('status', help='Display repository status')
    parser_status.set_defaults(func=cmd_status)

    # diff command
    parser_diff = subparsers.add_parser('diff', help='Display diff')
    parser_diff.add_argument('snapshot_id', type=int, nargs='?', help='Snapshot ID to diff')
    parser_diff.set_defaults(func=cmd_diff)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    args.func(args)


if __name__ == '__main__':
    main()
