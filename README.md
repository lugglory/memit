# memit: Smart Version Control with Character-Level Diff

A version control system that prevents excessive commit fragmentation by automatically amending safe commits using character-level diff and triangle inequality.

## Key Features

- **Smart Auto-Amend**: Automatically amends commits when safe (no information loss)
- **Character-Level Diff**: Uses precise character-level LCS for change detection
- **Triangle Inequality**: Leverages edit distance properties to detect information loss
- **Performance Optimized**: Line-level diff narrows search space before character-level analysis

## Core Algorithm

The system uses the **triangle inequality** to determine if amending is safe:

```
d(A,B) + d(B,C) == d(A,C)
```

Where:
- `A` = snapshot S[-2] (grandparent)
- `B` = snapshot S[-1] (current last snapshot)
- `C` = current working directory state
- `d(x,y)` = character-level indel distance = `|x| + |y| - 2 * LCS_length(x,y)`

If B is on the shortest edit path from A to C, amending is safe.

### Verified Examples

1. **SAFE**: `A="Hello World"`, `B="Hello"`, `C="Hel"`
   - d(A,B)=6, d(B,C)=2, d(A,C)=8
   - 6 + 2 = 8 ✓ (Progressive deletion)

2. **UNSAFE**: `A="abc"`, `B="abXc"`, `C="abc"`
   - d(A,B)=1, d(B,C)=1, d(A,C)=0
   - 1 + 1 ≠ 0 ✗ (Reverted insertion loses 'X')

3. **SAFE**: `A="abc"`, `B="abXc"`, `C="abXYc"`
   - d(A,B)=1, d(B,C)=1, d(A,C)=2
   - 1 + 1 = 2 ✓ (Progressive insertion)

4. **UNSAFE**: `A="abc"`, `B="ac"`, `C="abc"`
   - d(A,B)=1, d(B,C)=1, d(A,C)=0
   - 1 + 1 ≠ 0 ✗ (Reverted deletion loses information)

## Installation

```bash
# Clone the repository
git clone <repository-url>
cd memit

# Use directly with Python
python3 -m memit --help

# Or install locally
pip install -e .
```

## Usage

### Initialize Repository

```bash
memit init
```

### Create Commits

```bash
# Basic commit
memit commit -m "Your commit message"

# Force new snapshot (disable auto-amend)
memit commit -m "Message" --force-new

# Force amend (dangerous, overrides safety check)
memit commit -m "Message" --force-amend
```

### View History

```bash
# Show all commits
memit log

# Show last N commits
memit log -n 5
```

### Check Status

```bash
memit status
```

### View Changes

```bash
# Diff working directory against last snapshot
memit diff

# Diff specific snapshot against its parent
memit diff 3
```

## Example Session

```bash
# Initialize repository
cd /tmp/my_project
memit init

# First commit
echo "Hello World" > test.txt
memit commit -m "initial"
# Output: ✓ Created snapshot 1

# Second commit
echo "Hello" > test.txt
memit commit -m "partial delete"
# Output: ✓ Created snapshot 2

# Third commit (will auto-amend snapshot 2)
echo "Hel" > test.txt
memit commit -m "more delete"
# Output: ✓ Amended snapshot 2 (All changes are on the shortest edit path)

# Check history
memit log
# Shows only 2 snapshots (3rd commit amended 2nd)
```

## Repository Structure

```
.memit/
├── config.json           # Repository configuration
└── snapshots/
    └── 1/
        ├── meta.json     # Snapshot metadata
        └── files/        # Full copy of tracked files
```

### Snapshot Metadata

```json
{
  "id": 2,
  "message": "commit message",
  "timestamp": "2026-02-14T12:00:00",
  "parent": 1,
  "files": ["test.txt", "other.txt"],
  "amended": true,
  "amend_count": 3
}
```

## Ignore Patterns

Create `.memitignore` to specify patterns to ignore:

```
# Custom patterns
*.log
temp/
secrets.json

# Built-in patterns (automatically ignored):
# .memit, __pycache__, *.pyc, .git, .DS_Store, etc.
```

## Performance

- **LCS Calculation**: O(min(n,m)) space using DP optimization
- **Efficient Distance**: Line-level diff + character-level LCS only on changed hunks
- **Hunk Size Limit**: 10,000 characters (conservative fallback for larger hunks)

## Architecture

```
memit/
├── diff_engine.py    # LCS and edit distance calculation
├── ignore.py         # .memitignore pattern matching
├── snapshot.py       # Snapshot management
├── amend_check.py    # Triangle inequality validation
├── repository.py     # Core repository operations
├── display.py        # Terminal output formatting
└── cli.py           # Command-line interface
```

## Testing

```bash
# Run tests (requires pytest)
python3 -m pytest tests/ -v

# Run specific test file
python3 -m pytest tests/test_diff_engine.py -v
```

## Theory

The system is based on the property that edit distance forms a **metric space**, satisfying:

1. **Non-negativity**: d(x,y) ≥ 0
2. **Identity**: d(x,y) = 0 ⟺ x = y
3. **Symmetry**: d(x,y) = d(y,x)
4. **Triangle inequality**: d(x,z) ≤ d(x,y) + d(y,z)

When d(A,B) + d(B,C) = d(A,C), the **equality holds**, meaning B is on the shortest path from A to C. This guarantees no information is lost by replacing B with C.

## License

MIT

## Contributing

Contributions welcome! Please ensure all tests pass before submitting PRs.
