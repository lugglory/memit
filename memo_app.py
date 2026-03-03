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
from typing import Optional, List

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

        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = int(sw * 0.75)
        h = int(sh * 0.75)
        x = (sw - w) // 2
        y = (sh - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

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

        # Auto-pull on startup (silently ignore failures)
        self.root.after(500, self._auto_pull)

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
        # Right-click on status bar → remote settings
        self.status_label.bind('<Button-3>', lambda e: self.show_remote_settings())

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

        # Push button
        self.push_button = ctk.CTkButton(
            controls_frame,
            text="☁ Push",
            command=self.push_to_remote,
            font=ctk.CTkFont(size=13, weight="bold"),
            height=35,
            fg_color=("gray60", "gray30"),
            hover_color=("gray50", "gray40")
        )
        self.push_button.pack(side="left", padx=5)

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

        # History listbox frame
        history_list_frame = ctk.CTkFrame(self.right_frame)
        history_list_frame.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        history_list_frame.grid_rowconfigure(0, weight=1)
        history_list_frame.grid_columnconfigure(0, weight=1)

        scrollbar = ctk.CTkScrollbar(history_list_frame)
        scrollbar.grid(row=0, column=1, sticky="ns")

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

        diff_frame = ctk.CTkFrame(self.right_frame)
        diff_frame.grid(row=3, column=0, padx=10, pady=(30, 5), sticky="nsew")
        diff_frame.grid_rowconfigure(0, weight=1)
        diff_frame.grid_columnconfigure(0, weight=1)

        diff_scrollbar = ctk.CTkScrollbar(diff_frame)
        diff_scrollbar.grid(row=0, column=1, sticky="ns")

        self.diff_text = tk.Text(
            diff_frame,
            font=('Consolas', 10),
            wrap='word',
            bg='#1e1e1e',
            fg='#d4d4d4',
            bd=0,
            highlightthickness=0,
            yscrollcommand=diff_scrollbar.set,
            state='disabled'
        )
        self.diff_text.grid(row=0, column=0, sticky="nsew")
        diff_scrollbar.configure(command=self.diff_text.yview)

        self.diff_text.tag_config('delete', foreground='#ff6b6b', background='#3d1a1a')
        self.diff_text.tag_config('insert', foreground='#69db7c', background='#1a3d1a')

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

    def _auto_message(self, old_content: str, new_content: str) -> str:
        """Generate commit message from first 10 chars of changed content."""
        diff_ops = get_character_diff(old_content, new_content)

        changed = ''
        for op, text in diff_ops:
            if op in ('insert', 'delete'):
                changed += text.replace('\n', ' ')
                if len(changed) >= 10:
                    break

        changed = changed.strip()
        if not changed:
            return '(no changes)'
        if len(changed) > 10:
            return changed[:10] + '..'
        return changed

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
        content = self.text_editor.get('1.0', 'end-1c')

        # Determine commit message before saving
        if self.use_custom_msg.get():
            message = self.show_commit_message_dialog()
            if message is None:  # User cancelled
                return
        else:
            # Pre-compute auto-message from diff of current HEAD vs new content
            last_snap = self.repo.get_last_snapshot()
            parent_content = last_snap.files.get('memo.txt', '') if last_snap else ''
            message = self._auto_message(parent_content, content)

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
                if "Amended" in msg:
                    self.status_label.configure(text=f"✓ {msg} (shortest edit path)")
                else:
                    self.status_label.configure(text=f"✓ {msg}")

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

        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        result = {"message": None}

        ctk.CTkLabel(
            dialog,
            text="커밋 메시지를 입력하세요:",
            font=ctk.CTkFont(size=13)
        ).pack(pady=(15, 10), padx=15)

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

        entry.bind('<Return>', lambda e: on_ok())
        entry.bind('<Escape>', lambda e: on_cancel())

        dialog.wait_window()
        return result["message"]

    def refresh_history(self):
        """Update history listbox with snapshots."""
        self.history_listbox.delete(0, tk.END)

        try:
            snapshots = self.repo.get_snapshots(limit=50)

            if not snapshots:
                self.history_listbox.insert(tk.END, "No snapshots yet")
                return

            self.snapshots = snapshots

            for i, snap in enumerate(snapshots):
                try:
                    dt = datetime.fromisoformat(snap.timestamp)
                    time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    time_str = snap.timestamp

                short_id = snap.id[:7] if snap.id else '?'
                entry = f"[{short_id}] {snap.message} - {time_str}"

                self.history_listbox.insert(tk.END, entry)
                idx = self.history_listbox.size() - 1

                change_type = self.analyze_change_type(snap, i, snapshots)
                if change_type == 'insert':
                    bg_color = '#90ee90'
                elif change_type == 'delete':
                    bg_color = '#ff9999'
                elif change_type == 'mixed':
                    bg_color = '#b0c4de'
                else:
                    bg_color = None

                if bg_color:
                    self.history_listbox.itemconfig(idx, bg=bg_color, fg='#000000')

        except Exception as e:
            self.history_listbox.insert(tk.END, f"Error loading history: {e}")

    def analyze_change_type(self, snapshot: Snapshot, index: int, snapshots: List[Snapshot]) -> str:
        """Analyze the type of change in this snapshot."""
        if index >= len(snapshots) - 1:
            return 'insert'

        prev_snapshot = snapshots[index + 1]

        current_content = snapshot.files.get('memo.txt', '')
        prev_content = prev_snapshot.files.get('memo.txt', '')

        if not prev_content and current_content:
            return 'insert'
        if prev_content and not current_content:
            return 'delete'

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
        except Exception:
            return 'mixed'

    def on_history_select(self, event):
        """Show diff when snapshot selected."""
        selection = self.history_listbox.curselection()

        if not selection:
            self.restore_button.configure(state="disabled")
            return

        idx = selection[0]

        if not hasattr(self, 'snapshots') or idx >= len(self.snapshots):
            return

        selected_snapshot = self.snapshots[idx]
        self.restore_button.configure(state="normal")

        new_content = selected_snapshot.files.get('memo.txt', '')

        if idx + 1 < len(self.snapshots):
            prev_snapshot = self.snapshots[idx + 1]
            old_content = prev_snapshot.files.get('memo.txt', '')
        else:
            old_content = ''

        self.show_diff(old_content, new_content)

    def show_diff(self, old_content: str, new_content: str):
        """Display colored diff in preview pane."""
        self.diff_text.configure(state='normal')
        self.diff_text.delete('1.0', tk.END)

        if old_content == new_content:
            self.diff_text.insert('1.0', "[No differences - content is identical]")
            self.diff_text.configure(state='disabled')
            return

        try:
            diff_ops = get_character_diff(old_content, new_content)

            for op, text in diff_ops:
                if op == 'equal':
                    self.diff_text.insert(tk.END, text)
                elif op == 'delete':
                    self.diff_text.insert(tk.END, text, 'delete')
                elif op == 'insert':
                    self.diff_text.insert(tk.END, text, 'insert')

        except Exception as e:
            self.diff_text.insert('1.0', f"Error generating diff: {e}")

        self.diff_text.configure(state='disabled')

    def restore_version(self):
        """Restore selected snapshot to editor."""
        selection = self.history_listbox.curselection()

        if not selection:
            return

        idx = selection[0]

        if not hasattr(self, 'snapshots') or idx >= len(self.snapshots):
            return

        selected_snapshot = self.snapshots[idx]
        short_id = selected_snapshot.id[:7] if selected_snapshot.id else '?'

        result = messagebox.askyesno(
            "Restore Version",
            f"Restore snapshot [{short_id}]?\n\n"
            f"Message: {selected_snapshot.message}\n"
            f"Time: {selected_snapshot.timestamp}\n\n"
            f"Current unsaved changes will be lost."
        )

        if not result:
            return

        content = selected_snapshot.files.get('memo.txt', '')

        self.text_editor.delete('1.0', tk.END)
        self.text_editor.insert('1.0', content)

        self.last_saved_content = ""
        self.modified = True
        self.update_status()

        messagebox.showinfo(
            "Version Restored",
            f"Snapshot [{short_id}] has been restored to the editor.\n\n"
            "Don't forget to Save & Commit to preserve this change."
        )

    def update_status(self):
        """Update status bar with current repository state and sync info."""
        try:
            last_snapshot, changes = self.repo.get_status()

            if last_snapshot:
                short_id = last_snapshot.id[:7] if last_snapshot.id else '?'
                status = f"[{short_id}] {last_snapshot.message}"

                if self.modified:
                    status += " | Modified ✏️"
                else:
                    status += " | Clean ✓"

                # Show sync status if upstream is configured
                count = self.repo.get_unpushed_count()
                if count is not None:
                    if count > 0:
                        status += f" | ↑{count} unpushed"
                    else:
                        status += " | ✓ synced"
            else:
                status = "No snapshots yet"
                if self.modified:
                    status += " | Modified ✏️"

            self.status_label.configure(text=f"Status: {status}")

        except Exception as e:
            self.status_label.configure(text=f"Status: Error - {e}")

    def push_to_remote(self):
        """Push to remote, showing remote settings dialog if no remote is set."""
        remote_url = self.repo.get_remote_url()
        if not remote_url:
            if self.repo.is_gh_available():
                self.show_github_create_dialog()
            else:
                self.show_remote_settings()
            return

        success, msg = self.repo.push()
        if success:
            self.status_label.configure(text="✓ Push successful")
            self.update_status()
        else:
            retry = messagebox.askyesno(
                "Push Failed",
                f"Push 실패:\n{msg}\n\nRemote 주소를 재설정하시겠습니까?"
            )
            if retry:
                self.show_remote_settings()

    def show_github_create_dialog(self):
        """Show dialog to create a new GitHub repository via gh CLI."""
        username = self.repo.get_gh_username() or "unknown"

        dialog = ctk.CTkToplevel(self.root)
        dialog.title("GitHub 저장소 생성")
        dialog.geometry("460x260")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)

        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        # Account info row
        account_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        account_frame.pack(fill="x", padx=20, pady=(15, 5))
        ctk.CTkLabel(
            account_frame,
            text=f"계정: {username}  (GitHub CLI 연결됨 ✓)",
            font=ctk.CTkFont(size=12),
            text_color=("gray40", "gray70")
        ).pack(side="left")

        # Repo name entry
        ctk.CTkLabel(
            dialog,
            text="저장소 이름:",
            font=ctk.CTkFont(size=13)
        ).pack(anchor="w", padx=20, pady=(5, 2))

        name_entry = ctk.CTkEntry(
            dialog,
            font=ctk.CTkFont(family="Consolas", size=12),
            height=35
        )
        name_entry.pack(fill="x", padx=20)
        name_entry.insert(0, "memit-memo")
        name_entry.focus()

        # Live preview label
        preview_label = ctk.CTkLabel(
            dialog,
            text=f"→ github.com/{username}/memit-memo",
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color=("gray40", "gray60")
        )
        preview_label.pack(anchor="w", padx=22, pady=(2, 8))

        def update_preview(event=None):
            name = name_entry.get().strip() or "..."
            preview_label.configure(text=f"→ github.com/{username}/{name}")

        name_entry.bind('<KeyRelease>', update_preview)

        # Visibility radio buttons
        visibility_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        visibility_frame.pack(fill="x", padx=20, pady=(0, 12))

        is_private = tk.BooleanVar(value=True)

        ctk.CTkRadioButton(
            visibility_frame,
            text="Private (기본)",
            variable=is_private,
            value=True,
            font=ctk.CTkFont(size=12)
        ).pack(side="left", padx=(0, 20))

        ctk.CTkRadioButton(
            visibility_frame,
            text="Public",
            variable=is_private,
            value=False,
            font=ctk.CTkFont(size=12)
        ).pack(side="left")

        # Buttons row
        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(pady=5)

        create_btn = ctk.CTkButton(
            button_frame,
            text="생성 & Push",
            width=120,
            font=ctk.CTkFont(size=13, weight="bold")
        )
        create_btn.pack(side="left", padx=5)

        ctk.CTkButton(
            button_frame,
            text="URL 직접 입력",
            width=120,
            font=ctk.CTkFont(size=12),
            fg_color=("gray60", "gray35"),
            hover_color=("gray50", "gray45"),
            command=lambda: [dialog.destroy(), self.show_remote_settings()]
        ).pack(side="left", padx=5)

        ctk.CTkButton(
            button_frame,
            text="취소",
            width=80,
            font=ctk.CTkFont(size=12),
            fg_color=("gray60", "gray35"),
            hover_color=("gray50", "gray45"),
            command=dialog.destroy
        ).pack(side="left", padx=5)

        def on_create():
            name = name_entry.get().strip()
            if not name:
                messagebox.showwarning("입력 오류", "저장소 이름을 입력하세요.", parent=dialog)
                return

            create_btn.configure(state="disabled", text="생성 중...")
            dialog.update()

            success, result = self.repo.create_github_repo(name, private=is_private.get())

            if success:
                dialog.destroy()
                self.status_label.configure(text=f"✓ GitHub 저장소 생성 및 Push 완료: {result}")
                self.update_status()
            else:
                create_btn.configure(state="normal", text="생성 & Push")
                messagebox.showerror("생성 실패", f"저장소 생성에 실패했습니다:\n{result}", parent=dialog)

        create_btn.configure(command=on_create)
        name_entry.bind('<Return>', lambda e: on_create())

    def show_remote_settings(self):
        """Show dialog to configure remote URL."""
        dialog = ctk.CTkToplevel(self.root)
        dialog.title("Remote 설정")
        dialog.geometry("500x200")
        dialog.transient(self.root)
        dialog.grab_set()

        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        current_url = self.repo.get_remote_url() or ""

        ctk.CTkLabel(
            dialog,
            text="GitHub Remote URL:",
            font=ctk.CTkFont(size=13, weight="bold")
        ).pack(pady=(15, 5), padx=15, anchor="w")

        url_entry = ctk.CTkEntry(
            dialog,
            font=ctk.CTkFont(family="Consolas", size=11),
            height=35,
            placeholder_text="repo-name  또는  https://github.com/username/repo.git"
        )
        url_entry.pack(fill="x", padx=15, pady=5)
        if current_url:
            url_entry.insert(0, current_url)
        url_entry.focus()

        ctk.CTkLabel(
            dialog,
            text="인증은 Git Credential Manager 또는 SSH 키를 사용하세요.",
            font=ctk.CTkFont(size=11),
            text_color=("gray50", "gray60")
        ).pack(padx=15, anchor="w")

        button_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        button_frame.pack(pady=15)

        def on_save():
            url = url_entry.get().strip()
            if not url:
                messagebox.showwarning("입력 오류", "URL을 입력하세요.")
                return
            # 저장소명만 입력한 경우 full URL로 자동 변환
            if '/' not in url and '.' not in url:
                username = self.repo.get_gh_username() or ""
                if not username:
                    messagebox.showwarning("입력 오류", "저장소명만 입력하려면 gh CLI 인증이 필요합니다.\n전체 URL을 입력하세요.")
                    return
                url = f"https://github.com/{username}/{url}.git"
            if self.repo.set_remote_url(url):
                dialog.destroy()
                self.update_status()
                # Offer to push immediately
                if messagebox.askyesno("Push", f"Remote URL이 설정되었습니다.\n지금 Push하시겠습니까?"):
                    self.push_to_remote()
            else:
                messagebox.showerror("오류", "Remote URL 설정에 실패했습니다.")

        def on_cancel():
            dialog.destroy()

        ctk.CTkButton(
            button_frame,
            text="저장",
            command=on_save,
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

        url_entry.bind('<Return>', lambda e: on_save())
        url_entry.bind('<Escape>', lambda e: on_cancel())

        dialog.wait_window()

    def _auto_pull(self):
        """Pull from remote on startup (silently ignore failures)."""
        try:
            success, msg = self.repo.pull()
            if success and msg not in ("skipped (no remote)", "Already up to date"):
                # Refresh UI if we pulled new commits
                self.refresh_history()
                self.update_status()
        except Exception:
            pass  # Network unavailable or other error — ignore silently

    def show_history_context_menu(self, event):
        """Show context menu on right-click."""
        index = self.history_listbox.nearest(event.y)
        self.history_listbox.selection_clear(0, tk.END)
        self.history_listbox.selection_set(index)
        self.history_listbox.activate(index)

        try:
            self.history_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.history_context_menu.grab_release()

    def edit_commit_message(self):
        """Edit the commit message of the selected snapshot (HEAD only, unpushed only)."""
        selection = self.history_listbox.curselection()

        if not selection:
            return

        idx = selection[0]

        if not hasattr(self, 'snapshots') or idx >= len(self.snapshots):
            return

        selected_snapshot = self.snapshots[idx]
        short_id = selected_snapshot.id[:7] if selected_snapshot.id else '?'

        # Only HEAD is editable
        head_snap = self.repo.get_last_snapshot()
        if head_snap is None or head_snap.id != selected_snapshot.id:
            messagebox.showinfo(
                "알림",
                "가장 최근 스냅샷의 메시지만 수정할 수 있습니다.\n"
                "(Push되지 않은 커밋에 한해)"
            )
            return

        dialog = ctk.CTkToplevel(self.root)
        dialog.title("커밋 메시지 수정")
        dialog.geometry("450x150")
        dialog.transient(self.root)
        dialog.grab_set()

        dialog.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - dialog.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        result = {"message": None}

        ctk.CTkLabel(
            dialog,
            text=f"[{short_id}] 메시지 수정:",
            font=ctk.CTkFont(size=13)
        ).pack(pady=(15, 10), padx=15)

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

        entry.bind('<Return>', lambda e: on_ok())
        entry.bind('<Escape>', lambda e: on_cancel())

        dialog.wait_window()

        if result["message"]:
            try:
                ok, reason = self.repo.update_commit_message(selected_snapshot.id, result["message"])
                if ok:
                    self.refresh_history()
                    self.update_status()
                    self.status_label.configure(text=f"✓ [{short_id}] 메시지 수정됨")
                else:
                    messagebox.showerror("Error", f"메시지 수정 실패: {reason}")
            except Exception as e:
                messagebox.showerror("Error", f"메시지 수정 실패: {e}")


def main():
    """Main entry point for the application."""
    root = ctk.CTk()
    app = MemoApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
