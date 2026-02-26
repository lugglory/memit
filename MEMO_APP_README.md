# Memit Memo App - Usage Guide

## Overview

A simple GUI application to test and visualize memit's auto-amend feature. This app lets you create and edit memos while tracking their version history.

## Running the App

```bash
cd D:\side_repos\memit\memit
python memo_app.py
```

## Features

### 1. **Memo Editor** (Left Panel)
- Write and edit your memos
- Changes are tracked but not saved until you commit
- Use `Ctrl+S` as a keyboard shortcut for Save & Commit

### 2. **History List** (Right Panel, Top)
- Shows all snapshots in reverse chronological order
- Format: `#{id}: {message} (amended {count}x) - {timestamp}`
- **Yellow background** = Amended snapshots (auto-merged commits)
- Click on any snapshot to see the diff

### 3. **Diff Preview** (Right Panel, Bottom)
- Shows character-level differences between selected snapshot and current content
- **Red text** = Deleted content
- **Green text** = Added content
- **Black text** = Unchanged content

### 4. **Status Bar** (Top)
- Shows current snapshot information
- Indicates if content has been modified (✏️) or is clean (✓)
- Shows amend count for amended snapshots

## How to Use

### Creating Your First Memo

1. Type something in the editor (e.g., "Hello World")
2. Enter a commit message (e.g., "initial memo")
3. Click "Save & Commit"
4. You'll see "Snapshot 1" created in the history

### Testing Auto-Amend

Memit automatically amends commits when changes follow the "shortest edit path":

**Example: Incremental Deletion**
1. Start with: "Hello World" → Save (message: "initial") → **Snapshot 1**
2. Change to: "Hello" → Save (message: "remove world") → **Snapshot 2**
3. Change to: "Hel" → Save (message: "typo fix") → **Snapshot 2 amended!**

The third change amends Snapshot 2 because removing "lo" is on the shortest path from "Hello World" to "Hel".

**Example: Linear Addition**
1. Start with: "A" → Save → **Snapshot 1**
2. Change to: "AB" → Save → **Snapshot 2**
3. Change to: "ABC" → Save → **Snapshot 2 amended!**

Adding "C" after "AB" is on the shortest path from "A" to "ABC".

### Viewing History and Diffs

1. Click on any snapshot in the History list
2. The Diff Preview shows what changed between that snapshot and your current content
3. Amended snapshots are highlighted in yellow

### Restoring Previous Versions

1. Select a snapshot from the History list
2. Click "Restore Selected Version"
3. Confirm the restoration
4. The snapshot's content will be loaded into the editor
5. Don't forget to "Save & Commit" to preserve the restoration

## Understanding the Output

### New Snapshot
```
✓ Created snapshot 3
```
A completely new version was created.

### Amended Snapshot
```
✓ Amended snapshot 2 (All changes are on the shortest edit path)
```
The changes were merged into snapshot 2 because they follow the optimal edit sequence.

## Files and Directories

- **memo_app.py** - The GUI application
- **memo_data/** - Working directory
  - **.memit/** - Memit repository (version history)
  - **memo.txt** - Your actual memo file

## Tips

- Use `Ctrl+S` to quickly save and commit
- The status bar shows if you have unsaved changes
- Yellow highlighting helps identify which snapshots have been auto-amended
- The diff preview updates in real-time as you select different snapshots

## Example Workflow

1. **Initial memo**: "Shopping list:\n- Milk"
   - Save with message "start shopping list"
   - **Snapshot 1 created**

2. **Add item**: "Shopping list:\n- Milk\n- Bread"
   - Save with message "add bread"
   - **Snapshot 2 created**

3. **Add another**: "Shopping list:\n- Milk\n- Bread\n- Eggs"
   - Save with message "add eggs"
   - **Snapshot 2 amended** (linear addition on shortest path)

4. **Remove all items**: "Shopping list:"
   - Save with message "clear list"
   - **Snapshot 3 created** (non-linear change, new snapshot needed)

## Troubleshooting

- If the app doesn't start, make sure you're in the correct directory
- The `memo_data` directory is created automatically
- History persists between sessions
- If you see an error, check that memit is properly installed

Enjoy testing memit's intelligent auto-amend feature!
