import tkinter as tk
from tkinter import ttk


class StatusTable(ttk.Treeview):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(
            master,
            columns=("source", "status", "message"),
            show="headings",
            selectmode="browse",
            height=14,
        )
        self.heading("source", text="Источник")
        self.heading("status", text="Статус")
        self.heading("message", text="Сообщение")
        self.column("source", width=420, anchor=tk.W)
        self.column("status", width=120, anchor=tk.W)
        self.column("message", width=420, anchor=tk.W)
