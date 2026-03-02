#!/usr/bin/env python3
"""
Memit Memo App - Modern GUI with CustomTkinter for testing memit version control system.

This app demonstrates memit's auto-amend feature by providing a visual
interface for creating and editing memos while tracking their history.
"""

import customtkinter as ctk
import tkinter as tk
from tkinter import messagebox
from pathlib import Path
from datetime import datetime
from typing import Optional, List, Tuple

from memit.repository import Repository
from memit.snapshot import Snapshot
from memit.diff_engine import get_character_diff


# Set appearance and theme
ctk.set_appearance_mode("dark")  # "dark" or "light"
ctk.set_default_color_theme("blue")  # "blue", "green", "dark-blue"


class MemoApp:
    """Main application window for Memit Memo."""

    def __init__(self, root: ctk.CTk):
        self.root = root
        self.root.title("Memit Memo - Simple Version Control")
        self.root.geometry("1200x800")

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
        # Configure grid
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        # Status bar at top
        self.status_label = ctk.CTkLabel(
            self.root,
            text="Status: No snapshots yet",
            anchor="w",
            height=30,
            fg_color=("gray85", "gray20"),
            corner_radius=6
        )
        self.status_label.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")

        # Main content frame
        self.main_frame = ctk.CTkFrame(self.root)
        self.main_frame.grid(row=1, column=0, padx=10, pady=(5, 10), sticky="nsew")
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=6)
        self.main_frame.grid_columnconfigure(1, weight=4)

        # Left panel - Editor
        self.setup_editor_panel()

        # Right panel - History and Diff
        self.setup_history_panel()

    def setup_editor_panel(self):
        """Setup the left panel with memo editor."""
        self.editor_frame = ctk.CTkFrame(self.main_frame)
        self.editor_frame.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")
        self.editor_frame.grid_rowconfigure(1, weight=1)
        self.editor_frame.grid_columnconfigure(0, weight=1)

        # Editor label
        editor_label = ctk.CTkLabel(
            self.editor_frame,
            text="MEMO EDITOR",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        editor_label.grid(row=0, column=0, pady=(10, 5))

        # Text editor
        self.text_editor = ctk.CTkTextbox(
            self.editor_frame,
            font=ctk.CTkFont(family="Consolas", size=12),
            wrap="word",
            undo=True
        )
        self.text_editor.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        self.text_editor.bind('<KeyRelease>', self.on_text_modified)

        # Bottom controls
        controls_frame = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        controls_frame.grid(row=2, column=0, pady=10, padx=10, sticky="ew")

        # Save button
        self.save_button = ctk.CTkButton(
            controls_frame,
            text="💾 Save (Ctrl+S)",
            command=self.save_and_commit,
            font=ctk.CTkFont(size=13, weight="bold"),
            height=35
        )
        self.save_button.pack(side="left", padx=5)

        # Checkbox for custom commit message
        self.use_custom_msg = ctk.BooleanVar(value=False)
        self.custom_msg_check = ctk.CTkCheckBox(
            controls_frame,
            text="커밋 메시지 직접 입력",
            variable=self.use_custom_msg,
            font=ctk.CTkFont(size=12)
        )
        self.custom_msg_check.pack(side="left", padx=15)

    def setup_history_panel(self):
        """Setup the right panel with history and diff preview."""
        self.right_frame = ctk.CTkFrame(self.main_frame)
        self.right_frame.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="nsew")
        self.right_frame.grid_rowconfigure(1, weight=4)
        self.right_frame.grid_rowconfigure(3, weight=6)
        self.right_frame.grid_columnconfigure(0, weight=1)

        # Upper part - History
        history_label = ctk.CTkLabel(
            self.right_frame,
            text="HISTORY",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        history_label.grid(row=0, column=0, pady=(10, 5))

        # History listbox frame (using traditional Listbox with CTk frame)
        history_list_frame = ctk.CTkFrame(self.right_frame)
        history_list_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        history_list_frame.grid_rowconfigure(0, weight=1)
        history_list_frame.grid_columnconfigure(0, weight=1)

        # Scrollbar
        scrollbar = ctk.CTkScrollbar(history_list_frame)
        scrollbar.grid(row=0, column=1, sticky="ns")

        # Using traditional Listbox (CustomTkinter doesn't have a good Listbox replacement)
        self.history_listbox = tk.Listbox(
            history_list_frame,
            font=('Consolas', 10),
            yscrollcommand=scrollbar.set,
            selectmode=tk.SINGLE,
            bg="#2b2b2b",
            fg="#ffffff",
            selectbackground="#1f538d",
            selectforeground="#ffffff",
            bd=0,
            highlightthickness=0
        )
        self.history_listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.configure(command=self.history_listbox.yview)

        self.history_listbox.bind('<<ListboxSelect>>', self.on_history_select)

        # Context menu for editing commit messages
        self.history_context_menu = tk.Menu(self.history_listbox, tearoff=0)
        self.history_context_menu.add_command(label="커밋 메시지 수정", command=self.edit_commit_message)
        self.history_listbox.bind('<Button-3>', self.show_history_context_menu)

        # Separator
        separator = ctk.CTkFrame(self.right_frame, height=2, fg_color=("gray70", "gray30"))
        separator.grid(row=2, column=0, padx=10, pady=10, sticky="ew")

        # Lower part - Diff Preview
        diff_label = ctk.CTkLabel(
            self.right_frame,
            text="DIFF PREVIEW",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        diff_label.grid(row=3, column=0, pady=(5, 5), sticky="n")

        # Diff text area
        self.diff_text = ctk.CTkTextbox(
            self.right_frame,
            font=ctk.CTkFont(family="Consolas", size=10),
            wrap="word"
        )
        self.diff_text.grid(row=3, column=0, padx=10, pady=(30, 5), sticky="nsew")

        # Restore button
        self.restore_button = ctk.CTkButton(
            self.right_frame,
            text="↻ Restore Selected Version",
            command=self.restore_version,
            state="disabled",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=32
        )
        self.restore_button.grid(row=4, column=0, pady=10, padx=10)

    def on_text_modified(self, event=None):
        """Handle text modification event."""
        current_content = self.text_editor.get('1.0', 'end-1c')
        if current_content != self.last_saved_content:
            self.modified = True
            self.update_status()

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
            # Generate automatic commit message with ordinal number
            snapshot_count = len(self.repo.get_snapshots())
            message = str(snapshot_count + 1)

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
                    self.status_label.configure(text=f"✓ {msg} (shortest edit path)")
                else:
                    self.status_label.configure(text=f"✓ {msg}")

                # Refresh UI
                self.refresh_history()
                self.update_status()
            else:
                messagebox.showerror("Commit Failed", msg)

        except Exception as e:
            messagebox.showerror("Commit Error", f"Failed to commit: {e}")

    def show_commit_message_dialog(self) -> Optional[str]:
        """Show modal dialog for commit message input."""
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("커밋 메시지 입력")
        dialog.geometry("450x150")
        dialog.transient(self.root)
        dialog.grab_set()

        # Center the dialog
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        result = {"message": None}

        # Label
        ctk.CTkLabel(
            dialog,
            text="커밋 메시지를 입력하세요:",
            font=ctk.CTkFont(size=13)
        ).pack(pady=(15, 10), padx=15)

        # Entry
        entry = ctk.CTkEntry(dialog, font=ctk.CTkFont(family="Consolas", size=12), height=35)
        entry.pack(fill="x", padx=15, pady=10)
        entry.focus()

        def on_ok():
            result["message"] = entry.get().strip()
            if not result["message"]:
                snapshot_count = len(self.repo.get_snapshots())
                result["message"] = str(snapshot_count + 1)
            dialog.destroy()

        def on_cancel():
            result["message"] = None
            dialog.destroy()

        # Buttons
        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(pady=10)

        ctk.CTkButton(
            button_frame,
            text="확인",
            command=on_ok,
            width=100
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            button_frame,
            text="취소",
            command=on_cancel,
            width=100,
            fg_color="gray50",
            hover_color="gray40"
        ).pack(side="left", padx=5)

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
                    entry += f" ({snap.amend_count})"

                entry += f" - {time_str}"

                self.history_listbox.insert(tk.END, entry)
                idx = self.history_listbox.size() - 1

                # Determine change type and color
                bg_color = None

                if snap.amended and snap.amend_count > 0:
                    # Amended snapshots: yellow
                    bg_color = '#ffd966'
                else:
                    # Analyze change type
                    change_type = self.analyze_change_type(snap, i, snapshots)
                    if change_type == 'insert':
                        bg_color = '#90ee90'  # Light green
                    elif change_type == 'delete':
                        bg_color = '#ff9999'  # Light red
                    elif change_type == 'mixed':
                        bg_color = '#b0c4de'  # Light blue

                if bg_color:
                    self.history_listbox.itemconfig(idx, bg=bg_color, fg='#000000')

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
            self.restore_button.configure(state="disabled")
            return

        idx = selection[0]

        # Check if valid snapshot
        if not hasattr(self, 'snapshots') or idx >= len(self.snapshots):
            return

        selected_snapshot = self.snapshots[idx]

        # Enable restore button
        self.restore_button.configure(state="normal")

        # Get content from selected snapshot
        old_content = selected_snapshot.files.get('memo.txt', '')

        # Get current content
        new_content = self.text_editor.get('1.0', 'end-1c')

        # Show diff
        self.show_diff(old_content, new_content)

    def show_diff(self, old_content: str, new_content: str):
        """Display colored diff in preview pane."""
        # Clear diff text
        self.diff_text.delete('1.0', tk.END)

        if old_content == new_content:
            self.diff_text.insert('1.0', "[No differences - content is identical]")
            return

        # Get character-level diff
        try:
            diff_ops = get_character_diff(old_content, new_content)

            # Insert diff with colors (using tags for CTkTextbox)
            for op, text in diff_ops:
                if op == 'equal':
                    self.diff_text.insert(tk.END, text)
                elif op == 'delete':
                    # Show deleted text in red with strikethrough
                    self.diff_text.insert(tk.END, f"[-{text}-]")
                elif op == 'insert':
                    # Show inserted text in green
                    self.diff_text.insert(tk.END, f"[+{text}+]")

        except Exception as e:
            self.diff_text.insert('1.0', f"Error generating diff: {e}")

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
                    status += f" ({last_snapshot.amend_count})"

                if self.modified:
                    status += " | Modified ✏️"
                else:
                    status += " | Clean ✓"
            else:
                status = "No snapshots yet"
                if self.modified:
                    status += " | Modified ✏️"

            self.status_label.configure(text=f"Status: {status}")

        except Exception as e:
            self.status_label.configure(text=f"Status: Error - {e}")

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
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("커밋 메시지 수정")
        dialog.geometry("450x150")
        dialog.transient(self.root)
        dialog.grab_set()

        # Center the dialog
        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        result = {"message": None}

        # Label
        ctk.CTkLabel(
            dialog,
            text=f"Snapshot #{selected_snapshot.id}의 메시지를 수정:",
            font=ctk.CTkFont(size=13)
        ).pack(pady=(15, 10), padx=15)

        # Entry with current message
        entry = ctk.CTkEntry(dialog, font=ctk.CTkFont(family="Consolas", size=12), height=35)
        entry.pack(fill="x", padx=15, pady=10)
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
        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(pady=10)

        ctk.CTkButton(
            button_frame,
            text="확인",
            command=on_ok,
            width=100
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            button_frame,
            text="취소",
            command=on_cancel,
            width=100,
            fg_color="gray50",
            hover_color="gray40"
        ).pack(side="left", padx=5)

        # Bind keys
        entry.bind('<Return>', lambda e: on_ok())
        entry.bind('<Escape>', lambda e: on_cancel())

        dialog.wait_window()

        # Update the snapshot message
        if result["message"]:
            try:
                selected_snapshot.message = result["message"]
                selected_snapshot.save(self.repo.memit_dir)
                self.refresh_history()
                self.update_status()
                self.status_label.configure(text=f"✓ Snapshot #{selected_snapshot.id} 메시지 수정됨")
            except Exception as e:
                messagebox.showerror("Error", f"메시지 수정 실패: {e}")


def main():
    """Main entry point for the application."""
    root = ctk.CTk()
    app = MemoApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
