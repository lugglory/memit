#!/usr/bin/env python3
"""
Memit Memo App - Single-file .memit document editor with version history.

Run with a .memit file path to open it directly:
    python memo_app.py notes.memit

Run without arguments to show the Open/New file dialog.
"""

import sys
from pathlib import Path
from datetime import datetime
from typing import List, Optional

from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QSplitter, QTextEdit, QListWidget, QListWidgetItem, QPushButton,
    QLabel, QCheckBox, QDialog, QLineEdit, QDialogButtonBox,
    QFileDialog, QMessageBox, QFrame, QMenu,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import (
    QFont, QColor, QTextCharFormat, QKeySequence, QAction, QTextCursor,
)

from memit.document import MemitDocument, MemitSnapshot
from memit.amend_check import check_amend_safe
from memit.diff_engine import get_character_diff


# ---------------------------------------------------------------------------
# Dark theme
# ---------------------------------------------------------------------------

_DARK_BG    = "#1e1e1e"
_PANEL_BG   = "#252526"
_WIDGET_BG  = "#2b2b2b"
_TEXT_FG    = "#d4d4d4"
_ACCENT     = "#1f538d"
_BORDER     = "#3e3e42"

_STYLESHEET = f"""
QMainWindow, QWidget {{
    background-color: {_DARK_BG};
    color: {_TEXT_FG};
}}
QTextEdit {{
    background-color: {_DARK_BG};
    color: {_TEXT_FG};
    border: 1px solid {_BORDER};
    selection-background-color: {_ACCENT};
    selection-color: #ffffff;
}}
QListWidget {{
    background-color: {_WIDGET_BG};
    color: {_TEXT_FG};
    border: 1px solid {_BORDER};
    outline: none;
}}
QListWidget::item {{
    padding: 3px 6px;
}}
QListWidget::item:selected {{
    background-color: {_ACCENT};
    color: #ffffff;
}}
QPushButton {{
    background-color: #3a3d41;
    color: {_TEXT_FG};
    border: 1px solid {_BORDER};
    padding: 5px 14px;
    border-radius: 4px;
    min-height: 28px;
}}
QPushButton:hover {{
    background-color: #4a4d51;
}}
QPushButton:pressed {{
    background-color: {_ACCENT};
}}
QPushButton:disabled {{
    color: #555;
    background-color: #2a2a2a;
    border-color: #333;
}}
QLabel {{
    color: {_TEXT_FG};
    background: transparent;
}}
QCheckBox {{
    color: {_TEXT_FG};
    spacing: 6px;
}}
QCheckBox::indicator {{
    width: 14px;
    height: 14px;
    border: 1px solid {_BORDER};
    background: {_WIDGET_BG};
    border-radius: 2px;
}}
QCheckBox::indicator:checked {{
    background: {_ACCENT};
}}
QLineEdit {{
    background-color: {_WIDGET_BG};
    color: {_TEXT_FG};
    border: 1px solid {_BORDER};
    padding: 5px 8px;
    border-radius: 3px;
    selection-background-color: {_ACCENT};
}}
QSplitter::handle {{
    background-color: {_BORDER};
    width: 2px;
    height: 2px;
}}
QScrollBar:vertical {{
    background: {_WIDGET_BG};
    width: 12px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: #5a5a5a;
    border-radius: 6px;
    min-height: 24px;
    margin: 2px;
}}
QScrollBar::handle:vertical:hover {{
    background: #7a7a7a;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    background: {_WIDGET_BG};
    height: 12px;
    margin: 0;
}}
QScrollBar::handle:horizontal {{
    background: #5a5a5a;
    border-radius: 6px;
    min-width: 24px;
    margin: 2px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0;
}}
QMenu {{
    background-color: {_PANEL_BG};
    color: {_TEXT_FG};
    border: 1px solid {_BORDER};
    padding: 4px 0;
}}
QMenu::item {{
    padding: 5px 20px;
}}
QMenu::item:selected {{
    background-color: {_ACCENT};
}}
QFrame[frameShape="4"],
QFrame[frameShape="5"] {{
    color: {_BORDER};
}}
QDialog {{
    background-color: {_PANEL_BG};
}}
QDialogButtonBox QPushButton {{
    min-width: 80px;
}}
"""


# ---------------------------------------------------------------------------
# Startup file chooser
# ---------------------------------------------------------------------------

