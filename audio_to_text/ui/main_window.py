from __future__ import annotations

import threading
import tkinter as tk
from pathlib import Path
from queue import Empty, Queue
from tkinter import filedialog, ttk

from audio_to_text.downloader.http_downloader import HttpDownloader
from audio_to_text.errors.app_errors import ConfigurationError, InputValidationError, OutputError
from audio_to_text.input_sources.folder_source import FolderSource
from audio_to_text.input_sources.url_source import UrlListSource
from audio_to_text.models.job import BatchJobItem, ExistingFilePolicy, ProcessingMode
from audio_to_text.models.result import BatchItemResult
from audio_to_text.models.status import ItemStatus
from audio_to_text.output.naming import sanitize_filename
from audio_to_text.output.reporting import BatchLogger, BatchReportWriter, ReportItem
from audio_to_text.output.writer import TranscriptWriter
from audio_to_text.settings.manager import SettingsManager
from audio_to_text.settings.schema import AppSettings
from audio_to_text.transcription.backend import FasterWhisperBackend
from audio_to_text.transcription.environment import EnvironmentChecker, EnvironmentReport
from audio_to_text.transcription.worker import BatchProcessor
from audio_to_text.ui.dialogs import show_error, show_info
from audio_to_text.ui.status_table import StatusTable


LANGUAGE_OPTIONS = {
    "Auto detect": "auto",
    "Russian": "ru",
    "English": "en",
}

STATUS_LABELS = {
    ItemStatus.QUEUED: "В очереди",
    ItemStatus.DOWNLOADING: "Скачивание",
    ItemStatus.PROCESSING: "Распознавание",
    ItemStatus.SAVING: "Сохранение",
    ItemStatus.DONE: "Готово",
    ItemStatus.SKIPPED: "Пропущено",
    ItemStatus.CANCELLED: "Отменено",
    ItemStatus.ERROR: "Ошибка",
}


