# Memit Memo App - Usage Guide

## Overview

A modern GUI application built with CustomTkinter to test and visualize memit's auto-amend feature. This app lets you create and edit memos while tracking their version history with a sleek dark-themed interface.

## Running the App

**Option 1: Using the convenience script (Recommended)**
```bash
./run_memo_app.sh
```

**Option 2: Manual activation**
```bash
source venv/bin/activate
python memo_app.py
```

**First-time setup:**
The app uses a Python virtual environment with CustomTkinter. The `run_memo_app.sh` script will automatically create the virtual environment and install dependencies on first run.

## Features

### 1. **Modern UI with CustomTkinter**
- Sleek dark-themed interface
- Smooth, professional appearance
- Responsive layout with grid-based design
- Custom buttons and input fields

### 2. **Memo Editor** (Left Panel)
- Large text editor with syntax highlighting
- Changes are tracked but not saved until you commit
- Use `Ctrl+S` as a keyboard shortcut for Save & Commit
- 💾 Save button with custom commit message option

### 3. **History List** (Right Panel, Top)
- Shows all snapshots in reverse chronological order
- Format: `#{id}: {message} ({amend_count}) - {timestamp}`
- **Automatic ordinal commit messages** (1, 2, 3, ...)
- **Yellow background** = Amended snapshots (auto-merged commits)
- **Green background** = Insert operations
- **Red background** = Delete operations
- **Blue background** = Mixed operations
- Click on any snapshot to see the diff
- Right-click to edit commit messages

### 4. **Diff Preview** (Right Panel, Bottom)
- Shows character-level differences between selected snapshot and current content
- **`[-text-]`** = Deleted content (red-highlighted)
- **`[+text+]`** = Added content (green-highlighted)
- Plain text = Unchanged content
- Clear, readable diff format

### 5. **Status Bar** (Top)
- Shows current snapshot information
- Indicates if content has been modified (✏️) or is clean (✓)
- Shows amend count for amended snapshots
- Rounded corners with subtle background color

## How to Use

### Creating Your First Memo

1. Type something in the editor (e.g., "Hello World")
2. Click "💾 Save (Ctrl+S)" button
3. Commit message "1" is automatically generated
4. You'll see "#1: 1" created in the history

**Note:** Commit messages are now automatically numbered (1, 2, 3, ...) for simplicity. You can check the "커밋 메시지 직접 입력" checkbox if you want to write custom messages.

### Testing Auto-Amend

Memit automatically amends commits when changes follow the "shortest edit path":

**Example: Incremental Deletion**
1. Start with: "Hello World" → Save → **Snapshot #1: 1**
2. Change to: "Hello" → Save → **Snapshot #2: 2**
3. Change to: "Hel" → Save → **Snapshot #2: 2 (1)** ← Amended!

The third change amends Snapshot 2 because removing "lo" is on the shortest path from "Hello World" to "Hel". The "(1)" indicates this snapshot has been amended once.

**Example: Linear Addition**
1. Start with: "A" → Save → **Snapshot #1: 1**
2. Change to: "AB" → Save → **Snapshot #2: 2**
3. Change to: "ABC" → Save → **Snapshot #2: 2 (1)** ← Amended!

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

- **Keyboard shortcut:** Use `Ctrl+S` to quickly save and commit
- **Status indicator:** The status bar shows if you have unsaved changes (✏️) or if it's clean (✓)
- **Color coding:**
  - Yellow = Amended snapshots
  - Green = Insert operations
  - Red = Delete operations
  - Blue = Mixed operations
- **Custom messages:** Check "커밋 메시지 직접 입력" to write your own commit messages
- **Edit history:** Right-click on any snapshot to edit its commit message
- **Diff preview:** Updates in real-time as you select different snapshots
- **Dark mode:** The app uses a modern dark theme by default

## Example Workflow

1. **Initial memo**: "Shopping list:\n- Milk"
   - Click Save (Ctrl+S)
   - **Snapshot #1: 1 created** (green background - insert)

2. **Add item**: "Shopping list:\n- Milk\n- Bread"
   - Click Save
   - **Snapshot #2: 2 created** (green background - insert)

3. **Add another**: "Shopping list:\n- Milk\n- Bread\n- Eggs"
   - Click Save
   - **Snapshot #2: 2 (1) amended** (yellow background - linear addition on shortest path)

4. **Remove all items**: "Shopping list:"
   - Click Save
   - **Snapshot #3: 3 created** (red background - delete, non-linear change, new snapshot needed)

## Technology Stack

- **Python 3.13+** - Programming language
- **CustomTkinter 5.2+** - Modern UI framework (built on tkinter)
- **Memit** - Custom version control system with auto-amend
- **Virtual Environment** - Isolated Python dependencies

## Troubleshooting

### App won't start
- Make sure you have Python 3.13+ installed
- Run `./run_memo_app.sh` which handles virtual environment setup automatically
- Check that `python3-tk` is installed: `sudo apt install python3-tk python3-venv`

### Import errors
- Activate the virtual environment: `source venv/bin/activate`
- Install dependencies: `pip install customtkinter`

### Display issues
- The app requires a graphical display (X11/Wayland)
- For headless environments, you'll need to set up a virtual display
- Color schemes work best on dark-themed systems

### General issues
- The `memo_data` directory is created automatically on first run
- History persists between sessions in `.memit/` directory
- If you see memit-related errors, check that the memit package is properly installed

## What's New

**v2.0 - Modern UI Update**
- 🎨 Upgraded to CustomTkinter for modern, sleek interface
- 🌙 Dark mode theme by default
- 📝 Simplified commit messages (automatic ordinal numbering: 1, 2, 3, ...)
- 🎯 Cleaner amended display format: `(count)` instead of `(amended countx)`
- 🎨 Color-coded history entries by operation type
- ✨ Improved button styling and layout
- 📱 Larger, more responsive window (1200x800)

Enjoy testing memit's intelligent auto-amend feature with a beautiful modern interface!