class _FileChooserDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Memit Memo")
        self.setFixedSize(320, 130)
        self.result_path: Optional[Path] = None

        layout = QVBoxLayout(self)
        layout.setSpacing(12)

        label = QLabel("메모 파일을 선택하세요")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        label.setStyleSheet("font-size: 12px; padding-top: 8px;")
        layout.addWidget(label)

        btn_layout = QHBoxLayout()
        open_btn = QPushButton("파일 열기")
        new_btn  = QPushButton("새로 만들기")
        btn_layout.addWidget(open_btn)
        btn_layout.addWidget(new_btn)
        layout.addLayout(btn_layout)

        open_btn.clicked.connect(self._open_file)
        new_btn.clicked.connect(self._new_file)

    def _open_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "메모 파일 열기", "",
            "Memit 파일 (*.memit);;모든 파일 (*.*)",
        )
        if path:
            self.result_path = Path(path)
        self.accept()

    def _new_file(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "새 메모 파일 만들기", "",
            "Memit 파일 (*.memit)",
        )
        if path:
            self.result_path = Path(path)
        self.accept()


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class MemoApp(QMainWindow):
    def __init__(self, doc: MemitDocument):
        super().__init__()
        self.doc = doc
        self.modified = False
        self.last_saved_content = ""
        self.snapshots: List[MemitSnapshot] = []

        self.setWindowTitle(f"{doc.path.name} - Memit Memo")

        screen = QApplication.primaryScreen().availableGeometry()
        w = int(screen.width() * 0.75)
        h = int(screen.height() * 0.75)
        self.resize(w, h)
        self.move(screen.x() + (screen.width() - w) // 2,
                  screen.y() + (screen.height() - h) // 2)

        self._setup_ui()
        self._setup_shortcuts()
        self.load_content()
        self.refresh_history()
        self.update_status()

    # ------------------------------------------------------------------
    # UI setup
    # ------------------------------------------------------------------

    def _setup_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(6)

        self.status_label = QLabel("Status: No snapshots yet")
        self.status_label.setStyleSheet(
            f"background: {_PANEL_BG}; padding: 5px 10px; "
            f"border: 1px solid {_BORDER}; border-radius: 4px;"
        )
        root.addWidget(self.status_label)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(self._make_editor_panel())
        splitter.addWidget(self._make_history_panel())
        splitter.setStretchFactor(0, 6)
        splitter.setStretchFactor(1, 4)
        root.addWidget(splitter, 1)

    def _make_editor_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 4, 0)
        layout.setSpacing(6)

        title = QLabel("MEMO EDITOR")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("font-weight: bold; font-size: 13px; padding: 4px;")
        layout.addWidget(title)

        self.text_editor = QTextEdit()
        self.text_editor.setFont(QFont("Malgun Gothic", 14))
        self.text_editor.setAcceptRichText(False)
        self.text_editor.textChanged.connect(self.on_text_modified)
        layout.addWidget(self.text_editor, 1)

        controls = QWidget()
        ctrl = QHBoxLayout(controls)
        ctrl.setContentsMargins(0, 0, 0, 0)
        ctrl.setSpacing(8)

        self.save_btn = QPushButton("💾 Save (Ctrl+S)")
        self.save_btn.setStyleSheet("font-weight: bold;")
        self.save_btn.clicked.connect(self.save_and_commit)
        ctrl.addWidget(self.save_btn)

        self.use_custom_msg = QCheckBox("커밋 메시지 직접 입력")
        ctrl.addWidget(self.use_custom_msg)
        ctrl.addStretch()

        export_btn = QPushButton("TXT 저장")
        export_btn.clicked.connect(self.export_txt)
        ctrl.addWidget(export_btn)

        copy_btn = QPushButton("클립보드 복사")
        copy_btn.clicked.connect(self.copy_to_clipboard)
        ctrl.addWidget(copy_btn)

        layout.addWidget(controls)
        return widget

    def _make_history_panel(self) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(4, 0, 0, 0)
        layout.setSpacing(6)

        history_title = QLabel("HISTORY")
        history_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        history_title.setStyleSheet("font-weight: bold; font-size: 13px; padding: 4px;")
        layout.addWidget(history_title)

        self.history_list = QListWidget()
        self.history_list.setFont(QFont("Malgun Gothic", 10))
        self.history_list.currentRowChanged.connect(self.on_history_select)
        self.history_list.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu
        )
        self.history_list.customContextMenuRequested.connect(
            self.show_history_context_menu
        )
        layout.addWidget(self.history_list, 4)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"color: {_BORDER};")
        layout.addWidget(sep)

        diff_title = QLabel("DIFF PREVIEW")
        diff_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        diff_title.setStyleSheet("font-weight: bold; font-size: 13px; padding: 4px;")
        layout.addWidget(diff_title)

        self.diff_text = QTextEdit()
        self.diff_text.setFont(QFont("Malgun Gothic", 10))
        self.diff_text.setReadOnly(True)
        layout.addWidget(self.diff_text, 6)

        self.restore_btn = QPushButton("↻ Restore Selected Version")
        self.restore_btn.setEnabled(False)
        self.restore_btn.clicked.connect(self.restore_version)
        layout.addWidget(self.restore_btn)

        return widget

    def _setup_shortcuts(self):
        save_action = QAction(self)
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self.save_and_commit)
        self.addAction(save_action)

    # ------------------------------------------------------------------
    # Core operations
    # ------------------------------------------------------------------

    def _auto_message(self, old_content: str, new_content: str) -> str:
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

    def on_text_modified(self):
        current = self.text_editor.toPlainText()
        if current != self.last_saved_content:
            self.modified = True
            self.update_status()

    def load_content(self):
        content = self.doc.get_content()
        self.text_editor.blockSignals(True)
        self.text_editor.setPlainText(content)
        self.text_editor.blockSignals(False)
        self.last_saved_content = content
        self.modified = False

    def save_and_commit(self):
        new_content = self.text_editor.toPlainText()

        if self.use_custom_msg.isChecked():
            message = self._ask_commit_message()
            if message is None:
                return
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
            QMessageBox.critical(self, "Commit Error", f"Failed to commit: {e}")
            return

        if success:
            self.last_saved_content = new_content
            self.modified = False
            prefix = "✓ Amended" if "Amended" in result_msg else "✓ Saved"
            self.status_label.setText(f"{prefix}: {result_msg}")
            self.refresh_history()
            self.update_status()
        else:
            self.status_label.setText(f"ℹ {result_msg}")

    def copy_to_clipboard(self):
        QApplication.clipboard().setText(self.text_editor.toPlainText())
        self.status_label.setText("✓ 클립보드에 복사됨")

    def export_txt(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "TXT로 저장", "",
            "텍스트 파일 (*.txt);;모든 파일 (*.*)",
        )
        if not path:
            return
        try:
            self.doc.export_txt(Path(path))
            self.status_label.setText(f"✓ TXT 저장됨: {Path(path).name}")
        except Exception as e:
            QMessageBox.critical(self, "저장 오류", f"파일 저장 실패: {e}")

    # ------------------------------------------------------------------
    # Commit message dialog
    # ------------------------------------------------------------------

    def _ask_commit_message(self, initial: str = "") -> Optional[str]:
        dialog = QDialog(self)
        dialog.setWindowTitle("커밋 메시지 입력")
        dialog.setFixedSize(450, 140)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(8)
        layout.addWidget(QLabel("커밋 메시지를 입력하세요:"))

        entry = QLineEdit(initial)
        entry.setFont(QFont("Malgun Gothic", 12))
        layout.addWidget(entry)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        entry.setFocus()
        entry.returnPressed.connect(dialog.accept)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None

        msg = entry.text().strip()
        return msg if msg else str(len(self.doc.get_snapshots()) + 1)

    # ------------------------------------------------------------------
    # History panel
    # ------------------------------------------------------------------

    def refresh_history(self):
        self.history_list.clear()
        snapshots = list(reversed(self.doc.get_snapshots()))
        self.snapshots = snapshots

        if not snapshots:
            self.history_list.addItem("No snapshots yet")
            return

        for i, snap in enumerate(snapshots):
            try:
                dt = datetime.fromisoformat(snap.timestamp)
                time_str = dt.strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                time_str = snap.timestamp

            item = QListWidgetItem(f"#{snap.id}: {snap.message} - {time_str}")
            change_type = self._change_type(snap, i, snapshots)
            bg = {
                'insert': '#1a3d1a',
                'delete': '#3d1a1a',
                'mixed':  '#1a2d3d',
            }.get(change_type)
            if bg:
                item.setBackground(QColor(bg))
            self.history_list.addItem(item)

    def _change_type(self, snap: MemitSnapshot, index: int,
                     snapshots: List[MemitSnapshot]) -> str:
        if index >= len(snapshots) - 1:
            return 'insert'
        prev = snapshots[index + 1]
        if not prev.content and snap.content:
            return 'insert'
        if prev.content and not snap.content:
            return 'delete'
        try:
            diff_ops = get_character_diff(prev.content, snap.content)
            has_ins = any(op == 'insert' for op, _ in diff_ops)
            has_del = any(op == 'delete' for op, _ in diff_ops)
            if has_ins and has_del:
                return 'mixed'
            return 'insert' if has_ins else ('delete' if has_del else 'mixed')
        except Exception:
            return 'mixed'

    def on_history_select(self, row: int):
        if row < 0 or row >= len(self.snapshots):
            self.restore_btn.setEnabled(False)
            return
        self.restore_btn.setEnabled(True)
        snap = self.snapshots[row]
        old_content = self.snapshots[row + 1].content if row + 1 < len(self.snapshots) else ''
        self.show_diff(old_content, snap.content)

    def show_diff(self, old_content: str, new_content: str):
        self.diff_text.clear()
        if old_content == new_content:
            self.diff_text.setPlainText("[No differences - content is identical]")
            return
        cursor = QTextCursor(self.diff_text.document())
        try:
            for op, text in get_character_diff(old_content, new_content):
                fmt = QTextCharFormat()
                if op == 'insert':
                    fmt.setForeground(QColor('#69db7c'))
                    fmt.setBackground(QColor('#1a3d1a'))
                elif op == 'delete':
                    fmt.setForeground(QColor('#ff6b6b'))
                    fmt.setBackground(QColor('#3d1a1a'))
                else:
                    fmt.setForeground(QColor(_TEXT_FG))
                cursor.insertText(text, fmt)
        except Exception as e:
            self.diff_text.setPlainText(f"Error generating diff: {e}")

    def restore_version(self):
        row = self.history_list.currentRow()
        if row < 0 or row >= len(self.snapshots):
            return
        snap = self.snapshots[row]
        reply = QMessageBox.question(
            self, "Restore Version",
            f"Snapshot #{snap.id}을 복원할까요?\n\n"
            f"메시지: {snap.message}\n시간: {snap.timestamp}\n\n"
            "현재 저장되지 않은 내용은 사라집니다.",
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        self.text_editor.blockSignals(True)
        self.text_editor.setPlainText(snap.content)
        self.text_editor.blockSignals(False)
        self.last_saved_content = ""
        self.modified = True
        self.update_status()
        QMessageBox.information(
            self, "Version Restored",
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
        self.status_label.setText(f"Status: {status}")

    # ------------------------------------------------------------------
    # Context menu / edit commit message
    # ------------------------------------------------------------------

    def show_history_context_menu(self, pos):
        row = self.history_list.currentRow()
        if row < 0 or row >= len(self.snapshots):
            return
        menu = QMenu(self)
        edit_action = menu.addAction("커밋 메시지 수정")
        action = menu.exec(self.history_list.mapToGlobal(pos))
        if action == edit_action:
            self._edit_commit_message(row)

    def _edit_commit_message(self, row: int):
        if row >= len(self.snapshots):
            return
        snap = self.snapshots[row]

        dialog = QDialog(self)
        dialog.setWindowTitle("커밋 메시지 수정")
        dialog.setFixedSize(450, 140)

        layout = QVBoxLayout(dialog)
        layout.setSpacing(8)
        layout.addWidget(QLabel(f"Snapshot #{snap.id}의 메시지를 수정:"))

        entry = QLineEdit(snap.message)
        entry.setFont(QFont("Malgun Gothic", 12))
        entry.selectAll()
        layout.addWidget(entry)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        entry.setFocus()
        entry.returnPressed.connect(dialog.accept)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        new_msg = entry.text().strip()
        if new_msg and new_msg != snap.message:
            snap.message = new_msg
            self.doc.save()
            self.refresh_history()
            self.status_label.setText(f"✓ Snapshot #{snap.id} 메시지 수정됨")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def _ask_file_path() -> Optional[Path]:
    dialog = _FileChooserDialog()
    dialog.exec()
    return dialog.result_path


def main():
    app = QApplication(sys.argv)
    app.setStyleSheet(_STYLESHEET)

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
            QMessageBox.critical(None, "파일 오류", f"파일을 열 수 없습니다:\n{e}")
            return
    else:
        doc = MemitDocument.create(doc_path)

    window = MemoApp(doc)
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
