from pathlib import Path
import tkinter as tk

from audio_to_text.settings.manager import SettingsManager
from audio_to_text.transcription.environment import EnvironmentChecker
from audio_to_text.ui.main_window import MainWindow


def main() -> None:
    root = tk.Tk()
    root.title("Audio to Text")
    root.geometry("1200x760")
    root.minsize(960, 640)

    settings_manager = SettingsManager()
    settings = settings_manager.load()
    environment_checker = EnvironmentChecker(app_root=Path.cwd())

    MainWindow(
        root=root,
        settings_manager=settings_manager,
        initial_settings=settings,
        environment_checker=environment_checker,
    )
    root.mainloop()
