#!/usr/bin/env python3
"""
Memit Memo App - Single-file .memit document editor with version history.

Run with a .memit file path to open it directly:
    python memo_app.py notes.memit

Run without arguments to show the Open/New file dialog.
"""

import sys
import tkinter as tk
import tkinter.font as tkfont
from pathlib import Path
from datetime import datetime
from tkinter import filedialog, messagebox
from typing import List, Optional

import customtkinter as ctk

from memit.document import MemitDocument, MemitSnapshot
from memit.amend_check import check_amend_safe
from memit.diff_engine import get_character_diff


# Appearance
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


# ---------------------------------------------------------------------------
# Startup file chooser (shown when no CLI argument is given)
# ---------------------------------------------------------------------------

def _ask_file_path() -> Optional[Path]:
    """
    Show a startup dialog asking the user to open or create a .memit file.
    Returns the chosen Path, or None if the user cancelled.
    """
    temp = tk.Tk()
    temp.withdraw()

    result: dict = {"path": None, "done": False}

    dialog = tk.Toplevel(temp)
    dialog.title("Memit Memo")
    dialog.resizable(False, False)
    dialog.grab_set()

    # Center on screen
    dialog.update_idletasks()
    w, h = 320, 130
    sw, sh = dialog.winfo_screenwidth(), dialog.winfo_screenheight()
    dialog.geometry(f"{w}x{h}+{(sw - w)//2}+{(sh - h)//2}")

    tk.Label(dialog, text="메모 파일을 선택하세요", font=("Segoe UI", 11),
             pady=5).pack(pady=(18, 10))

    btn_frame = tk.Frame(dialog)
    btn_frame.pack()

    def open_file():
        path = filedialog.askopenfilename(
            parent=dialog,
            title="메모 파일 열기",
            filetypes=[("Memit 파일", "*.memit"), ("모든 파일", "*.*")],
        )
        if path:
            result["path"] = Path(path)
        result["done"] = True
        dialog.destroy()

    def new_file():
        path = filedialog.asksaveasfilename(
            parent=dialog,
            title="새 메모 파일 만들기",
            defaultextension=".memit",
            filetypes=[("Memit 파일", "*.memit")],
        )
        if path:
            result["path"] = Path(path)
        result["done"] = True
        dialog.destroy()

    def on_close():
        result["done"] = True
        dialog.destroy()

    tk.Button(btn_frame, text="파일 열기", command=open_file,
              width=12, pady=4).pack(side="left", padx=8)
    tk.Button(btn_frame, text="새로 만들기", command=new_file,
              width=12, pady=4).pack(side="left", padx=8)

    dialog.protocol("WM_DELETE_WINDOW", on_close)
    dialog.wait_window()
    temp.destroy()
    return result["path"]


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class MemoApp:
    """Main application window for Memit Memo."""

    def __init__(self, root: ctk.CTk, doc: MemitDocument):
        self.root = root
        self.doc = doc

        self.root.title(f"{doc.path.name} - Memit Memo")

        # Window size: 75% of screen
        self.root.update_idletasks()
        sw = self.root.winfo_screenwidth()
        sh = self.root.winfo_screenheight()
        w = int(sw * 0.75)
        h = int(sh * 0.75)
        self.root.geometry(f"{w}x{h}+{(sw - w)//2}+{(sh - h)//2}")

        self.modified = False
        self.last_saved_content = ""

        self.setup_ui()
        self.load_content()
        self.refresh_history()
        self.update_status()

        self.root.bind('<Control-s>', lambda e: self.save_and_commit())

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def setup_ui(self):
        self.root.grid_rowconfigure(1, weight=1)
        self.root.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            self.root,
            text="Status: No snapshots yet",
            anchor="w",
            height=30,
            fg_color=("gray85", "gray20"),
            corner_radius=6,
        )
        self.status_label.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")

        self.main_frame = ctk.CTkFrame(self.root)
        self.main_frame.grid(row=1, column=0, padx=10, pady=(5, 10), sticky="nsew")
        self.main_frame.grid_rowconfigure(0, weight=1)
        self.main_frame.grid_columnconfigure(0, weight=6)
        self.main_frame.grid_columnconfigure(1, weight=4)

        self.setup_editor_panel()
        self.setup_history_panel()

    def setup_editor_panel(self):
        self.editor_frame = ctk.CTkFrame(self.main_frame)
        self.editor_frame.grid(row=0, column=0, padx=(10, 5), pady=10, sticky="nsew")
        self.editor_frame.grid_rowconfigure(1, weight=1)
        self.editor_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.editor_frame,
            text="MEMO EDITOR",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, pady=(10, 5))

        self.text_editor = ctk.CTkTextbox(
            self.editor_frame,
            font=ctk.CTkFont(family="Consolas", size=14),
            wrap="word",
            undo=True,
        )
        self.text_editor.grid(row=1, column=0, padx=10, pady=5, sticky="nsew")
        # Windows IME가 CTkFont를 인식하지 못해 조합 문자 크기가 작아지므로
        # 내부 tk.Text 위젯에 직접 tkfont.Font를 재지정한다.
        self.text_editor._textbox.configure(font=tkfont.Font(family="Consolas", size=14))
        self.text_editor.bind('<KeyRelease>', self.on_text_modified)

        # Bottom controls row
        controls_frame = ctk.CTkFrame(self.editor_frame, fg_color="transparent")
        controls_frame.grid(row=2, column=0, pady=10, padx=10, sticky="ew")

        self.save_button = ctk.CTkButton(
            controls_frame,
            text="💾 Save (Ctrl+S)",
            command=self.save_and_commit,
            font=ctk.CTkFont(size=13, weight="bold"),
            height=35,
        )
        self.save_button.pack(side="left", padx=(0, 5))

        self.use_custom_msg = ctk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            controls_frame,
            text="커밋 메시지 직접 입력",
            variable=self.use_custom_msg,
            font=ctk.CTkFont(size=12),
        ).pack(side="left", padx=10)

        # Export buttons
        ctk.CTkButton(
            controls_frame,
            text="클립보드 복사",
            command=self.copy_to_clipboard,
            font=ctk.CTkFont(size=12),
            height=35,
            width=110,
        ).pack(side="right", padx=(5, 0))

        ctk.CTkButton(
            controls_frame,
            text="TXT 저장",
            command=self.export_txt,
            font=ctk.CTkFont(size=12),
            height=35,
            width=90,
        ).pack(side="right", padx=5)

    def setup_history_panel(self):
        self.right_frame = ctk.CTkFrame(self.main_frame)
        self.right_frame.grid(row=0, column=1, padx=(5, 10), pady=10, sticky="nsew")
        self.right_frame.grid_rowconfigure(1, weight=4)
        self.right_frame.grid_rowconfigure(3, weight=6)
        self.right_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.right_frame,
            text="HISTORY",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=0, column=0, pady=(10, 5))

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
            highlightthickness=0,
        )
        self.history_listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.configure(command=self.history_listbox.yview)

        self.history_listbox.bind('<<ListboxSelect>>', self.on_history_select)

        self.history_context_menu = tk.Menu(self.history_listbox, tearoff=0)
        self.history_context_menu.add_command(
            label="커밋 메시지 수정", command=self.edit_commit_message
        )
        self.history_listbox.bind('<Button-3>', self.show_history_context_menu)

        separator = ctk.CTkFrame(self.right_frame, height=2, fg_color=("gray70", "gray30"))
        separator.grid(row=2, column=0, padx=10, pady=10, sticky="ew")

        ctk.CTkLabel(
            self.right_frame,
            text="DIFF PREVIEW",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).grid(row=3, column=0, pady=(5, 5), sticky="n")

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
            state='disabled',
        )
        self.diff_text.grid(row=0, column=0, sticky="nsew")
        diff_scrollbar.configure(command=self.diff_text.yview)

        self.diff_text.tag_config('delete', foreground='#ff6b6b', background='#3d1a1a')
        self.diff_text.tag_config('insert', foreground='#69db7c', background='#1a3d1a')

        self.restore_button = ctk.CTkButton(
            self.right_frame,
            text="↻ Restore Selected Version",
            command=self.restore_version,
            state="disabled",
            font=ctk.CTkFont(size=12, weight="bold"),
            height=32,
        )
        self.restore_button.grid(row=4, column=0, pady=10, padx=10)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def _auto_message(self, old_content: str, new_content: str) -> str:
        """Generate a short commit message from the first changed characters."""
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
        return changed[:10] + '..' if len(changed) > 10 else changed

    def on_text_modified(self, event=None):
        current = self.text_editor.get('1.0', 'end-1c')
        if current != self.last_saved_content:
            self.modified = True
            self.update_status()

    def load_content(self):
        """Load content from document into editor."""
        content = self.doc.get_content()
        self.text_editor.delete('1.0', tk.END)
        if content:
            self.text_editor.insert('1.0', content)
        self.last_saved_content = content
        self.modified = False

    def save_and_commit(self):
        """Commit current editor content to the document."""
        new_content = self.text_editor.get('1.0', 'end-1c')

        if self.use_custom_msg.get():
            custom_message = self.show_commit_message_dialog()
            if custom_message is None:
                return
            message = custom_message
        else:
            snapshots = self.doc.get_snapshots()
            if len(snapshots) >= 2:
                second_last = snapshots[-2]
                last = snapshots[-1]
                is_safe, _ = check_amend_safe(
                    A_files={"memo": second_last.content},
                    B_files={"memo": last.content},
                    C_files={"memo": new_content},
                )
                old_content = second_last.content if is_safe else last.content
            else:
                old_content = self.doc.get_content()
            message = self._auto_message(old_content, new_content)

        try:
            success, result_msg = self.doc.commit(new_content, message)
        except Exception as e:
            messagebox.showerror("Commit Error", f"Failed to commit: {e}")
            return

        if success:
            self.last_saved_content = new_content
            self.modified = False
            prefix = "✓ Amended" if "Amended" in result_msg else "✓ Saved"
            self.status_label.configure(text=f"{prefix}: {result_msg}")
            self.refresh_history()
            self.update_status()
        else:
            self.status_label.configure(text=f"ℹ {result_msg}")

    def copy_to_clipboard(self):
        """Copy current editor content to the system clipboard."""
        content = self.text_editor.get('1.0', 'end-1c')
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self.status_label.configure(text="✓ 클립보드에 복사됨")

    def export_txt(self):
        """Save current content as a plain .txt file."""
        path = filedialog.asksaveasfilename(
            parent=self.root,
            title="TXT로 저장",
            defaultextension=".txt",
            filetypes=[("텍스트 파일", "*.txt"), ("모든 파일", "*.*")],
        )
        if not path:
            return
        try:
            self.doc.export_txt(Path(path))
            self.status_label.configure(text=f"✓ TXT 저장됨: {Path(path).name}")
        except Exception as e:
            messagebox.showerror("저장 오류", f"파일 저장 실패: {e}")

    # ------------------------------------------------------------------
    # Commit message dialog
    # ------------------------------------------------------------------

    def show_commit_message_dialog(self) -> Optional[str]:
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

        ctk.CTkLabel(dialog, text="커밋 메시지를 입력하세요:",
                     font=ctk.CTkFont(size=13)).pack(pady=(15, 5), padx=15)

        entry = ctk.CTkEntry(dialog, font=ctk.CTkFont(family="Consolas", size=12), height=35)
        entry.pack(fill="x", padx=15, pady=5)
        entry.focus()

        def on_ok():
            msg = entry.get().strip()
            if not msg:
                msg = str(len(self.doc.get_snapshots()) + 1)
            result["message"] = msg
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="확인", command=on_ok, width=100).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="취소", command=on_cancel, width=100,
                      fg_color="gray50", hover_color="gray40").pack(side="left", padx=5)

        entry.bind('<Return>', lambda e: on_ok())
        entry.bind('<Escape>', lambda e: on_cancel())
        dialog.wait_window()
        return result["message"]

    # ------------------------------------------------------------------
    # History panel
    # ------------------------------------------------------------------

    def refresh_history(self):
        self.history_listbox.delete(0, tk.END)

        snapshots = list(reversed(self.doc.get_snapshots()))  # newest first
        self.snapshots: List[MemitSnapshot] = snapshots

        if not snapshots:
            self.history_listbox.insert(tk.END, "No snapshots yet")
            return

        for i, snap in enumerate(snapshots):
            try:
                dt = datetime.fromisoformat(snap.timestamp)
                time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                time_str = snap.timestamp

            entry = f"#{snap.id}: {snap.message} - {time_str}"
            self.history_listbox.insert(tk.END, entry)
            idx = self.history_listbox.size() - 1

            change_type = self._change_type(snap, i, snapshots)
            bg = {'insert': '#90ee90', 'delete': '#ff9999', 'mixed': '#b0c4de'}.get(change_type)
            if bg:
                self.history_listbox.itemconfig(idx, bg=bg, fg='#000000')

    def _change_type(self, snap: MemitSnapshot, index: int,
                     snapshots: List[MemitSnapshot]) -> str:
        """Classify the change type for coloring the history entry."""
        if index >= len(snapshots) - 1:
            return 'insert'

        prev = snapshots[index + 1]
        cur_content = snap.content
        prev_content = prev.content

        if not prev_content and cur_content:
            return 'insert'
        if prev_content and not cur_content:
            return 'delete'

        try:
            diff_ops = get_character_diff(prev_content, cur_content)
            has_ins = any(op == 'insert' for op, _ in diff_ops)
            has_del = any(op == 'delete' for op, _ in diff_ops)
            if has_ins and has_del:
                return 'mixed'
            return 'insert' if has_ins else ('delete' if has_del else 'mixed')
        except Exception:
            return 'mixed'

    def on_history_select(self, event=None):
        selection = self.history_listbox.curselection()
        if not selection or not hasattr(self, 'snapshots'):
            self.restore_button.configure(state="disabled")
            return

        idx = selection[0]
        if idx >= len(self.snapshots):
            return

        self.restore_button.configure(state="normal")

        snap = self.snapshots[idx]
        new_content = snap.content
        old_content = self.snapshots[idx + 1].content if idx + 1 < len(self.snapshots) else ''
        self.show_diff(old_content, new_content)

    def show_diff(self, old_content: str, new_content: str):
        self.diff_text.configure(state='normal')
        self.diff_text.delete('1.0', tk.END)

        if old_content == new_content:
            self.diff_text.insert('1.0', "[No differences - content is identical]")
            self.diff_text.configure(state='disabled')
            return

        try:
            for op, text in get_character_diff(old_content, new_content):
                tag = None if op == 'equal' else op
                self.diff_text.insert(tk.END, text, tag)
        except Exception as e:
            self.diff_text.insert('1.0', f"Error generating diff: {e}")

        self.diff_text.configure(state='disabled')

    def restore_version(self):
        selection = self.history_listbox.curselection()
        if not selection or not hasattr(self, 'snapshots'):
            return

        idx = selection[0]
        if idx >= len(self.snapshots):
            return

        snap = self.snapshots[idx]
        if not messagebox.askyesno(
            "Restore Version",
            f"Snapshot #{snap.id}을 복원할까요?\n\n"
            f"메시지: {snap.message}\n시간: {snap.timestamp}\n\n"
            "현재 저장되지 않은 내용은 사라집니다.",
        ):
            return

        self.text_editor.delete('1.0', tk.END)
        self.text_editor.insert('1.0', snap.content)
        self.last_saved_content = ""
        self.modified = True
        self.update_status()

        messagebox.showinfo(
            "Version Restored",
            f"Snapshot #{snap.id}이 에디터에 복원되었습니다.\n\n"
            "저장하려면 Save & Commit 버튼을 누르세요.",
        )

    def update_status(self):
        snapshots = self.doc.get_snapshots()
        if snapshots:
            last = snapshots[-1]
            status = f"Snapshot #{last.id}: {last.message}"
            status += " | Modified ✏️" if self.modified else " | Clean ✓"
        else:
            status = "No snapshots yet"
            if self.modified:
                status += " | Modified ✏️"
        self.status_label.configure(text=f"Status: {status}")

    # ------------------------------------------------------------------
    # Edit commit message (right-click context menu)
    # ------------------------------------------------------------------

    def show_history_context_menu(self, event):
        index = self.history_listbox.nearest(event.y)
        self.history_listbox.selection_clear(0, tk.END)
        self.history_listbox.selection_set(index)
        self.history_listbox.activate(index)
        try:
            self.history_context_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.history_context_menu.grab_release()

    def edit_commit_message(self):
        selection = self.history_listbox.curselection()
        if not selection or not hasattr(self, 'snapshots'):
            return

        idx = selection[0]
        if idx >= len(self.snapshots):
            return

        snap = self.snapshots[idx]

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

        ctk.CTkLabel(dialog, text=f"Snapshot #{snap.id}의 메시지를 수정:",
                     font=ctk.CTkFont(size=13)).pack(pady=(15, 5), padx=15)

        entry = ctk.CTkEntry(dialog, font=ctk.CTkFont(family="Consolas", size=12), height=35)
        entry.pack(fill="x", padx=15, pady=5)
        entry.insert(0, snap.message)
        entry.select_range(0, tk.END)
        entry.focus()

        def on_ok():
            new_msg = entry.get().strip()
            if new_msg and new_msg != snap.message:
                result["message"] = new_msg
            dialog.destroy()

        def on_cancel():
            dialog.destroy()

        btn_frame = ctk.CTkFrame(dialog, fg_color="transparent")
        btn_frame.pack(pady=10)
        ctk.CTkButton(btn_frame, text="확인", command=on_ok, width=100).pack(side="left", padx=5)
        ctk.CTkButton(btn_frame, text="취소", command=on_cancel, width=100,
                      fg_color="gray50", hover_color="gray40").pack(side="left", padx=5)

        entry.bind('<Return>', lambda e: on_ok())
        entry.bind('<Escape>', lambda e: on_cancel())
        dialog.wait_window()

        if result["message"]:
            snap.message = result["message"]
            self.doc.save()
            self.refresh_history()
            self.status_label.configure(text=f"✓ Snapshot #{snap.id} 메시지 수정됨")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    if len(sys.argv) > 1:
        doc_path = Path(sys.argv[1])
    else:
        doc_path = _ask_file_path()
        if doc_path is None:
            return

    if doc_path.exists():
        try:
            doc = MemitDocument.load(doc_path)
        except Exception as e:
            messagebox.showerror("파일 오류", f"파일을 열 수 없습니다:\n{e}")
            return
    else:
        doc = MemitDocument.create(doc_path)

    root = ctk.CTk()
    MemoApp(root, doc)
    root.mainloop()


if __name__ == "__main__":
    main()
