#!/usr/bin/env python3
"""
Memit Memo App - Simple GUI for testing memit version control system.

This app demonstrates memit's auto-amend feature by providing a visual
interface for creating and editing memos while tracking their history.
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple

from memit.repository import Repository
from memit.snapshot import Snapshot
from memit.diff_engine import get_character_diff


class MemoApp:
    """Main application window for Memit Memo."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Memit Memo - Simple Version Control")
        self.root.geometry("1000x700")

        # Initialize memit repository
        self.work_dir = Path.cwd() / "memo_data"
        self.work_dir.mkdir(exist_ok=True)
        self.repo = Repository(self.work_dir)

        if not self.repo.is_initialized():
            self.repo.init()

        self.memo_file = self.work_dir / "memo.txt"

        # Track if content has been modified
        self.modified = False
        self.last_saved_content = ""

        # Setup UI components
        self.setup_ui()

        # Load initial content
        self.load_content()
        self.refresh_history()
        self.update_status()

        # Setup keyboard shortcuts
        self.root.bind('<Control-s>', lambda e: self.save_and_commit())

    def setup_ui(self):
        """Create all UI widgets and layout."""
        # Status bar at top
        self.status_frame = ttk.Frame(self.root)
        self.status_frame.pack(side=tk.TOP, fill=tk.X, padx=5, pady=5)

        self.status_label = ttk.Label(
            self.status_frame,
            text="Status: No snapshots yet",
            relief=tk.SUNKEN,
            anchor=tk.W
        )
        self.status_label.pack(fill=tk.X)

        # Main content area with PanedWindow
        self.paned_window = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Left panel - Editor
        self.setup_editor_panel()

        # Right panel - History and Diff
        self.setup_history_panel()

        # Add panels to PanedWindow
        self.paned_window.add(self.editor_frame, weight=60)
        self.paned_window.add(self.right_frame, weight=40)

    def setup_editor_panel(self):
        """Setup the left panel with memo editor."""
        self.editor_frame = ttk.Frame(self.paned_window)

        # Editor label
        editor_label = ttk.Label(self.editor_frame, text="MEMO EDITOR", font=('Arial', 10, 'bold'))
        editor_label.pack(pady=5)

        # Text editor
        self.text_editor = scrolledtext.ScrolledText(
            self.editor_frame,
            font=('Consolas', 11),
            wrap=tk.WORD,
            undo=True
        )
        self.text_editor.pack(fill=tk.BOTH, expand=True, pady=5)
        self.text_editor.bind('<<Modified>>', self.on_text_modified)

        # Bottom controls
        controls_frame = ttk.Frame(self.editor_frame)
        controls_frame.pack(fill=tk.X, pady=5)

        # Save button
        self.save_button = ttk.Button(
            controls_frame,
            text="Save (Ctrl+S)",
            command=self.save_and_commit
        )
        self.save_button.pack(side=tk.LEFT, padx=5)

        # Checkbox for custom commit message
        self.use_custom_msg = tk.BooleanVar(value=False)
        self.custom_msg_check = ttk.Checkbutton(
            controls_frame,
            text="커밋 메시지 직접 입력",
            variable=self.use_custom_msg
        )
        self.custom_msg_check.pack(side=tk.LEFT, padx=(15, 5))

    def setup_history_panel(self):
        """Setup the right panel with history and diff preview."""
        self.right_frame = ttk.Frame(self.paned_window)

        # Upper part - History
        history_label = ttk.Label(self.right_frame, text="HISTORY", font=('Arial', 10, 'bold'))
        history_label.pack(pady=5)

        # History listbox with scrollbar
        history_frame = ttk.Frame(self.right_frame)
        history_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        scrollbar = ttk.Scrollbar(history_frame)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.history_listbox = tk.Listbox(
            history_frame,
            font=('Consolas', 9),
            yscrollcommand=scrollbar.set,
            selectmode=tk.SINGLE
        )
        self.history_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.config(command=self.history_listbox.yview)

        self.history_listbox.bind('<<ListboxSelect>>', self.on_history_select)

        # Context menu for editing commit messages
        self.history_context_menu = tk.Menu(self.history_listbox, tearoff=0)
        self.history_context_menu.add_command(label="커밋 메시지 수정", command=self.edit_commit_message)
        self.history_listbox.bind('<Button-3>', self.show_history_context_menu)

        # Separator
        ttk.Separator(self.right_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

        # Lower part - Diff Preview
        diff_label = ttk.Label(self.right_frame, text="DIFF PREVIEW", font=('Arial', 10, 'bold'))
        diff_label.pack(pady=5)

        # Diff text area
        self.diff_text = scrolledtext.ScrolledText(
            self.right_frame,
            font=('Consolas', 9),
            wrap=tk.WORD,
            height=15,
            state=tk.DISABLED
        )
        self.diff_text.pack(fill=tk.BOTH, expand=True, pady=5)

        # Configure color tags for diff
        self.diff_text.tag_config('delete', foreground='red', background='#ffe0e0')
        self.diff_text.tag_config('insert', foreground='green', background='#e0ffe0')
        self.diff_text.tag_config('equal', foreground='black')

        # Restore button
        self.restore_button = ttk.Button(
            self.right_frame,
            text="Restore Selected Version",
            command=self.restore_version,
            state=tk.DISABLED
        )
        self.restore_button.pack(pady=5)

    def on_text_modified(self, event=None):
        """Handle text modification event."""
        if self.text_editor.edit_modified():
            current_content = self.text_editor.get('1.0', 'end-1c')
            if current_content != self.last_saved_content:
                self.modified = True
                self.update_status()
            self.text_editor.edit_modified(False)

    def load_content(self):
        """Load memo content from file."""
        if self.memo_file.exists():
            content = self.memo_file.read_text(encoding='utf-8')
            self.text_editor.delete('1.0', tk.END)
            self.text_editor.insert('1.0', content)
            self.last_saved_content = content
        else:
            self.last_saved_content = ""

        self.modified = False
        self.text_editor.edit_modified(False)

    def save_and_commit(self):
        """Save memo.txt and commit to repository."""
        # Get content
        content = self.text_editor.get('1.0', 'end-1c')

        # Determine commit message
        message = None
        if self.use_custom_msg.get():
            # Show modal dialog for custom message
            message = self.show_commit_message_dialog()
            if message is None:  # User cancelled
                return
        else:
            # Generate automatic commit message with timestamp
            now = datetime.now()
            message = now.strftime("Update at %H:%M:%S")

        # Save to file
        try:
            self.memo_file.write_text(content, encoding='utf-8')
            self.last_saved_content = content
            self.modified = False
        except Exception as e:
            messagebox.showerror("Save Error", f"Failed to save file: {e}")
            return

        # Commit to repository
        try:
            success, msg = self.repo.commit(message)

            if success:
                # Update status bar to show result
                if "Amended" in msg:
                    self.status_label.config(text=f"✓ {msg} (shortest edit path)")
                else:
                    self.status_label.config(text=f"✓ {msg}")

                # Refresh UI
                self.refresh_history()
                self.update_status()
            else:
                messagebox.showerror("Commit Failed", msg)

        except Exception as e:
            messagebox.showerror("Commit Error", f"Failed to commit: {e}")

    def show_commit_message_dialog(self) -> Optional[str]:
        """Show modal dialog for commit message input."""
        dialog = tk.Toplevel(self.root)
        dialog.title("커밋 메시지 입력")
        dialog.geometry("400x120")
        dialog.transient(self.root)
        dialog.grab_set()

        # Center the dialog
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        result = {"message": None}

        # Label
        ttk.Label(dialog, text="커밋 메시지를 입력하세요:").pack(pady=10, padx=10)

        # Entry
        entry = ttk.Entry(dialog, font=('Consolas', 11))
        entry.pack(fill=tk.X, padx=10, pady=5)
        entry.focus()

        def on_ok():
            result["message"] = entry.get().strip()
            if not result["message"]:
                result["message"] = datetime.now().strftime("Update at %H:%M:%S")
            dialog.destroy()

        def on_cancel():
            result["message"] = None
            dialog.destroy()

        # Buttons
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)

        ttk.Button(button_frame, text="확인", command=on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="취소", command=on_cancel).pack(side=tk.LEFT, padx=5)

        # Bind Enter key
        entry.bind('<Return>', lambda e: on_ok())
        entry.bind('<Escape>', lambda e: on_cancel())

        dialog.wait_window()
        return result["message"]

    def refresh_history(self):
        """Update history listbox with snapshots."""
        # Clear listbox
        self.history_listbox.delete(0, tk.END)

        # Get snapshots
        try:
            snapshots = self.repo.get_snapshots(limit=50)

            if not snapshots:
                self.history_listbox.insert(tk.END, "No snapshots yet")
                return

            # Store snapshots for later reference
            self.snapshots = snapshots

            # Populate listbox (newest first)
            for i, snap in enumerate(snapshots):
                # Format timestamp
                try:
                    dt = datetime.fromisoformat(snap.timestamp)
                    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except:
                    time_str = snap.timestamp

                # Format entry
                entry = f"#{snap.id}: {snap.message}"

                if snap.amended and snap.amend_count > 0:
                    entry += f" (amended {snap.amend_count}x)"

                entry += f" - {time_str}"

                self.history_listbox.insert(tk.END, entry)
                idx = self.history_listbox.size() - 1

                # Determine change type and color
                bg_color = None

                if snap.amended and snap.amend_count > 0:
                    # Amended snapshots: yellow
                    bg_color = '#ffffcc'
                else:
                    # Analyze change type
                    change_type = self.analyze_change_type(snap, i, snapshots)
                    if change_type == 'insert':
                        bg_color = '#e0ffe0'  # Light green
                    elif change_type == 'delete':
                        bg_color = '#ffe0e0'  # Light red
                    elif change_type == 'mixed':
                        bg_color = '#e0e0ff'  # Light blue

                if bg_color:
                    self.history_listbox.itemconfig(idx, bg=bg_color)

        except Exception as e:
            self.history_listbox.insert(tk.END, f"Error loading history: {e}")

    def analyze_change_type(self, snapshot: Snapshot, index: int, snapshots: List[Snapshot]) -> str:
        """Analyze the type of change in this snapshot."""
        # Get previous snapshot
        if index >= len(snapshots) - 1:
            # First snapshot, consider it as insert
            return 'insert'

        prev_snapshot = snapshots[index + 1]

        # Get file contents
        current_content = snapshot.files.get('memo.txt', '')
        prev_content = prev_snapshot.files.get('memo.txt', '')

        if not prev_content and current_content:
            return 'insert'
        if prev_content and not current_content:
            return 'delete'

        # Analyze diff
        try:
            diff_ops = get_character_diff(prev_content, current_content)

            has_insert = False
            has_delete = False

            for op, text in diff_ops:
                if op == 'insert':
                    has_insert = True
                elif op == 'delete':
                    has_delete = True

            if has_insert and has_delete:
                return 'mixed'
            elif has_insert:
                return 'insert'
            elif has_delete:
                return 'delete'
            else:
                return 'mixed'
        except:
            return 'mixed'

    def on_history_select(self, event):
        """Show diff when snapshot selected."""
        selection = self.history_listbox.curselection()

        if not selection:
            self.restore_button.config(state=tk.DISABLED)
            return

        idx = selection[0]

        # Check if valid snapshot
        if not hasattr(self, 'snapshots') or idx >= len(self.snapshots):
            return

        selected_snapshot = self.snapshots[idx]

        # Enable restore button
        self.restore_button.config(state=tk.NORMAL)

        # Get content from selected snapshot
        old_content = selected_snapshot.files.get('memo.txt', '')

        # Get current content
        new_content = self.text_editor.get('1.0', 'end-1c')

        # Show diff
        self.show_diff(old_content, new_content)

    def show_diff(self, old_content: str, new_content: str):
        """Display colored diff in preview pane."""
        # Clear diff text
        self.diff_text.config(state=tk.NORMAL)
        self.diff_text.delete('1.0', tk.END)

        if old_content == new_content:
            self.diff_text.insert('1.0', "[No differences - content is identical]")
            self.diff_text.config(state=tk.DISABLED)
            return

        # Get character-level diff
        try:
            diff_ops = get_character_diff(old_content, new_content)

            # Insert diff with colors
            for op, text in diff_ops:
                if op == 'equal':
                    self.diff_text.insert(tk.END, text, 'equal')
                elif op == 'delete':
                    self.diff_text.insert(tk.END, text, 'delete')
                elif op == 'insert':
                    self.diff_text.insert(tk.END, text, 'insert')

        except Exception as e:
            self.diff_text.insert('1.0', f"Error generating diff: {e}")

        self.diff_text.config(state=tk.DISABLED)

    def restore_version(self):
        """Restore selected snapshot to editor."""
        selection = self.history_listbox.curselection()

        if not selection:
            return

        idx = selection[0]

        # Check if valid snapshot
        if not hasattr(self, 'snapshots') or idx >= len(self.snapshots):
            return

        selected_snapshot = self.snapshots[idx]

        # Confirm restore
        result = messagebox.askyesno(
            "Restore Version",
            f"Restore snapshot #{selected_snapshot.id}?\n\n"
            f"Message: {selected_snapshot.message}\n"
            f"Time: {selected_snapshot.timestamp}\n\n"
            f"Current unsaved changes will be lost."
        )

        if not result:
            return

        # Get content from snapshot
        content = selected_snapshot.files.get('memo.txt', '')

        # Set to editor
        self.text_editor.delete('1.0', tk.END)
        self.text_editor.insert('1.0', content)

        # Mark as modified (not saved yet)
        self.last_saved_content = ""  # Force modified state
        self.modified = True
        self.update_status()

        messagebox.showinfo(
            "Version Restored",
            f"Snapshot #{selected_snapshot.id} has been restored to the editor.\n\n"
            "Don't forget to Save & Commit to preserve this change."
        )

    def update_status(self):
        """Update status bar with current repository state."""
        try:
            last_snapshot, changes = self.repo.get_status()

            if last_snapshot:
                status = f"Snapshot #{last_snapshot.id}: {last_snapshot.message}"

                if last_snapshot.amended and last_snapshot.amend_count > 0:
                    status += f" (amended {last_snapshot.amend_count}x)"

                if self.modified:
                    status += " | Modified ✏️"
                else:
                    status += " | Clean ✓"
            else:
                status = "No snapshots yet"
                if self.modified:
                    status += " | Modified ✏️"

            self.status_label.config(text=f"Status: {status}")

        except Exception as e:
            self.status_label.config(text=f"Status: Error - {e}")

    def show_history_context_menu(self, event):
        """Show context menu on right-click."""
        # Select the item under cursor
        index = self.history_listbox.nearest(event.y)
        self.history_listbox.selection_clear(0, tk.END)
        self.history_listbox.selection_set(index)
        self.history_listbox.activate(index)

        # Show context menu
        try:
            self.history_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.history_context_menu.grab_release()

    def edit_commit_message(self):
        """Edit the commit message of the selected snapshot."""
        selection = self.history_listbox.curselection()

        if not selection:
            return

        idx = selection[0]

        # Check if valid snapshot
        if not hasattr(self, 'snapshots') or idx >= len(self.snapshots):
            return

        selected_snapshot = self.snapshots[idx]

        # Show dialog to edit message
        dialog = tk.Toplevel(self.root)
        dialog.title("커밋 메시지 수정")
        dialog.geometry("400x120")
        dialog.transient(self.root)
        dialog.grab_set()

        # Center the dialog
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        result = {"message": None}

        # Label
        ttk.Label(dialog, text=f"Snapshot #{selected_snapshot.id}의 메시지를 수정:").pack(pady=10, padx=10)

        # Entry with current message
        entry = ttk.Entry(dialog, font=('Consolas', 11))
        entry.pack(fill=tk.X, padx=10, pady=5)
        entry.insert(0, selected_snapshot.message)
        entry.select_range(0, tk.END)
        entry.focus()

        def on_ok():
            new_message = entry.get().strip()
            if new_message and new_message != selected_snapshot.message:
                result["message"] = new_message
            dialog.destroy()

        def on_cancel():
            result["message"] = None
            dialog.destroy()

        # Buttons
        button_frame = ttk.Frame(dialog)
        button_frame.pack(pady=10)

        ttk.Button(button_frame, text="확인", command=on_ok).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="취소", command=on_cancel).pack(side=tk.LEFT, padx=5)

        # Bind keys
        entry.bind('<Return>', lambda e: on_ok())
        entry.bind('<Escape>', lambda e: on_cancel())

        dialog.wait_window()

        # Update the snapshot message
        if result["message"]:
            try:
                selected_snapshot.message = result["message"]
                selected_snapshot.save()
                self.refresh_history()
                self.update_status()
                self.status_label.config(text=f"✓ Snapshot #{selected_snapshot.id} 메시지 수정됨")
            except Exception as e:
                messagebox.showerror("Error", f"메시지 수정 실패: {e}")


def main():
    """Main entry point for the application."""
    root = tk.Tk()
    app = MemoApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
