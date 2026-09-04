from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QDragEnterEvent, QDropEvent, QFont, QPainter, QPalette
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from story_builder.assemble import Arrangement, SourceFile, assemble
from story_builder.clean import prepared_sources
from story_builder.config import DEFAULT_MODEL, MODELS, load_config, save_config
from story_builder.openrouter import arrange_files

ALLOWED_SUFFIXES = {".txt", ".md", ".markdown", ".text"}


def read_text_file(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


class ArrangeWorker(QThread):
    succeeded = Signal(object, str)
    failed = Signal(str)

    def __init__(self, api_key: str, model: str, files: list[SourceFile]):
        super().__init__()
        self.api_key = api_key
        self.model = model
        self.files = files

    def run(self) -> None:
        try:
            plan = arrange_files(self.api_key, self.model, self.files)
            text = assemble(self.files, plan)
            self.succeeded.emit(plan, text)
        except Exception as exc:  # noqa: BLE001 - surface any API/IO failure in the UI
            self.failed.emit(str(exc))


class FileDropList(QListWidget):
    files_dropped = Signal(list)
    selection_changed = Signal()

    def __init__(self) -> None:
        super().__init__()
        self.setAcceptDrops(True)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setAlternatingRowColors(True)
        self.setSpacing(2)
        self.placeholder = "Drop .txt or .md files here"
        self.itemSelectionChanged.connect(self.selection_changed.emit)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        self.files_dropped.emit(paths)
        event.acceptProposedAction()

    def paintEvent(self, event) -> None:  # type: ignore[override]
        super().paintEvent(event)
        if self.count() == 0:
            canvas = QPainter(self.viewport())
            canvas.setPen(QColor("#8a7a68"))
            font = QFont(self.font())
            font.setPointSize(12)
            canvas.setFont(font)
            canvas.drawText(self.viewport().rect(), Qt.AlignmentFlag.AlignCenter, self.placeholder)
            canvas.end()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Story Builder")
        self.resize(1100, 720)
        self.setAcceptDrops(True)
        self.sources: list[SourceFile] = []
        self.worker: ArrangeWorker | None = None
        self._copy_reset = QTimer(self)
        self._copy_reset.setSingleShot(True)
        self._copy_reset.timeout.connect(self._reset_copy_label)

        saved = load_config()
        self._build_ui(saved)
        self._apply_theme()

    def _build_ui(self, saved: dict) -> None:
        root = QWidget()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel("Story Builder")
        title.setObjectName("appTitle")
        subtitle = QLabel(
            "Drop text fragments. OpenRouter orders them without rewriting. Copy the assembled story."
        )
        subtitle.setObjectName("subtitle")
        subtitle.setWordWrap(True)
        layout.addWidget(title)
        layout.addWidget(subtitle)

        settings = QFrame()
        settings.setObjectName("settingsBar")
        settings_row = QHBoxLayout(settings)
        settings_row.setContentsMargins(12, 10, 12, 10)
        settings_row.setSpacing(8)

        key_label = QLabel("OpenRouter key")
        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.EchoMode.Password)
        self.key_edit.setPlaceholderText("sk-or-...")
        self.key_edit.setText(saved.get("api_key", ""))
        self.key_edit.setClearButtonEnabled(True)

        model_label = QLabel("Model")
        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        self.model_combo.addItems(MODELS)
        model = saved.get("model") or DEFAULT_MODEL
        if model not in MODELS:
            self.model_combo.insertItem(0, model)
        self.model_combo.setCurrentText(model)

        save_btn = QPushButton("Save settings")
        save_btn.clicked.connect(self._save_settings)

        settings_row.addWidget(key_label)
        settings_row.addWidget(self.key_edit, 2)
        settings_row.addWidget(model_label)
        settings_row.addWidget(self.model_combo, 1)
        settings_row.addWidget(save_btn)
        layout.addWidget(settings)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(8)

        files_header = QLabel("Files")
        files_header.setObjectName("sectionLabel")
        left_layout.addWidget(files_header)

        self.file_list = FileDropList()
        self.file_list.files_dropped.connect(self.add_paths)
        self.file_list.selection_changed.connect(self._update_buttons)
        left_layout.addWidget(self.file_list, 1)

        file_buttons = QHBoxLayout()
        self.add_btn = QPushButton("Add files")
        self.remove_btn = QPushButton("Remove")
        self.clear_btn = QPushButton("Clear")
        self.arrange_btn = QPushButton("Arrange story")
        self.arrange_btn.setObjectName("primaryButton")
        self.add_btn.clicked.connect(self._browse_files)
        self.remove_btn.clicked.connect(self._remove_selected)
        self.clear_btn.clicked.connect(self._clear_files)
        self.arrange_btn.clicked.connect(self._arrange)
        file_buttons.addWidget(self.add_btn)
        file_buttons.addWidget(self.remove_btn)
        file_buttons.addWidget(self.clear_btn)
        file_buttons.addStretch(1)
        self.strip_markdown = QCheckBox("Remove Markdown tags")
        self.strip_markdown.setToolTip(
            "Strip Markdown, HTML, and empty lines before sending text to OpenRouter, "
            "and from the finished story."
        )
        self.strip_markdown.setChecked(bool(saved.get("strip_markdown")))
        self.strip_markdown.toggled.connect(lambda _: self._save_settings())
        left_layout.addLayout(file_buttons)
        left_layout.addWidget(self.strip_markdown)
        left_layout.addWidget(self.arrange_btn)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(8)

        story_header_row = QHBoxLayout()
        story_header = QLabel("Assembled story")
        story_header.setObjectName("sectionLabel")
        self.copy_btn = QPushButton("Copy")
        self.copy_btn.clicked.connect(self._copy_story)
        story_header_row.addWidget(story_header)
        story_header_row.addStretch(1)
        story_header_row.addWidget(self.copy_btn)
        right_layout.addLayout(story_header_row)

        self.story_view = QTextEdit()
        self.story_view.setReadOnly(True)
        self.story_view.setPlaceholderText(
            "The ordered original text will appear here after you click Arrange story."
        )
        self.story_view.setObjectName("storyView")
        right_layout.addWidget(self.story_view, 1)

        self.status_label = QLabel("Drop at least two .txt or .md files to begin.")
        self.status_label.setObjectName("statusLabel")
        self.status_label.setWordWrap(True)
        right_layout.addWidget(self.status_label)

        splitter.addWidget(left)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 2)
        splitter.setSizes([380, 720])
        layout.addWidget(splitter, 1)

        self.setCentralWidget(root)
        self._update_buttons()

        copy_shortcut = QAction(self)
        copy_shortcut.setShortcut("Ctrl+Shift+C")
        copy_shortcut.triggered.connect(self._copy_story)
        self.addAction(copy_shortcut)

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            """
            QMainWindow, QWidget {
                background: #1c1814;
                color: #f3ece3;
                font-family: "Segoe UI";
                font-size: 13px;
            }
            QLabel#appTitle {
                font-size: 26px;
                font-weight: 600;
                color: #f7efe4;
                letter-spacing: 0.4px;
            }
            QLabel#subtitle, QLabel#statusLabel {
                color: #b7a898;
            }
            QLabel#sectionLabel {
                font-size: 12px;
                font-weight: 600;
                letter-spacing: 1.2px;
                text-transform: uppercase;
                color: #c4a574;
            }
            QFrame#settingsBar {
                background: #2a241f;
                border: 1px solid #3b322b;
                border-radius: 10px;
            }
            QLineEdit, QComboBox {
                background: #161310;
                border: 1px solid #4a3f36;
                border-radius: 6px;
                padding: 6px 8px;
                color: #f3ece3;
                selection-background-color: #8b5e34;
            }
            QComboBox QAbstractItemView {
                background: #161310;
                color: #f3ece3;
                selection-background-color: #8b5e34;
            }
            QListWidget {
                background: #151210;
                border: 1px dashed #6b5a48;
                border-radius: 10px;
                padding: 6px;
                color: #f3ece3;
                alternate-background-color: #1d1814;
            }
            QListWidget::item {
                padding: 8px;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background: #8b5e34;
                color: #fff8f0;
            }
            QTextEdit#storyView {
                background: #f4ead8;
                color: #2b241c;
                border: 1px solid #d7c4a5;
                border-radius: 10px;
                padding: 14px;
                font-family: Cambria, "Times New Roman", serif;
                font-size: 15px;
                line-height: 1.45;
            }
            QPushButton {
                background: #3a312a;
                color: #f3ece3;
                border: 1px solid #56483d;
                border-radius: 6px;
                padding: 8px 12px;
            }
            QPushButton:hover { background: #4a3f36; }
            QPushButton:disabled { color: #7d7166; background: #2a241f; }
            QPushButton#primaryButton {
                background: #8b5e34;
                border: 1px solid #a07245;
                font-weight: 600;
                padding: 10px 14px;
            }
            QPushButton#primaryButton:hover { background: #a06d3d; }
            QCheckBox {
                color: #f3ece3;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 16px;
                height: 16px;
                border: 1px solid #6b5a48;
                border-radius: 3px;
                background: #161310;
            }
            QCheckBox::indicator:checked {
                background: #8b5e34;
                border-color: #a07245;
            }
            """
        )
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Window, QColor("#1c1814"))
        palette.setColor(QPalette.ColorRole.Base, QColor("#151210"))
        palette.setColor(QPalette.ColorRole.Text, QColor("#f3ece3"))
        self.setPalette(palette)

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        self.add_paths(paths)
        event.acceptProposedAction()

    def add_paths(self, paths: list[str]) -> None:
        added = 0
        skipped = 0
        existing = {source.path for source in self.sources}
        for raw in paths:
            path = Path(raw)
            if path.is_dir():
                children = [
                    str(child)
                    for child in sorted(path.rglob("*"))
                    if child.is_file() and child.suffix.lower() in ALLOWED_SUFFIXES
                ]
                self.add_paths(children)
                continue
            if not path.is_file() or path.suffix.lower() not in ALLOWED_SUFFIXES:
                skipped += 1
                continue
            resolved = str(path.resolve())
            if resolved in existing:
                continue
            try:
                text = read_text_file(path)
            except OSError as exc:
                self._set_status(f"Could not read {path.name}: {exc}")
                continue
            self.sources.append(SourceFile(path=resolved, name=path.name, text=text))
            existing.add(resolved)
            item = QListWidgetItem(path.name)
            item.setToolTip(resolved)
            item.setData(Qt.ItemDataRole.UserRole, resolved)
            self.file_list.addItem(item)
            added += 1

        if added:
            self._set_status(f"Added {added} file{'s' if added != 1 else ''}. {len(self.sources)} ready.")
        elif skipped and not added:
            self._set_status("Only .txt and .md files are accepted.")
        self._update_buttons()

    def _browse_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "Add text files",
            "",
            "Text files (*.txt *.md *.markdown *.text);;All files (*.*)",
        )
        if paths:
            self.add_paths(paths)

    def _remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.file_list.selectedIndexes()}, reverse=True)
        for row in rows:
            self.file_list.takeItem(row)
            del self.sources[row]
        self._update_buttons()
        self._set_status(f"{len(self.sources)} file{'s' if len(self.sources) != 1 else ''} remaining.")

    def _clear_files(self) -> None:
        self.file_list.clear()
        self.sources.clear()
        self.story_view.clear()
        self._update_buttons()
        self._set_status("File list cleared.")

    def _save_settings(self) -> None:
        save_config(
            self.key_edit.text(),
            self.model_combo.currentText(),
            self.strip_markdown.isChecked(),
        )
        self._set_status("Settings saved.")

    def _arrange(self) -> None:
        if not self.sources:
            QMessageBox.information(self, "Need files", "Drop at least one .txt or .md file.")
            return
        sources = prepared_sources(self.sources, self.strip_markdown.isChecked())
        if len(sources) == 1:
            text = sources[0].text.strip()
            self.story_view.setPlainText(text)
            self._set_status("Only one file, so it was used as-is.")
            self._update_buttons()
            return
        if not self.key_edit.text().strip():
            QMessageBox.information(
                self,
                "API key needed",
                "Paste an OpenRouter API key, then click Arrange story.",
            )
            return
        if self.worker and self.worker.isRunning():
            return

        save_config(
            self.key_edit.text(),
            self.model_combo.currentText(),
            self.strip_markdown.isChecked(),
        )
        self.arrange_btn.setEnabled(False)
        self._set_status("Asking OpenRouter to find the reading order…")
        self.worker = ArrangeWorker(
            self.key_edit.text().strip(),
            self.model_combo.currentText().strip() or DEFAULT_MODEL,
            sources,
        )
        self.worker.succeeded.connect(self._on_arranged)
        self.worker.failed.connect(self._on_arrange_failed)
        self.worker.finished.connect(lambda: self.arrange_btn.setEnabled(True))
        self.worker.start()

    def _on_arranged(self, plan: Arrangement, text: str) -> None:
        ordered = [self.sources[i] for i in plan.order]
        self.sources = ordered
        self.file_list.clear()
        for source in self.sources:
            item = QListWidgetItem(source.name)
            item.setToolTip(source.path)
            item.setData(Qt.ItemDataRole.UserRole, source.path)
            self.file_list.addItem(item)
        self.story_view.setPlainText(text)
        sequence = " → ".join(source.name for source in self.sources)
        note = f" {plan.notes}" if plan.notes else ""
        self._set_status(f"Reading order: {sequence}.{note}")
        self._update_buttons()

    def _on_arrange_failed(self, message: str) -> None:
        self._set_status(message)
        QMessageBox.warning(self, "Could not arrange files", message)

    def _copy_story(self) -> None:
        text = self.story_view.toPlainText()
        if not text.strip():
            self._set_status("Nothing to copy yet.")
            return
        QApplication.clipboard().setText(text)
        self.copy_btn.setText("Copied")
        self._copy_reset.start(1600)

    def _reset_copy_label(self) -> None:
        self.copy_btn.setText("Copy")

    def _set_status(self, message: str) -> None:
        self.status_label.setText(message)

    def _update_buttons(self) -> None:
        if not hasattr(self, "copy_btn"):
            return
        has_files = bool(self.sources)
        self.remove_btn.setEnabled(bool(self.file_list.selectedItems()))
        self.clear_btn.setEnabled(has_files)
        busy = bool(self.worker and self.worker.isRunning())
        self.arrange_btn.setEnabled(has_files and not busy)
        self.copy_btn.setEnabled(bool(self.story_view.toPlainText().strip()))


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Story Builder")
    window = MainWindow()
    window.show()
    return app.exec()