class MainWindow:
    def __init__(
        self,
        root: tk.Tk,
        settings_manager: SettingsManager,
        initial_settings: AppSettings,
        environment_checker: EnvironmentChecker,
    ) -> None:
        self.root = root
        self.settings_manager = settings_manager
        self.settings = initial_settings
        self.environment_checker = environment_checker

        self.url_source = UrlListSource()
        self.folder_source = FolderSource()
        self.event_queue: Queue = Queue()
        self.processor_thread: threading.Thread | None = None
        self.cancel_event = threading.Event()
        self.processing = False
        self.items_by_id: dict[str, BatchJobItem] = {}
        self.current_log_path: Path | None = None
        self.current_report_path: Path | None = None

        self.mode_var = tk.StringVar(value=ProcessingMode.URL_LIST.value)
        self.language_var = tk.StringVar(value=self._label_for_language(self.settings.default_language))
        self.input_folder_var = tk.StringVar(value=self.settings.input_folder)
        self.output_folder_var = tk.StringVar(value=self.settings.output_folder)
        self.recursive_var = tk.BooleanVar(value=self.settings.recursive)
        self.status_var = tk.StringVar(value="Проверьте настройки и нажмите Запуск.")
        self.policy_var = tk.StringVar(value=self.settings.existing_file_policy)
        self.environment_var = tk.StringVar()
        self.summary_var = tk.StringVar(value="Нет активной обработки.")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_text_var = tk.StringVar(value="Прогресс: 0%")

        self._build_ui()
        self._bind_settings_persistence()
        self._refresh_mode()
        self._run_environment_check()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(150, self._poll_events)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(2, weight=1)

        top = ttk.Frame(self.root, padding=12)
        top.grid(row=0, column=0, sticky="nsew")
        top.columnconfigure(1, weight=1)
        top.columnconfigure(3, weight=1)

        ttk.Label(top, text="Режим").grid(row=0, column=0, sticky="w")
        mode_box = ttk.Combobox(
            top,
            textvariable=self.mode_var,
            values=[ProcessingMode.URL_LIST.value, ProcessingMode.FOLDER.value, ProcessingMode.SINGLE_FILE.value],
            state="readonly",
            width=18,
        )
        mode_box.grid(row=0, column=1, sticky="w", padx=(6, 16))
        mode_box.bind("<<ComboboxSelected>>", lambda _event: self._refresh_mode())

        ttk.Label(top, text="Язык").grid(row=0, column=2, sticky="w")
        language_box = ttk.Combobox(
            top,
            textvariable=self.language_var,
            values=list(LANGUAGE_OPTIONS.keys()),
            state="readonly",
            width=18,
        )
        language_box.grid(row=0, column=3, sticky="w")

        self.input_path_label = ttk.Label(top, text="Папка с аудио")
        self.input_path_label.grid(row=1, column=0, sticky="w", pady=(10, 0))
        self.input_folder_entry = ttk.Entry(top, textvariable=self.input_folder_var)
        self.input_folder_entry.grid(row=1, column=1, columnspan=2, sticky="ew", pady=(10, 0), padx=(6, 6))
        self.input_folder_button = ttk.Button(top, text="Выбрать", command=self._choose_input_folder)
        self.input_folder_button.grid(row=1, column=3, sticky="w", pady=(10, 0))

        ttk.Label(top, text="Папка результатов").grid(row=2, column=0, sticky="w", pady=(10, 0))
        self.output_folder_entry = ttk.Entry(top, textvariable=self.output_folder_var)
        self.output_folder_entry.grid(
            row=2, column=1, columnspan=2, sticky="ew", pady=(10, 0), padx=(6, 6)
        )
        ttk.Button(top, text="Выбрать", command=self._choose_output_folder).grid(row=2, column=3, sticky="w", pady=(10, 0))

        self.recursive_checkbutton = ttk.Checkbutton(
            top,
            text="Обрабатывать вложенные папки",
            variable=self.recursive_var,
            command=self._on_recursive_changed,
        )
        self.recursive_checkbutton.grid(
            row=3, column=1, sticky="w", pady=(10, 0)
        )
        ttk.Label(top, text="Если .txt уже существует").grid(row=3, column=2, sticky="w", pady=(10, 0))
        self.policy_box = ttk.Combobox(
            top,
            textvariable=self.policy_var,
            values=[policy.value for policy in ExistingFilePolicy],
            state="readonly",
            width=12,
        )
        self.policy_box.grid(row=3, column=3, sticky="w", pady=(10, 0))
        self.language_box = language_box
        self.mode_box = mode_box

        self.url_frame = ttk.LabelFrame(self.root, text="Список URL", padding=12)
        self.url_frame.grid(row=1, column=0, sticky="nsew", padx=12)
        self.url_frame.columnconfigure(0, weight=1)
        self.url_frame.rowconfigure(0, weight=1)
        self.url_text = tk.Text(self.url_frame, height=8, wrap="word")
        self.url_text.grid(row=0, column=0, sticky="nsew")
        url_buttons = ttk.Frame(self.url_frame)
        url_buttons.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(url_buttons, text="Загрузить список из .txt", command=self._load_url_file).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(url_buttons, text="Очистить URL", command=lambda: self.url_text.delete("1.0", tk.END)).grid(
            row=0, column=1, sticky="w", padx=(8, 0)
        )

        center = ttk.Panedwindow(self.root, orient=tk.HORIZONTAL)
        center.grid(row=2, column=0, sticky="nsew", padx=12, pady=12)

        left = ttk.Frame(center)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(0, weight=1)
        self.status_table = StatusTable(left)
        self.status_table.grid(row=0, column=0, sticky="nsew")
        self.status_table.bind("<<TreeviewSelect>>", self._on_select_item)
        scroll = ttk.Scrollbar(left, orient="vertical", command=self.status_table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.status_table.configure(yscrollcommand=scroll.set)
        center.add(left, weight=3)

        right = ttk.Frame(center, padding=(12, 0, 0, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        ttk.Label(right, text="Результат выбранного элемента").grid(row=0, column=0, sticky="w")
        ttk.Label(right, textvariable=self.summary_var, foreground="#444").grid(row=1, column=0, sticky="w", pady=(4, 0))
        self.result_text = tk.Text(right, wrap="word")
        self.result_text.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        center.add(right, weight=2)

        bottom = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        bottom.grid(row=3, column=0, sticky="ew")
        bottom.columnconfigure(0, weight=1)
        ttk.Label(bottom, textvariable=self.environment_var, foreground="#444").grid(row=0, column=0, sticky="w")
        ttk.Label(bottom, textvariable=self.status_var).grid(row=1, column=0, sticky="w", pady=(6, 0))
        progress_frame = ttk.Frame(bottom)
        progress_frame.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        progress_frame.columnconfigure(0, weight=1)
        self.progress_bar = ttk.Progressbar(
            progress_frame,
            variable=self.progress_var,
            maximum=100,
            mode="determinate",
        )
        self.progress_bar.grid(row=0, column=0, sticky="ew")
        ttk.Label(progress_frame, textvariable=self.progress_text_var, width=18).grid(row=0, column=1, sticky="e", padx=(10, 0))
        self.paths_label = ttk.Label(bottom, text="", foreground="#444")
        self.paths_label.grid(row=3, column=0, sticky="w", pady=(6, 0))
        buttons = ttk.Frame(bottom)
        buttons.grid(row=1, column=1, rowspan=3, sticky="e")
        self.start_button = ttk.Button(buttons, text="Запуск", command=self._start_processing)
        self.start_button.grid(row=0, column=0, padx=(0, 6))
        self.cancel_button = ttk.Button(buttons, text="Отмена", command=self._cancel_processing, state="disabled")
        self.cancel_button.grid(row=0, column=1, padx=6)
        ttk.Button(buttons, text="Сохранить текст", command=self._save_selected_text).grid(row=0, column=2, padx=6)
        ttk.Button(buttons, text="Копировать текст", command=self._copy_selected_text).grid(row=0, column=3, padx=6)
        ttk.Button(buttons, text="Сохранить все", command=self._save_all_results).grid(row=0, column=4, padx=6)
        ttk.Button(buttons, text="Очистить", command=self._clear_all).grid(row=0, column=5, padx=(6, 0))

    def _refresh_mode(self) -> None:
        is_url = self.mode_var.get() == ProcessingMode.URL_LIST.value
        is_folder = self.mode_var.get() == ProcessingMode.FOLDER.value
        is_file = self.mode_var.get() == ProcessingMode.SINGLE_FILE.value
        if is_url:
            self.url_frame.grid()
        else:
            self.url_frame.grid_remove()
        state = "normal" if is_folder or is_file else "disabled"
        self.input_folder_entry.configure(state=state)
        self.input_folder_button.configure(state="normal" if is_folder or is_file else "disabled")
        self.input_path_label.configure(text="Файл с аудио" if is_file else "Папка с аудио")
        self._refresh_input_preview()

    def _bind_settings_persistence(self) -> None:
        self.input_folder_entry.bind("<FocusOut>", self._persist_settings_event)
        self.input_folder_entry.bind("<Return>", self._persist_settings_event)
        self.output_folder_entry.bind("<FocusOut>", self._persist_settings_event)
        self.output_folder_entry.bind("<Return>", self._persist_settings_event)
        self.language_box.bind("<<ComboboxSelected>>", self._persist_settings_event)
        self.policy_box.bind("<<ComboboxSelected>>", self._persist_settings_event)
        self.mode_box.bind("<<ComboboxSelected>>", self._persist_settings_event, add="+")

    def _run_environment_check(self) -> None:
        report = self.environment_checker.check(self._collect_settings())
        self._apply_environment_report(report)

    def _apply_environment_report(self, report: EnvironmentReport) -> None:
        parts = [f"Backend: {report.backend_name}", f"Модель: {report.model_name}"]
        if report.issues:
            parts.append("Проблемы: " + " | ".join(report.issues))
        elif report.warnings:
            parts.append("Предупреждения: " + " | ".join(report.warnings))
        else:
            parts.append(report.summary)
        self.environment_var.set("   ".join(parts))
        self.start_button.configure(state="normal" if report.ready and not self.processing else "disabled")

    def _collect_settings(self) -> AppSettings:
        return AppSettings(
            input_folder=self.input_folder_var.get().strip(),
            output_folder=self.output_folder_var.get().strip(),
            default_language=LANGUAGE_OPTIONS[self.language_var.get()],
            recursive=self.recursive_var.get(),
            existing_file_policy=self.policy_var.get(),
        )

    def _persist_settings(self) -> bool:
        self.settings = self._collect_settings()
        try:
            self.settings_manager.save(self.settings)
        except ConfigurationError as exc:
            show_error("Ошибка настроек", str(exc))
            return False
        self._run_environment_check()
        return True

    def _persist_settings_event(self, _event: tk.Event | None = None) -> None:
        self._persist_settings()
        self._refresh_input_preview()

    def _on_close(self) -> None:
        self._persist_settings()
        self.root.destroy()

    def _on_recursive_changed(self) -> None:
        self._persist_settings()
        self._refresh_input_preview()

    def _choose_input_folder(self) -> None:
        if self.mode_var.get() == ProcessingMode.SINGLE_FILE.value:
            selected = filedialog.askopenfilename(
                title="Выберите аудиофайл",
                filetypes=[
                    ("Audio files", "*.mp3 *.wav *.m4a *.mp4 *.ogg *.flac *.webm"),
                    ("All files", "*.*"),
                ],
            )
        else:
            selected = filedialog.askdirectory(title="Выберите папку с аудио")
        if selected:
            self.input_folder_var.set(selected)
            self._persist_settings()
            self._refresh_input_preview()

    def _choose_output_folder(self) -> None:
        selected = filedialog.askdirectory(title="Выберите папку результатов")
        if selected:
            self.output_folder_var.set(selected)
            self._persist_settings()

    def _load_url_file(self) -> None:
        selected = filedialog.askopenfilename(
            title="Выберите .txt со списком URL",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if not selected:
            return
        try:
            text = self.url_source.load_from_file(Path(selected))
        except InputValidationError as exc:
            show_error("Ошибка URL", str(exc))
            return
        self.url_text.delete("1.0", tk.END)
        self.url_text.insert("1.0", text)

    def _start_processing(self) -> None:
        if self.processing:
            return
        if not self._persist_settings():
            return
        report = self.environment_checker.check(self.settings)
        self._apply_environment_report(report)
        if not report.ready:
            show_error("Окружение не готово", "\n".join(report.issues))
            return

        try:
            items = self._build_items()
        except InputValidationError as exc:
            show_error("Ошибка ввода", str(exc))
            return

        output_dir = self.settings.output_folder_path
        if output_dir is None:
            show_error("Ошибка настроек", "Укажите папку для сохранения результатов.")
            return

        self.processing = True
        self.cancel_event.clear()
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.status_var.set("Обработка запущена.")
        self.summary_var.set(f"Подготовлено элементов: {len(items)}")
        self._set_progress(0, len(items))
        self.result_text.delete("1.0", tk.END)
        self._load_items_into_table(items)

        processor = BatchProcessor(
            backend=FasterWhisperBackend(model_name="small", compute_type="int8"),
            downloader=HttpDownloader(),
            writer=TranscriptWriter(),
            logger=self._start_batch_logger(output_dir),
        )
        language = self.settings.default_language
        self.current_report_path = None
        self.processor_thread = threading.Thread(
            target=processor.process,
            kwargs={
                "items": items,
                "output_dir": output_dir,
                "language": language,
                "existing_file_policy": self.settings.existing_file_policy,
                "event_queue": self.event_queue,
                "cancel_event": self.cancel_event,
            },
            daemon=True,
        )
        self.processor_thread.start()

    def _cancel_processing(self) -> None:
        if not self.processing:
            return
        self.cancel_event.set()
        self.cancel_button.configure(state="disabled")
        self.status_var.set("Запрошена отмена. Текущий шаг завершится и пакет остановится.")

    def _build_items(self) -> list[BatchJobItem]:
        mode = self.mode_var.get()
        if mode == ProcessingMode.URL_LIST.value:
            return self.url_source.build_items(self.url_text.get("1.0", tk.END))
        if mode == ProcessingMode.FOLDER.value:
            return self.folder_source.build_items(self.input_folder_var.get(), self.recursive_var.get())
        if mode == ProcessingMode.SINGLE_FILE.value:
            path = self.input_folder_var.get().strip()
            if not path:
                raise InputValidationError("Файл не указан.")
            file_path = Path(path)
            if not file_path.exists() or not file_path.is_file():
                raise InputValidationError("Указанный файл не существует.")
            if file_path.suffix.lower() not in {".mp3", ".wav", ".m4a", ".mp4", ".ogg", ".flac", ".webm"}:
                raise InputValidationError("Формат выбранного файла не поддерживается.")
            return [
                BatchJobItem(
                    item_id="single-file",
                    source_label=str(file_path),
                    source_path=file_path,
                    mode=ProcessingMode.SINGLE_FILE,
                )
            ]
        raise InputValidationError("Режим обработки не выбран.")

    def _load_items_into_table(self, items: list[BatchJobItem]) -> None:
        self.items_by_id = {item.item_id: item for item in items}
        for row in self.status_table.get_children():
            self.status_table.delete(row)
        for item in items:
            self.status_table.insert(
                "",
                tk.END,
                iid=item.item_id,
                values=(item.source_label, STATUS_LABELS[item.status], item.message),
            )

    def _refresh_input_preview(self) -> None:
        if self.processing:
            return
        mode = self.mode_var.get()
        if mode == ProcessingMode.URL_LIST.value:
            self._clear_preview_table()
            self.summary_var.set("Нет активной обработки.")
            self._reset_progress()
            return
        try:
            items = self._build_items()
        except InputValidationError:
            self._clear_preview_table()
            self._reset_progress()
            if mode == ProcessingMode.FOLDER.value:
                self.summary_var.set("Нет выбранных файлов для обработки.")
            elif mode == ProcessingMode.SINGLE_FILE.value:
                self.summary_var.set("Файл для обработки не выбран.")
            return

        for item in items:
            item.message = "Готов к обработке."
        self._load_items_into_table(items)
        if mode == ProcessingMode.FOLDER.value:
            self.status_var.set(f"Найдено файлов для обработки: {len(items)}.")
            self.summary_var.set(f"Предпросмотр: найдено файлов {len(items)}")
        elif mode == ProcessingMode.SINGLE_FILE.value:
            self.status_var.set("Выбран один файл для обработки.")
            self.summary_var.set("Предпросмотр: выбран 1 файл")
        self._reset_progress()

    def _clear_preview_table(self) -> None:
        for row in self.status_table.get_children():
            self.status_table.delete(row)
        self.items_by_id.clear()

    def _poll_events(self) -> None:
        try:
            while True:
                event = self.event_queue.get_nowait()
                self._handle_event(event)
        except Empty:
            pass
        finally:
            self.root.after(150, self._poll_events)

    def _handle_event(self, event: tuple) -> None:
        kind = event[0]
        if kind == "item_update":
            _, item_id, status, message = event
            self._update_item(item_id, status, message)
        elif kind == "item_text":
            _, item_id, text = event
            self.items_by_id[item_id].transcript_text = text
        elif kind == "item_result":
            _, result = event
            self._apply_result(result)
        elif kind == "progress":
            _, index, total = event
            self.status_var.set(f"Обработано {index} из {total}.")
            self._set_progress(index, total)
            self._update_summary(index=index, total=total)
        elif kind == "critical_error":
            _, message = event
            self.status_var.set("Пакет остановлен из-за критической ошибки.")
            show_error("Критическая ошибка", message)
        elif kind == "finished":
            _, was_cancelled = event
            self.processing = False
            self.cancel_button.configure(state="disabled")
            if self.status_var.get() != "Пакет остановлен из-за критической ошибки.":
                self.status_var.set("Обработка отменена." if was_cancelled else "Обработка завершена.")
            if self.items_by_id:
                self._set_progress(len(self.items_by_id), len(self.items_by_id))
            self._create_batch_report()
            self._update_summary()
            self._run_environment_check()

    def _update_item(self, item_id: str, status: ItemStatus, message: str) -> None:
        item = self.items_by_id[item_id]
        item.status = status
        item.message = message
        self.status_table.item(item_id, values=(item.source_label, STATUS_LABELS[status], message))

    def _apply_result(self, result: BatchItemResult) -> None:
        item = self.items_by_id[result.item_id]
        item.status = result.status
        item.message = result.message
        item.transcript_text = result.transcript_text
        item.output_path = result.output_path
        self.status_table.item(
            result.item_id,
            values=(item.source_label, STATUS_LABELS[result.status], result.message),
        )
        selected = self.status_table.selection()
        if selected and selected[0] == result.item_id:
            self._show_item_text(item)
        self._update_summary()

    def _on_select_item(self, _event: tk.Event) -> None:
        selected = self.status_table.selection()
        if not selected:
            return
        item = self.items_by_id[selected[0]]
        self._show_item_text(item)
        self.summary_var.set(f"Выбран: {STATUS_LABELS[item.status]} | {item.source_label}")

    def _show_item_text(self, item: BatchJobItem) -> None:
        self.result_text.delete("1.0", tk.END)
        if item.transcript_text:
            self.result_text.insert("1.0", item.transcript_text)
        elif item.message:
            self.result_text.insert("1.0", item.message)

    def _save_selected_text(self) -> None:
        selected = self.status_table.selection()
        if not selected:
            show_info("Сохранение", "Сначала выберите элемент в списке.")
            return
        item = self.items_by_id[selected[0]]
        text = self.result_text.get("1.0", tk.END).strip()
        if not text:
            show_info("Сохранение", "Для выбранного элемента нет текста.")
            return
        target = filedialog.asksaveasfilename(
            title="Сохранить текст",
            defaultextension=".txt",
            initialfile=f"{self._item_base_name(item)}.txt",
            filetypes=[("Text files", "*.txt"), ("All files", "*.*")],
        )
        if target:
            try:
                Path(target).write_text(text, encoding="utf-8")
            except OSError as exc:
                show_error("Сохранение", f"Не удалось сохранить текст: {exc}")
                return
            show_info("Сохранение", "Текст сохранен.")

    def _copy_selected_text(self) -> None:
        text = self.result_text.get("1.0", tk.END).strip()
        if not text:
            show_info("Копирование", "Нет текста для копирования.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(text)
        show_info("Копирование", "Текст скопирован в буфер обмена.")

    def _save_all_results(self) -> None:
        destination = filedialog.askdirectory(title="Выберите папку для сохранения всех результатов")
        if not destination:
            return
        writer = TranscriptWriter()
        count = 0
        skipped = 0
        for item in self.items_by_id.values():
            if not item.transcript_text.strip():
                continue
            try:
                output_path, _message = writer.write(
                    output_dir=Path(destination),
                    base_name=self._item_base_name(item),
                    text=item.transcript_text,
                    policy=ExistingFilePolicy.RENAME.value,
                )
            except OutputError as exc:
                show_error("Сохранить все", str(exc))
                return
            if output_path is None:
                skipped += 1
            else:
                count += 1
        show_info("Сохранить все", f"Сохранено файлов: {count}. Пропущено: {skipped}.")

    def _clear_all(self) -> None:
        if self.processing:
            show_info("Очистка", "Нельзя очищать форму во время обработки.")
            return
        self.url_text.delete("1.0", tk.END)
        self.result_text.delete("1.0", tk.END)
        for row in self.status_table.get_children():
            self.status_table.delete(row)
        self.items_by_id.clear()
        self.status_var.set("Форма очищена.")
        self.summary_var.set("Нет активной обработки.")
        self._reset_progress()
        self.paths_label.configure(text="")
        self.current_log_path = None
        self.current_report_path = None

    def _label_for_language(self, code: str) -> str:
        for label, value in LANGUAGE_OPTIONS.items():
            if value == code:
                return label
        return "Auto detect"

    def _item_base_name(self, item: BatchJobItem) -> str:
        if item.source_path is not None:
            return sanitize_filename(item.source_path.stem or item.item_id)
        if item.source_url:
            raw_name = Path(item.source_url.split("?", maxsplit=1)[0]).stem
            return sanitize_filename(raw_name or item.item_id)
        return sanitize_filename(item.item_id)

    def _update_summary(self, index: int | None = None, total: int | None = None) -> None:
        counts = {
            ItemStatus.DONE: 0,
            ItemStatus.ERROR: 0,
            ItemStatus.SKIPPED: 0,
            ItemStatus.CANCELLED: 0,
            ItemStatus.PROCESSING: 0,
            ItemStatus.DOWNLOADING: 0,
            ItemStatus.QUEUED: 0,
            ItemStatus.SAVING: 0,
        }
        for item in self.items_by_id.values():
            counts[item.status] = counts.get(item.status, 0) + 1
        progress_text = ""
        if index is not None and total is not None:
            progress_text = f" | Прогресс: {index}/{total}"
        self.summary_var.set(
            "Готово: {done} | Ошибки: {error} | Пропущено: {skipped} | Отменено: {cancelled} | В работе: {active} | В очереди: {queued}{progress}".format(
                done=counts[ItemStatus.DONE],
                error=counts[ItemStatus.ERROR],
                skipped=counts[ItemStatus.SKIPPED],
                cancelled=counts[ItemStatus.CANCELLED],
                active=counts[ItemStatus.PROCESSING] + counts[ItemStatus.DOWNLOADING] + counts[ItemStatus.SAVING],
                queued=counts[ItemStatus.QUEUED],
                progress=progress_text,
            )
        )

    def _start_batch_logger(self, output_dir: Path) -> BatchLogger | None:
        logger = BatchLogger()
        try:
            self.current_log_path = logger.start(output_dir / "logs")
        except OutputError as exc:
            self.current_log_path = None
            show_error("Логирование", str(exc))
            return None
        self._refresh_output_paths()
        return logger

    def _create_batch_report(self) -> None:
        if not self.items_by_id:
            return
        writer = BatchReportWriter()
        report_items = [
            ReportItem(
                item_id=item.item_id,
                source_label=item.source_label,
                status=item.status.value,
                message=item.message,
                output_path=str(item.output_path) if item.output_path else "",
            )
            for item in self.items_by_id.values()
        ]
        try:
            destination = Path(self.output_folder_var.get().strip()) / "reports"
            self.current_report_path = writer.write_report(
                destination=destination,
                mode=self.mode_var.get(),
                language=LANGUAGE_OPTIONS[self.language_var.get()],
                items=report_items,
            )
        except OutputError as exc:
            self.current_report_path = None
            show_error("Отчет", str(exc))
            return
        self._refresh_output_paths()

    def _refresh_output_paths(self) -> None:
        parts: list[str] = []
        if self.current_log_path is not None:
            parts.append(f"Лог: {self.current_log_path}")
        if self.current_report_path is not None:
            parts.append(f"Отчет: {self.current_report_path}")
        self.paths_label.configure(text=" | ".join(parts))

    def _set_progress(self, completed: int, total: int) -> None:
        if total <= 0:
            self._reset_progress()
            return
        percent = round((completed / total) * 100)
        self.progress_var.set(percent)
        self.progress_text_var.set(f"Прогресс: {percent}% ({completed}/{total})")

    def _reset_progress(self) -> None:
        self.progress_var.set(0.0)
        self.progress_text_var.set("Прогресс: 0%")
