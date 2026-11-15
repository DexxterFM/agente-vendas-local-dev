"""Interface desktop Tkinter do Agente de Vendas Local."""
from __future__ import annotations

import re
import queue
import threading
import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk
from typing import Any, Callable

from core.agent import Agent
from core.config import APP_NAME, APP_VERSION, AppConfig, load_config
from core.instagram import build_plan, normalize_profile_url, plan_prompt_context
from core.memory import Memory
from core.playbook import BUILTIN_ENTRIES, comparison_checklist, search_playbook
from core.rea import analyze_project, latest_report, summary as rea_summary
from core.style import analyze_style, greeting_for_hour
from core.supervisor import Supervisor
from core.tools import STAGE_ORDER, next_step_for_stage, stage_label, validate_https_url
from sales_logic import draft_followup, qualify_lead

FONT = "Segoe UI"
COLORS = {
    "bg": "#080f1c",
    "sidebar": "#0b1424",
    "surface": "#101c30",
    "surface_2": "#16263e",
    "input": "#0c1728",
    "border": "#253754",
    "border_soft": "#1b2a43",
    "text": "#edf3fb",
    "muted": "#93a8c4",
    "muted_2": "#6f86a5",
    "accent": "#2dd4bf",
    "accent_dark": "#0f766e",
    "accent_soft": "#123e3a",
    "amber": "#f5b84b",
    "amber_soft": "#3b2b12",
    "green": "#34d399",
    "red": "#f87171",
    "red_soft": "#3a1d24",
    "user_bubble": "#0f3b38",
    "user_border": "#1f6f66",
    "agent_bubble": "#15253d",
}
STATUS_COLORS = {
    "connected": COLORS["green"],
    "attention": COLORS["amber"],
    "unavailable": COLORS["red"],
}
STATUS_LABELS = {
    "connected": "Conectado",
    "attention": "Atenção",
    "unavailable": "Indisponível",
}


def _font(size: int, bold: bool = False) -> tuple:
    return (FONT, size, "bold" if bold else "normal")


def _card(parent: tk.Misc) -> tk.Frame:
    return tk.Frame(
        parent,
        bg=COLORS["surface"],
        highlightbackground=COLORS["border"],
        highlightthickness=1,
        bd=0,
    )


def _button(
    parent: tk.Misc,
    text: str,
    command: Callable[[], None],
    *,
    kind: str = "primary",
    width: int | None = None,
) -> tk.Button:
    if kind == "primary":
        bg, fg, active_bg, active_fg, border = (
            COLORS["accent"],
            COLORS["bg"],
            "#5eead4",
            COLORS["bg"],
            COLORS["accent"],
        )
    elif kind == "danger":
        bg, fg, active_bg, active_fg, border = (
            COLORS["red_soft"],
            COLORS["red"],
            "#4a252e",
            "#fecaca",
            "#6b2d39",
        )
    elif kind == "ghost":
        bg, fg, active_bg, active_fg, border = (
            COLORS["surface"],
            COLORS["muted"],
            COLORS["surface_2"],
            COLORS["text"],
            COLORS["border_soft"],
        )
    else:
        bg, fg, active_bg, active_fg, border = (
            COLORS["surface_2"],
            COLORS["text"],
            "#1d3352",
            COLORS["text"],
            COLORS["border"],
        )
    return tk.Button(
        parent,
        text=text,
        command=command,
        bg=bg,
        fg=fg,
        activebackground=active_bg,
        activeforeground=active_fg,
        relief="flat",
        bd=0,
        padx=14,
        pady=8,
        cursor="hand2",
        font=_font(10, bold=(kind == "primary")),
        highlightthickness=1,
        highlightbackground=border,
        highlightcolor=COLORS["accent"],
        takefocus=True,
        disabledforeground=COLORS["muted_2"],
        width=width,
    )


def _entry(parent: tk.Misc, width: int | None = None) -> tk.Entry:
    return tk.Entry(
        parent,
        width=width,
        bg=COLORS["input"],
        fg=COLORS["text"],
        insertbackground=COLORS["text"],
        relief="flat",
        bd=0,
        highlightthickness=1,
        highlightbackground=COLORS["border"],
        highlightcolor=COLORS["accent"],
        font=_font(10),
    )


def _text(parent: tk.Misc, height: int = 4, state: str = "normal") -> tk.Text:
    widget = tk.Text(
        parent,
        height=height,
        wrap="word",
        bg=COLORS["input"],
        fg=COLORS["text"],
        insertbackground=COLORS["text"],
        relief="flat",
        bd=0,
        padx=10,
        pady=8,
        highlightthickness=1,
        highlightbackground=COLORS["border"],
        highlightcolor=COLORS["accent"],
        font=_font(10),
        state=state,
    )
    return widget


def _set_text(widget: tk.Text, value: str, disabled: bool = True) -> None:
    widget.configure(state="normal")
    widget.delete("1.0", "end")
    widget.insert("1.0", value)
    widget.configure(state="disabled" if disabled else "normal")


def _get_text(widget: tk.Text) -> str:
    return widget.get("1.0", "end").strip()


def _format_time(value: str | None) -> str:
    if not value:
        return "—"
    try:
        stamp = datetime.fromisoformat(value)
        if stamp.tzinfo:
            stamp = stamp.astimezone()
        return stamp.strftime("%d/%m/%Y %H:%M")
    except (TypeError, ValueError):
        return str(value)[:16]


def _stage_color(stage: str) -> str:
    if stage == "hot":
        return COLORS["amber"]
    if stage == "warm":
        return COLORS["accent"]
    return COLORS["muted"]


class Dot(tk.Canvas):
    def __init__(self, parent: tk.Misc, size: int = 10) -> None:
        super().__init__(
            parent,
            width=size,
            height=size,
            bg=COLORS["surface"],
            highlightthickness=0,
        )
        self._size = size
        self._dot = self.create_oval(1, 1, size - 1, size - 1, fill=COLORS["muted_2"], outline="")

    def set(self, color: str) -> None:
        self.itemconfigure(self._dot, fill=color)


class ChatView(tk.Frame):
    """Lista rolável de mensagens com alinhamento e rótulos acessíveis."""

    def __init__(self, parent: tk.Misc) -> None:
        super().__init__(parent, bg=COLORS["surface"])
        self.canvas = tk.Canvas(self, bg=COLORS["surface"], highlightthickness=0, bd=0)
        self.scroll = ttk.Scrollbar(
            self,
            orient="vertical",
            command=self.canvas.yview,
            style="Vertical.TScrollbar",
        )
        self.inner = tk.Frame(self.canvas, bg=COLORS["surface"])
        self.window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scroll.grid(row=0, column=1, sticky="ns")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.inner.grid_columnconfigure(0, weight=1)
        self.inner.bind("<Configure>", self._update_scroll)
        self.canvas.bind("<Configure>", self._on_resize)
        self._labels: list[tk.Label] = []
        self._bind_wheel(self.canvas)
        self._bind_wheel(self.inner)

    def _bind_wheel(self, widget: tk.Misc) -> None:
        widget.bind("<MouseWheel>", self._on_wheel)

    def _on_wheel(self, event: tk.Event) -> str:
        delta = int(-event.delta / 120) if event.delta else 0
        self.canvas.yview_scroll(delta, "units")
        return "break"

    def _update_scroll(self, _event: tk.Event | None = None) -> None:
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_resize(self, event: tk.Event) -> None:
        self.canvas.itemconfigure(self.window, width=event.width)
        wrap = max(240, min(620, event.width - 180))
        for label in self._labels:
            label.configure(wraplength=wrap)

    def _copy(self, text: str) -> None:
        self.clipboard_clear()
        self.clipboard_append(text)

    def append(self, role: str, text: str, meta: str | None = None) -> None:
        text = (text or "").strip()
        if not text:
            return
        row = tk.Frame(self.inner, bg=COLORS["surface"])
        row.grid(sticky="ew", padx=14, pady=4)
        row.grid_columnconfigure(0, weight=1)
        if role == "user":
            holder = tk.Frame(row, bg=COLORS["surface"])
            holder.grid(row=0, column=0, sticky="e")
            tk.Label(
                holder,
                text=meta or "Você",
                bg=COLORS["surface"],
                fg=COLORS["muted"],
                font=_font(8),
            ).pack(anchor="e", padx=4, pady=(0, 2))
            bubble = tk.Frame(
                holder,
                bg=COLORS["user_bubble"],
                highlightbackground=COLORS["user_border"],
                highlightthickness=1,
            )
            bubble.pack(anchor="e")
            label = tk.Label(
                bubble,
                text=text,
                bg=COLORS["user_bubble"],
                fg=COLORS["text"],
                font=_font(10),
                justify="left",
                anchor="w",
                padx=14,
                pady=10,
            )
            label.pack()
        elif role in {"agent", "error"}:
            line = tk.Frame(row, bg=COLORS["surface"])
            line.grid(row=0, column=0, sticky="w")
            avatar = tk.Canvas(
                line,
                width=28,
                height=28,
                bg=COLORS["surface"],
                highlightthickness=0,
            )
            avatar.pack(side="left", anchor="n", padx=(0, 8))
            avatar.create_oval(
                1,
                1,
                27,
                27,
                fill=COLORS["accent_soft"],
                outline=COLORS["accent_dark"],
                width=1,
            )
            avatar.create_text(14, 14, text="A", fill=COLORS["accent"], font=_font(10, bold=True))
            holder = tk.Frame(line, bg=COLORS["surface"])
            holder.pack(side="left", anchor="n")
            tk.Label(
                holder,
                text=meta or ("Agente" if role == "agent" else "Erro"),
                bg=COLORS["surface"],
                fg=COLORS["muted"],
                font=_font(8),
            ).pack(anchor="w", padx=4, pady=(0, 2))
            bubble_bg = COLORS["agent_bubble"] if role == "agent" else COLORS["red_soft"]
            border = COLORS["border"] if role == "agent" else "#6b2d39"
            bubble = tk.Frame(
                holder,
                bg=bubble_bg,
                highlightbackground=border,
                highlightthickness=1,
            )
            bubble.pack(anchor="w")
            label = tk.Label(
                bubble,
                text=text,
                bg=bubble_bg,
                fg=COLORS["text"] if role == "agent" else "#fecaca",
                font=_font(10),
                justify="left",
                anchor="w",
                padx=14,
                pady=10,
            )
            label.pack()
        else:
            holder = tk.Frame(row, bg=COLORS["surface"])
            holder.grid(row=0, column=0, sticky="w")
            label = tk.Label(
                holder,
                text=text,
                bg=COLORS["surface"],
                fg=COLORS["muted"],
                font=_font(9),
                justify="left",
                anchor="w",
            )
            label.pack(anchor="w", padx=4)
            self._labels.append(label)
            for widget in (row, holder, label):
                self._bind_wheel(widget)
            self._copy_bind(label, text)
            self.after_idle(lambda: self.canvas.yview_moveto(1.0))
            return
        self._labels.append(label)
        for widget in (row, line if role in {"agent", "error"} else holder, holder, bubble, label):
            self._bind_wheel(widget)
        self._copy_bind(label, text)
        self.update_idletasks()
        width = self.canvas.winfo_width()
        if width > 1:
            label.configure(wraplength=max(240, min(620, width - 180)))
        self.after_idle(lambda: self.canvas.yview_moveto(1.0))

    def _copy_bind(self, widget: tk.Label, text: str) -> None:
        widget.bind("<Button-3>", lambda _event: self._copy(text))


class App(tk.Tk):
    def __init__(
        self,
        config: AppConfig | None = None,
        memory: Memory | None = None,
        agent: Agent | None = None,
        supervisor: Supervisor | None = None,
    ) -> None:
        super().__init__()
        self.config_obj = config or load_config()
        self.memory = memory or Memory(self.config_obj.db_path)
        self.agent = agent or Agent(self.memory, self.config_obj)
        self.supervisor = supervisor or Supervisor(self.config_obj, self.memory)
        self.current_lead_id: int | None = None
        self._lead_choice_map: dict[str, int] = {}
        self._syncing_selection = False
        self._busy = False
        self._health_busy = False
        self._closing = False
        self._placeholder_active = False
        self._detail_lead_id: int | None = None
        self._ui_queue: queue.Queue = queue.Queue()
        self._instagram_plan = None
        self._instagram_text = ""
        self._instagram_url = ""
        self.health_data: dict[str, dict] = {}
        self.title(f"{APP_NAME} • {APP_VERSION}")
        self.geometry("1280x800")
        self.minsize(1100, 720)
        self.configure(bg=COLORS["bg"])
        self._build_style()
        self._build_shell()
        self._load_history()
        self.refresh_leads()
        self._show_page("chat")
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(100, self._poll_ui_queue)
        self.after(350, self.refresh_health_async)
        self.after(500, self._enable_dark_titlebar)

    # ---------------------------------------------------------- fila de threads
    def _post(self, callback: Callable[..., None], *args: Any) -> None:
        """Entrega resultados de threads à thread principal do Tk."""
        self._ui_queue.put((callback, args))

    def _poll_ui_queue(self) -> None:
        if self._closing:
            return
        while True:
            try:
                callback, args = self._ui_queue.get_nowait()
            except queue.Empty:
                break
            try:
                callback(*args)
            except Exception as exc:
                self.chat_status.configure(
                    text=f"Erro interno: {str(exc)[:120]}",
                    fg=COLORS["red"],
                )
        self.after(100, self._poll_ui_queue)

    # ------------------------------------------------------------------ estilo
    def _build_style(self) -> None:
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Treeview",
            background=COLORS["surface"],
            fieldbackground=COLORS["surface"],
            foreground=COLORS["text"],
            bordercolor=COLORS["surface"],
            borderwidth=0,
            rowheight=32,
            font=_font(9),
        )
        style.map(
            "Treeview",
            background=[("selected", COLORS["accent_dark"])],
            foreground=[("selected", "#ffffff")],
        )
        style.configure(
            "Treeview.Heading",
            background=COLORS["surface_2"],
            foreground=COLORS["muted"],
            relief="flat",
            borderwidth=0,
            font=_font(9, bold=True),
            padding=(8, 8),
        )
        style.map("Treeview.Heading", background=[("active", COLORS["surface_2"])])
        style.configure(
            "TCombobox",
            fieldbackground=COLORS["input"],
            background=COLORS["input"],
            foreground=COLORS["text"],
            arrowcolor=COLORS["muted"],
            bordercolor=COLORS["border"],
            lightcolor=COLORS["border"],
            darkcolor=COLORS["border"],
            padding=7,
            font=_font(9),
        )
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", COLORS["input"])],
            foreground=[("readonly", COLORS["text"])],
            selectbackground=[("readonly", COLORS["input"])],
            selectforeground=[("readonly", COLORS["text"])],
        )
        style.configure(
            "Vertical.TScrollbar",
            background=COLORS["surface_2"],
            troughcolor=COLORS["surface"],
            bordercolor=COLORS["surface"],
            arrowcolor=COLORS["muted"],
            width=10,
        )
        self.option_add("*TCombobox*Listbox.background", COLORS["surface_2"])
        self.option_add("*TCombobox*Listbox.foreground", COLORS["text"])
        self.option_add("*TCombobox*Listbox.selectBackground", COLORS["accent_dark"])
        self.option_add("*TCombobox*Listbox.selectForeground", "#ffffff")

    # ------------------------------------------------------------------ shell
    def _build_shell(self) -> None:
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)
        self._build_sidebar()
        self.content = tk.Frame(self, bg=COLORS["bg"])
        self.content.grid(row=0, column=1, sticky="nsew")
        self.content.grid_rowconfigure(0, weight=1)
        self.content.grid_columnconfigure(0, weight=1)
        self.pages: dict[str, tk.Frame] = {}
        for key in ("chat", "crm", "instagram", "learning", "status"):
            page = tk.Frame(self.content, bg=COLORS["bg"])
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page
        self._build_chat_page(self.pages["chat"])
        self._build_crm_page(self.pages["crm"])
        self._build_instagram_page(self.pages["instagram"])
        self._build_learning_page(self.pages["learning"])
        self._build_status_page(self.pages["status"])

    def _build_sidebar(self) -> None:
        sidebar = tk.Frame(self, bg=COLORS["sidebar"], width=236)
        sidebar.grid(row=0, column=0, sticky="ns")
        sidebar.grid_propagate(False)
        sidebar.grid_rowconfigure(4, weight=1)
        brand = tk.Frame(sidebar, bg=COLORS["sidebar"])
        brand.grid(row=0, column=0, sticky="ew", padx=20, pady=(24, 22))
        logo = tk.Canvas(
            brand,
            width=38,
            height=38,
            bg=COLORS["sidebar"],
            highlightthickness=0,
        )
        logo.pack(side="left")
        logo.create_oval(3, 3, 35, 35, fill=COLORS["accent"], outline="")
        logo.create_polygon(9, 29, 16, 29, 11, 36, fill=COLORS["accent"], outline="")
        logo.create_line(14, 21, 25, 10, fill=COLORS["bg"], width=2, arrow="last")
        text = tk.Frame(brand, bg=COLORS["sidebar"])
        text.pack(side="left", padx=(10, 0))
        tk.Label(
            text,
            text="Agente de Vendas",
            bg=COLORS["sidebar"],
            fg=COLORS["text"],
            font=_font(11, bold=True),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            text,
            text="Local",
            bg=COLORS["sidebar"],
            fg=COLORS["accent"],
            font=_font(9),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            sidebar,
            text="NAVEGAÇÃO",
            bg=COLORS["sidebar"],
            fg=COLORS["muted_2"],
            font=_font(8, bold=True),
            anchor="w",
        ).grid(row=1, column=0, sticky="ew", padx=22, pady=(0, 8))
        nav = tk.Frame(sidebar, bg=COLORS["sidebar"])
        nav.grid(row=2, column=0, sticky="ew", padx=12)
        nav.grid_columnconfigure(0, weight=1)
        self.nav_buttons: dict[str, tk.Button] = {}
        for row, (key, label) in enumerate(
            (
                ("chat", "Conversa"),
                ("crm", "CRM"),
                ("instagram", "Instagram"),
                ("learning", "Aprendizado"),
                ("status", "Status"),
            )
        ):
            button = tk.Button(
                nav,
                text=f"  {label}",
                command=lambda name=key: self._show_page(name),
                bg=COLORS["sidebar"],
                fg=COLORS["muted"],
                activebackground=COLORS["surface_2"],
                activeforeground=COLORS["text"],
                relief="flat",
                bd=0,
                anchor="w",
                padx=12,
                pady=10,
                cursor="hand2",
                font=_font(10),
                highlightthickness=0,
                takefocus=True,
            )
            button.grid(row=row, column=0, sticky="ew", pady=1)
            self.nav_buttons[key] = button
        spacer = tk.Frame(sidebar, bg=COLORS["sidebar"])
        spacer.grid(row=4, column=0, sticky="nsew")
        privacy = tk.Label(
            sidebar,
            text="●  Local / Privado",
            bg=COLORS["accent_soft"],
            fg=COLORS["accent"],
            font=_font(9, bold=True),
            padx=12,
            pady=7,
            anchor="w",
        )
        privacy.grid(row=5, column=0, sticky="ew", padx=18, pady=(8, 10))
        model_card = tk.Frame(
            sidebar,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border_soft"],
            highlightthickness=1,
        )
        model_card.grid(row=6, column=0, sticky="ew", padx=14, pady=(0, 18))
        model_inner = tk.Frame(model_card, bg=COLORS["surface"])
        model_inner.pack(fill="x", padx=12, pady=10)
        tk.Label(
            model_inner,
            text="MODELO ATUAL",
            bg=COLORS["surface"],
            fg=COLORS["muted_2"],
            font=_font(8, bold=True),
            anchor="w",
        ).pack(anchor="w")
        self.sidebar_model = tk.Label(
            model_inner,
            text=self.config_obj.ollama_model,
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=_font(9),
            anchor="w",
        )
        self.sidebar_model.pack(anchor="w", pady=(3, 0))
        tk.Label(
            model_inner,
            text=f"versão {APP_VERSION}",
            bg=COLORS["surface"],
            fg=COLORS["muted_2"],
            font=_font(8),
            anchor="w",
        ).pack(anchor="w", pady=(5, 0))

    def _page_header(self, parent: tk.Frame, title: str, subtitle: str) -> tk.Frame:
        header = tk.Frame(parent, bg=COLORS["bg"])
        left = tk.Frame(header, bg=COLORS["bg"])
        left.pack(side="left", fill="x", expand=True)
        tk.Label(
            left,
            text=title,
            bg=COLORS["bg"],
            fg=COLORS["text"],
            font=_font(19, bold=True),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            left,
            text=subtitle,
            bg=COLORS["bg"],
            fg=COLORS["muted"],
            font=_font(9),
            anchor="w",
        ).pack(anchor="w", pady=(3, 0))
        return header

    def _show_page(self, name: str) -> None:
        if name not in self.pages:
            return
        self.pages[name].tkraise()
        for key, button in self.nav_buttons.items():
            active = key == name
            button.configure(
                bg=COLORS["surface_2"] if active else COLORS["sidebar"],
                fg=COLORS["accent"] if active else COLORS["muted"],
                font=_font(10, bold=active),
            )
        if name == "crm":
            self.refresh_leads()
        elif name == "instagram":
            self.refresh_pending_actions()
            self._update_instagram_notes()
        elif name == "learning":
            self.refresh_learning()
        elif name == "status":
            self.refresh_audit()
            self._update_rea_text()

    # ------------------------------------------------------------------ conversa
    def _build_chat_page(self, page: tk.Frame) -> None:
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)
        header = self._page_header(
            page,
            "Conversa com o agente",
            "Seu vendedor assistido por IA local",
        )
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(22, 14))
        header_right = tk.Frame(header, bg=COLORS["bg"])
        header_right.pack(side="right", anchor="n")
        tk.Label(
            header_right,
            text="●  Ollama local",
            bg=COLORS["surface_2"],
            fg=COLORS["accent"],
            font=_font(9),
            padx=12,
            pady=7,
        ).pack()
        body = tk.Frame(page, bg=COLORS["bg"])
        body.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 18))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, minsize=326)
        chat_card = _card(body)
        chat_card.grid(row=0, column=0, sticky="nsew")
        chat_card.grid_rowconfigure(1, weight=1)
        chat_card.grid_columnconfigure(0, weight=1)
        chat_header = tk.Frame(chat_card, bg=COLORS["surface"])
        chat_header.grid(row=0, column=0, sticky="ew", padx=18, pady=(14, 5))
        chat_header.grid_columnconfigure(0, weight=1)
        tk.Label(
            chat_header,
            text="Histórico da conversa",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=_font(12, bold=True),
            anchor="w",
        ).grid(row=0, column=0, sticky="w")
        self.chat_status = tk.Label(
            chat_header,
            text="Pronto",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=_font(9),
            anchor="e",
        )
        self.chat_status.grid(row=0, column=1, sticky="e")
        self.chat_view = ChatView(chat_card)
        self.chat_view.grid(row=1, column=0, sticky="nsew", padx=4)
        composer = tk.Frame(chat_card, bg=COLORS["surface"])
        composer.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 14))
        composer.grid_columnconfigure(0, weight=1)
        input_frame = tk.Frame(
            composer,
            bg=COLORS["input"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
        )
        input_frame.grid(row=0, column=0, sticky="ew")
        self.input = _text(input_frame, height=4)
        self.input.pack(fill="x", padx=2, pady=2)
        self.input.bind("<Return>", self._on_return)
        self.input.bind("<FocusIn>", self._on_input_focus_in)
        self.input.bind("<FocusOut>", self._on_input_focus_out)
        self._set_placeholder()
        actions = tk.Frame(composer, bg=COLORS["surface"])
        actions.grid(row=1, column=0, sticky="ew", pady=(9, 0))
        self.send_button = _button(actions, "Enviar", self.send)
        self.send_button.pack(side="left")
        self.open_button = _button(
            actions,
            "Abrir no navegador",
            self.open_in_browser,
            kind="secondary",
        )
        self.open_button.pack(side="left", padx=(8, 0))
        tk.Label(
            actions,
            text="Enter envia • Shift+Enter quebra linha",
            bg=COLORS["surface"],
            fg=COLORS["muted_2"],
            font=_font(8),
        ).pack(side="right")
        tk.Label(
            composer,
            text="◈  Nenhuma ação externa é executada sem autorização.",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=_font(8),
        ).grid(row=2, column=0, sticky="w", pady=(8, 0))
        self._build_lead_panel(body)

    def _build_lead_panel(self, parent: tk.Frame) -> None:
        panel = _card(parent)
        panel.grid(row=0, column=1, sticky="nsew", padx=(14, 0))
        inner = tk.Frame(panel, bg=COLORS["surface"])
        inner.pack(fill="both", expand=True, padx=16, pady=16)
        tk.Label(
            inner,
            text="RESUMO COMERCIAL",
            bg=COLORS["surface"],
            fg=COLORS["muted_2"],
            font=_font(8, bold=True),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            inner,
            text="Lead em foco",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=_font(13, bold=True),
            anchor="w",
        ).pack(anchor="w", pady=(2, 10))
        self.lead_combo = ttk.Combobox(inner, state="readonly", font=_font(9))
        self.lead_combo.pack(fill="x")
        self.lead_combo.bind("<<ComboboxSelected>>", self._on_combo_select)
        separator = tk.Frame(inner, bg=COLORS["border_soft"], height=1)
        separator.pack(fill="x", pady=12)
        self.lead_name_label = tk.Label(
            inner,
            text="Nenhum lead selecionado",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=_font(13, bold=True),
            anchor="w",
            justify="left",
        )
        self.lead_name_label.pack(anchor="w")
        self.lead_contact_label = tk.Label(
            inner,
            text="Cadastre um lead na aba CRM.",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=_font(9),
            anchor="w",
            justify="left",
        )
        self.lead_contact_label.pack(anchor="w", pady=(3, 10))
        stages = tk.Frame(inner, bg=COLORS["surface"])
        stages.pack(fill="x", pady=(2, 12))
        self.stage_chips: dict[str, tk.Label] = {}
        for stage in STAGE_ORDER:
            chip = tk.Label(
                stages,
                text=stage_label(stage),
                bg=COLORS["surface_2"],
                fg=COLORS["muted"],
                font=_font(8, bold=True),
                padx=9,
                pady=5,
                highlightbackground=COLORS["border"],
                highlightthickness=1,
            )
            chip.pack(side="left", padx=(0, 5))
            self.stage_chips[stage] = chip
        score_row = tk.Frame(inner, bg=COLORS["surface"])
        score_row.pack(fill="x", pady=(0, 2))
        tk.Label(
            score_row,
            text="SCORE DE INTENÇÃO",
            bg=COLORS["surface"],
            fg=COLORS["muted_2"],
            font=_font(8, bold=True),
            anchor="w",
        ).pack(side="left")
        self.score_value = tk.Label(
            score_row,
            text="0/100",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=_font(12, bold=True),
            anchor="e",
        )
        self.score_value.pack(side="right")
        self.score_canvas = tk.Canvas(
            inner,
            height=7,
            bg=COLORS["surface"],
            highlightthickness=0,
            bd=0,
        )
        self.score_canvas.pack(fill="x", pady=(4, 12))
        self.score_canvas.bind("<Configure>", lambda _event: self._draw_score())
        tk.Label(
            inner,
            text="PRÓXIMO PASSO",
            bg=COLORS["surface"],
            fg=COLORS["muted_2"],
            font=_font(8, bold=True),
            anchor="w",
        ).pack(anchor="w")
        self.next_action_label = tk.Label(
            inner,
            text="—",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=_font(9),
            anchor="w",
            justify="left",
            wraplength=270,
        )
        self.next_action_label.pack(anchor="w", pady=(3, 12))
        follow_head = tk.Frame(inner, bg=COLORS["surface"])
        follow_head.pack(fill="x")
        tk.Label(
            follow_head,
            text="FOLLOW-UP",
            bg=COLORS["surface"],
            fg=COLORS["muted_2"],
            font=_font(8, bold=True),
            anchor="w",
        ).pack(side="left")
        self.follow_badge = tk.Label(
            follow_head,
            text="NÃO ENVIADO",
            bg=COLORS["amber_soft"],
            fg=COLORS["amber"],
            font=_font(7, bold=True),
            padx=7,
            pady=3,
        )
        self.follow_badge.pack(side="right")
        self.follow_text = _text(inner, height=4, state="disabled")
        self.follow_text.pack(fill="x", pady=(6, 8))
        self.follow_text.configure(bg=COLORS["input"], fg=COLORS["muted"], font=_font(9))
        self.follow_button = _button(
            inner,
            "Gerar follow-up",
            lambda: self.generate_followup(),
            kind="secondary",
        )
        self.follow_button.pack(fill="x", pady=(0, 6))
        consent_row = tk.Frame(inner, bg=COLORS["surface"])
        consent_row.pack(fill="x", pady=(2, 4))
        self.consent_label = tk.Label(
            consent_row,
            text="Consentimento: não registrado",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=_font(8),
            anchor="w",
        )
        self.consent_label.pack(side="left", fill="x", expand=True)
        self.consent_button = _button(
            consent_row,
            "Registrar",
            lambda: self.register_consent(),
            kind="ghost",
        )
        self.consent_button.configure(padx=8, pady=4, font=_font(8))
        self.consent_button.pack(side="right")
        self._set_lead_controls(False)

    def _load_history(self) -> None:
        self.chat_view.append(
            "system",
            "Aplicação pronta. O modelo, o navegador e a memória são locais. "
            "Nenhuma mensagem é enviada automaticamente.",
        )
        for role, content in self.memory.recent(6):
            if role in {"user", "assistant"}:
                self.chat_view.append("user" if role == "user" else "agent", content)

    def _set_placeholder(self) -> None:
        if self._placeholder_active:
            return
        self.input.delete("1.0", "end")
        self.input.insert(
            "1.0",
            "Descreva o que você precisa ou cole uma URL HTTPS…",
            "placeholder",
        )
        self.input.tag_configure("placeholder", foreground=COLORS["muted_2"])
        self._placeholder_active = True

    def _on_input_focus_in(self, _event: tk.Event) -> None:
        if self._placeholder_active:
            self.input.delete("1.0", "end")
            self._placeholder_active = False

    def _on_input_focus_out(self, _event: tk.Event) -> None:
        if not self.input.get("1.0", "end").strip():
            self._set_placeholder()

    def _composer_text(self) -> str:
        if self._placeholder_active:
            return ""
        return self.input.get("1.0", "end").strip()

    def _clear_composer(self) -> None:
        self.input.delete("1.0", "end")
        self._placeholder_active = False
        if self.focus_get() is not self.input:
            self._set_placeholder()

    def _on_return(self, event: tk.Event) -> str | None:
        if event.state & 0x0001:  # Shift+Enter
            return None
        self.send()
        return "break"

    def _set_busy(self, busy: bool, label: str = "Pronto") -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        self.send_button.configure(state=state)
        self.open_button.configure(state=state)
        self.chat_status.configure(
            text=label,
            fg=COLORS["amber"] if busy else COLORS["muted"],
        )
        self.update_idletasks()

    def send(self) -> None:
        text = self._composer_text()
        if not text or self._busy:
            return
        self._clear_composer()
        self.chat_view.append("user", text)
        self._set_busy(True, "Pensando…")
        threading.Thread(target=self._agent_worker, args=(text,), daemon=True).start()

    def _agent_worker(self, text: str) -> None:
        try:
            answer = self.agent.run(text)
        except Exception as exc:
            self._post(self._agent_done, None, str(exc))
        else:
            self._post(self._agent_done, answer, None)

    def _agent_done(self, answer: str | None, error: str | None) -> None:
        if self._closing:
            return
        self._set_busy(False)
        if answer:
            self.chat_view.append("agent", answer)
        if error:
            self.chat_view.append("error", error)
        self.refresh_leads()
        self.refresh_audit()

    def open_in_browser(self) -> None:
        text = self._composer_text()
        match = re.search(r"https://[^\s<>\"']+", text, re.I)
        if not match:
            self.chat_view.append(
                "system",
                "Cole uma URL HTTPS no campo de mensagem para abrir no navegador.",
            )
            self.input.focus_set()
            return
        url = match.group(0).rstrip(".,);]}!?")
        allowed, reason = validate_https_url(url)
        if not allowed:
            self.chat_view.append("error", reason)
            return
        confirmed = messagebox.askyesno(
            "Confirmar navegação",
            f"Abrir esta URL no BrowserOS?\n\n{url}\n\n"
            "A ação apenas abre e lê a página pública. Nenhum formulário será preenchido.",
            parent=self,
        )
        if not confirmed:
            return
        self._clear_composer()
        self.chat_view.append("user", f"Abrir no navegador: {url}")
        self._set_busy(True, "Lendo página…")
        threading.Thread(target=self._open_worker, args=(url,), daemon=True).start()

    def _open_worker(self, url: str) -> None:
        try:
            answer = self.agent.open_url(url)
        except Exception as exc:
            self._post(self._agent_done, None, str(exc))
        else:
            self._post(self._agent_done, answer, None)

    # ------------------------------------------------------------------ lead
    def _lead_detail(self) -> dict[str, Any] | None:
        if self.current_lead_id is None:
            return None
        return self.memory.get_lead_detail(self.current_lead_id)

    def _set_lead_controls(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for widget in (self.follow_button, self.consent_button):
            widget.configure(state=state)

    def _on_combo_select(self, _event: tk.Event) -> None:
        display = self.lead_combo.get()
        lead_id = self._lead_choice_map.get(display)
        if lead_id is not None:
            self.select_lead(lead_id)

    def select_lead(self, lead_id: int) -> None:
        self.current_lead_id = lead_id
        self._update_lead_panel()
        self._update_crm_detail()
        selection = self.leads_tree.selection()
        if selection:
            values = self.leads_tree.item(selection[0], "values")
            if values and int(values[0]) == lead_id:
                # Já está selecionado; evita disparar <<TreeviewSelect>> em loop.
                return
        self._syncing_selection = True
        try:
            for item in self.leads_tree.get_children():
                values = self.leads_tree.item(item, "values")
                if values and int(values[0]) == lead_id:
                    self.leads_tree.selection_set(item)
                    self.leads_tree.focus(item)
                    self.leads_tree.see(item)
                    break
        finally:
            self._syncing_selection = False

    def _update_lead_panel(self) -> None:
        detail = self._lead_detail()
        choices = self.memory.list_lead_choices()
        self._lead_choice_map = {f"#{lead_id}  {name}": lead_id for lead_id, name, _ in choices}
        self.lead_combo.configure(values=list(self._lead_choice_map))
        if detail:
            display = f"#{detail['id']}  {detail['name']}"
            self.lead_combo.set(display)
        else:
            self.lead_combo.set("")
        if not detail:
            self.lead_name_label.configure(text="Nenhum lead selecionado")
            self.lead_contact_label.configure(text="Cadastre um lead na aba CRM.")
            self.score_value.configure(text="0/100", fg=COLORS["muted"])
            self.next_action_label.configure(text="—")
            self.follow_text.configure(state="normal")
            self.follow_text.delete("1.0", "end")
            self.follow_text.insert("1.0", "Nenhum rascunho gerado.")
            self.follow_text.configure(state="disabled")
            self.follow_badge.configure(text="NÃO ENVIADO")
            self.consent_label.configure(text="Consentimento: não registrado")
            self._set_lead_controls(False)
            for chip in self.stage_chips.values():
                chip.configure(bg=COLORS["surface_2"], fg=COLORS["muted"])
            self._draw_score(0)
            return
        stage = str(detail["stage"])
        self.lead_name_label.configure(text=str(detail["name"]))
        contact = str(detail["contact"] or "Sem contato informado")
        self.lead_contact_label.configure(text=contact)
        self.score_value.configure(text=f"{detail['score']}/100", fg=_stage_color(stage))
        self.next_action_label.configure(
            text=str(detail["next_action"] or next_step_for_stage(stage))
        )
        for key, chip in self.stage_chips.items():
            active = key == stage
            chip.configure(
                bg=_stage_color(key) if active else COLORS["surface_2"],
                fg=COLORS["bg"] if active else COLORS["muted"],
            )
        followup = self.memory.latest_followup(int(detail["id"]))
        self.follow_text.configure(state="normal")
        self.follow_text.delete("1.0", "end")
        if followup and followup["draft"]:
            self.follow_text.insert("1.0", str(followup["draft"]))
            self.follow_badge.configure(
                text="NÃO ENVIADO",
                bg=COLORS["amber_soft"],
                fg=COLORS["amber"],
            )
        else:
            self.follow_text.insert("1.0", "Nenhum rascunho gerado.")
            self.follow_badge.configure(
                text="NÃO ENVIADO",
                bg=COLORS["surface_2"],
                fg=COLORS["muted"],
            )
        self.follow_text.configure(state="disabled")
        consent = self.memory.latest_consent(int(detail["id"]))
        if consent and consent["granted"]:
            self.consent_label.configure(
                text=f"Consentimento: registrado em {_format_time(consent['created_at'])}"
            )
        else:
            self.consent_label.configure(text="Consentimento: não registrado")
        self._set_lead_controls(True)
        self._draw_score(int(detail["score"]))

    def _draw_score(self, score: int | None = None) -> None:
        self.score_canvas.delete("all")
        width = self.score_canvas.winfo_width() or 270
        height = 7
        if score is None:
            detail = self._lead_detail()
            score = int(detail["score"]) if detail else 0
        self.score_canvas.create_rectangle(
            0, 0, width, height, fill=COLORS["surface_2"], outline=""
        )
        if score > 0:
            color = COLORS["amber"] if score >= 60 else COLORS["accent"]
            self.score_canvas.create_rectangle(
                0, 0, max(3, width * min(score, 100) / 100), height, fill=color, outline=""
            )

    # ------------------------------------------------------------------ CRM
    def _build_crm_page(self, page: tk.Frame) -> None:
        header = self._page_header(
            page,
            "CRM de leads",
            "Qualificação determinística, consentimento e follow-ups locais",
        )
        header.pack(fill="x", padx=24, pady=(22, 14))
        tk.Button(
            header,
            text="Atualizar lista",
            command=self.refresh_leads,
            bg=COLORS["surface_2"],
            fg=COLORS["text"],
            activebackground=COLORS["border"],
            activeforeground=COLORS["text"],
            relief="flat",
            bd=0,
            padx=12,
            pady=7,
            font=_font(9),
            cursor="hand2",
            highlightthickness=0,
            takefocus=True,
        ).pack(side="right", anchor="n")
        form = _card(page)
        form.pack(fill="x", padx=24, pady=(0, 12))
        form_inner = tk.Frame(form, bg=COLORS["surface"])
        form_inner.pack(fill="x", padx=14, pady=12)
        tk.Label(
            form_inner,
            text="Novo lead",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=_font(11, bold=True),
            anchor="w",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        tk.Label(
            form_inner,
            text="Nome",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=_font(9),
        ).grid(row=1, column=0, sticky="w", padx=(0, 6))
        self.lead_name = _entry(form_inner, 26)
        self.lead_name.grid(row=1, column=1, sticky="ew", padx=(0, 12))
        tk.Label(
            form_inner,
            text="Contato",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=_font(9),
        ).grid(row=1, column=2, sticky="w", padx=(0, 6))
        self.lead_contact = _entry(form_inner, 22)
        self.lead_contact.grid(row=1, column=3, sticky="ew", padx=(0, 12))
        self.consent_var = tk.BooleanVar(value=False)
        tk.Checkbutton(
            form_inner,
            text="Lead autorizou contato",
            variable=self.consent_var,
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            activebackground=COLORS["surface"],
            activeforeground=COLORS["text"],
            selectcolor=COLORS["input"],
            font=_font(9),
            highlightthickness=0,
            cursor="hand2",
        ).grid(row=1, column=4, sticky="w", padx=(0, 12))
        _button(form_inner, "Salvar lead", self.save_lead).grid(row=1, column=5, sticky="e")
        form_inner.grid_columnconfigure(1, weight=1)
        form_inner.grid_columnconfigure(3, weight=1)
        self.crm_hint = tk.Label(
            form_inner,
            text="",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=_font(8),
            anchor="w",
        )
        self.crm_hint.grid(row=2, column=0, columnspan=6, sticky="w", pady=(8, 0))
        body = tk.Frame(page, bg=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=24, pady=(0, 18))
        body.grid_rowconfigure(0, weight=1)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, minsize=360)
        table_card = _card(body)
        table_card.grid(row=0, column=0, sticky="nsew")
        table_header = tk.Frame(table_card, bg=COLORS["surface"])
        table_header.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(
            table_header,
            text="Leads",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=_font(11, bold=True),
        ).pack(side="left")
        self.leads_count = tk.Label(
            table_header,
            text="0 registros",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=_font(8),
        )
        self.leads_count.pack(side="right")
        table_holder = tk.Frame(table_card, bg=COLORS["surface"])
        table_holder.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        columns = ("id", "name", "contact", "stage", "score", "updated", "next")
        self.leads_tree = ttk.Treeview(
            table_holder,
            columns=columns,
            show="headings",
            selectmode="browse",
        )
        headings = {
            "id": ("ID", 44),
            "name": ("Nome", 160),
            "contact": ("Contato", 120),
            "stage": ("Etapa", 82),
            "score": ("Score", 60),
            "updated": ("Última interação", 120),
            "next": ("Próxima ação", 190),
        }
        for column, (label, width) in headings.items():
            self.leads_tree.heading(column, text=label, anchor="w")
            self.leads_tree.column(column, width=width, minwidth=40, anchor="w")
        scroll = ttk.Scrollbar(
            table_holder,
            orient="vertical",
            command=self.leads_tree.yview,
            style="Vertical.TScrollbar",
        )
        self.leads_tree.configure(yscrollcommand=scroll.set)
        self.leads_tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.leads_tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._build_crm_detail(body)

    def _build_crm_detail(self, parent: tk.Frame) -> None:
        panel = _card(parent)
        panel.grid(row=0, column=1, sticky="nsew", padx=(14, 0))
        inner = tk.Frame(panel, bg=COLORS["surface"])
        inner.pack(fill="both", expand=True, padx=16, pady=14)
        tk.Label(
            inner,
            text="Qualificação",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=_font(12, bold=True),
            anchor="w",
        ).pack(anchor="w")
        self.crm_lead_name = tk.Label(
            inner,
            text="Selecione um lead",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=_font(12, bold=True),
            anchor="w",
            justify="left",
        )
        self.crm_lead_name.pack(anchor="w", pady=(8, 1))
        self.crm_lead_meta = tk.Label(
            inner,
            text="—",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=_font(8),
            anchor="w",
            justify="left",
        )
        self.crm_lead_meta.pack(anchor="w", pady=(0, 8))
        tk.Label(
            inner,
            text="Mensagem recebida",
            bg=COLORS["surface"],
            fg=COLORS["muted_2"],
            font=_font(8, bold=True),
            anchor="w",
        ).pack(anchor="w")
        self.crm_message = _text(inner, height=4)
        self.crm_message.pack(fill="x", pady=(4, 7))
        _button(inner, "Qualificar lead", self.qualify_selected).pack(fill="x", pady=(0, 6))
        self.crm_result = tk.Label(
            inner,
            text="Sem qualificação registrada.",
            bg=COLORS["input"],
            fg=COLORS["muted"],
            font=_font(8),
            anchor="w",
            justify="left",
            wraplength=320,
            padx=9,
            pady=7,
        )
        self.crm_result.pack(fill="x", pady=(0, 8))
        tk.Label(
            inner,
            text="Rascunho de follow-up",
            bg=COLORS["surface"],
            fg=COLORS["muted_2"],
            font=_font(8, bold=True),
            anchor="w",
        ).pack(anchor="w")
        self.crm_followup = _text(inner, height=4, state="disabled")
        self.crm_followup.configure(fg=COLORS["muted"], font=_font(9))
        self.crm_followup.pack(fill="x", pady=(4, 7))
        row = tk.Frame(inner, bg=COLORS["surface"])
        row.pack(fill="x")
        self.crm_follow_button = _button(
            row,
            "Gerar follow-up",
            lambda: self.generate_followup(),
            kind="secondary",
        )
        self.crm_follow_button.pack(side="left")
        self.crm_consent_button = _button(
            row,
            "Registrar consentimento",
            lambda: self.register_consent(),
            kind="ghost",
        )
        self.crm_consent_button.configure(font=_font(8), padx=8)
        self.crm_consent_button.pack(side="right")
        self.crm_follow_button.configure(state="disabled")
        self.crm_consent_button.configure(state="disabled")

    def _on_tree_select(self, _event: tk.Event) -> None:
        if self._syncing_selection:
            return
        selection = self.leads_tree.selection()
        if not selection:
            return
        values = self.leads_tree.item(selection[0], "values")
        if values:
            try:
                self.select_lead(int(values[0]))
            except (TypeError, ValueError):
                return

    def refresh_leads(self) -> None:
        if not hasattr(self, "leads_tree"):
            return
        selected = self.current_lead_id
        rows = self.memory.list_leads_detailed()
        details = {int(row[0]): row for row in rows}
        for item in self.leads_tree.get_children():
            self.leads_tree.delete(item)
        for row in rows:
            lead_id, name, contact, stage, score, _notes, next_action, updated, _created = row
            self.leads_tree.insert(
                "",
                "end",
                values=(
                    lead_id,
                    name,
                    contact or "—",
                    stage_label(str(stage)),
                    f"{score}/100",
                    _format_time(str(updated)),
                    next_action or "—",
                ),
            )
        self.leads_count.configure(text=f"{len(rows)} registro{'s' if len(rows) != 1 else ''}")
        if selected not in details:
            selected = rows[0][0] if rows else None
        self.current_lead_id = selected
        self._update_lead_panel()
        self._update_crm_detail()
        if selected is not None:
            self._syncing_selection = True
            try:
                for item in self.leads_tree.get_children():
                    values = self.leads_tree.item(item, "values")
                    if values and int(values[0]) == selected:
                        self.leads_tree.selection_set(item)
                        self.leads_tree.focus(item)
                        break
            finally:
                self._syncing_selection = False

    def _update_crm_detail(self) -> None:
        detail = self._lead_detail()
        if not detail:
            self.crm_lead_name.configure(text="Selecione um lead")
            self.crm_lead_meta.configure(text="—")
            self.crm_result.configure(text="Sem qualificação registrada.")
            self.crm_followup.configure(state="normal")
            self.crm_followup.delete("1.0", "end")
            self.crm_followup.configure(state="disabled")
            self.crm_follow_button.configure(state="disabled")
            self.crm_consent_button.configure(state="disabled")
            return
        lead_id = int(detail["id"])
        if self._detail_lead_id != lead_id:
            self._detail_lead_id = lead_id
            self.crm_message.delete("1.0", "end")
            history = self.memory.list_conversations(lead_id, limit=1)
            if history:
                self.crm_message.insert("1.0", str(history[0][1]))
        self.crm_lead_name.configure(text=str(detail["name"]))
        self.crm_lead_meta.configure(
            text=(
                f"{detail['contact'] or 'Sem contato'} • {stage_label(str(detail['stage']))} "
                f"• score {detail['score']}/100"
            )
        )
        notes = str(detail["notes"] or "")
        reasons = notes.split(";", 1)[1].strip() if ";" in notes else notes.strip()
        if reasons:
            self.crm_result.configure(
                text=f"Etapa: {stage_label(str(detail['stage']))}. Razões: {reasons}",
                fg=COLORS["text"],
            )
        else:
            self.crm_result.configure(
                text="Sem qualificação registrada.",
                fg=COLORS["muted"],
            )
        followup = self.memory.latest_followup(lead_id)
        self.crm_followup.configure(state="normal")
        self.crm_followup.delete("1.0", "end")
        if followup and followup["draft"]:
            self.crm_followup.insert(
                "1.0",
                f"{followup['draft']}\n\nStatus: rascunho local — não enviado.",
            )
        else:
            self.crm_followup.insert("1.0", "Nenhum rascunho gerado.")
        self.crm_followup.configure(state="disabled")
        self.crm_follow_button.configure(state="normal")
        self.crm_consent_button.configure(state="normal")

    def save_lead(self) -> None:
        name = self.lead_name.get().strip()
        contact = self.lead_contact.get().strip()
        if not name:
            self.crm_hint.configure(text="Informe o nome do lead antes de salvar.", fg=COLORS["red"])
            return
        lead_id = self.memory.add_lead(name, contact)
        if self.consent_var.get():
            self.memory.add_consent(lead_id, "manual", True, "Registrado no formulário de novo lead")
        self.consent_var.set(False)
        self.lead_name.delete(0, "end")
        self.lead_contact.delete(0, "end")
        self.refresh_leads()
        self.select_lead(lead_id)
        self.crm_hint.configure(
            text=f"Lead salvo localmente (#{lead_id}). Nenhuma mensagem foi enviada.",
            fg=COLORS["accent"],
        )

    def qualify_selected(self) -> None:
        detail = self._lead_detail()
        if not detail:
            self.crm_hint.configure(text="Selecione um lead antes de qualificar.", fg=COLORS["red"])
            return
        message = self.crm_message.get("1.0", "end").strip()
        if not message:
            self.crm_hint.configure(
                text="Informe a mensagem recebida do lead.", fg=COLORS["red"]
            )
            return
        result = qualify_lead(message)
        notes = f"score={result.score}; " + (
            ", ".join(result.reasons) or "sem sinais detectados"
        )
        self.memory.update_lead_stage(
            int(detail["id"]),
            result.stage,
            notes,
            score=result.score,
            next_action=next_step_for_stage(result.stage),
        )
        self.memory.add_conversation(int(detail["id"]), "lead", message)
        self.refresh_leads()
        self.select_lead(int(detail["id"]))
        self.crm_result.configure(
            text=(
                f"Etapa: {stage_label(result.stage)} • score {result.score}/100. "
                f"Razões: {', '.join(result.reasons) or 'sem sinais detectados'}."
            ),
            fg=COLORS["text"],
        )
        self.crm_hint.configure(
            text="Qualificação local concluída. O modelo não decide sozinho a etapa.",
            fg=COLORS["accent"],
        )

    def generate_followup(self) -> None:
        detail = self._lead_detail()
        if not detail:
            self.crm_hint.configure(
                text="Selecione um lead para gerar o follow-up.", fg=COLORS["red"]
            )
            return
        draft = draft_followup(
            str(detail["name"]),
            self.config_obj.product_name,
            str(detail["stage"]),
        )
        due = (datetime.now().astimezone() + timedelta(days=2)).isoformat()
        self.memory.add_followup(
            int(detail["id"]),
            due,
            "Retornar contato",
            draft=draft,
            channel="manual",
        )
        self.refresh_leads()
        self.select_lead(int(detail["id"]))
        self.crm_hint.configure(
            text="Rascunho salvo localmente. Não enviado.",
            fg=COLORS["amber"],
        )

    def register_consent(self) -> None:
        detail = self._lead_detail()
        if not detail:
            self.crm_hint.configure(
                text="Selecione um lead para registrar consentimento.", fg=COLORS["red"]
            )
            return
        self.memory.add_consent(
            int(detail["id"]),
            "manual",
            True,
            "Registrado pelo operador na interface desktop",
        )
        self.refresh_leads()
        self.select_lead(int(detail["id"]))
        self.crm_hint.configure(
            text="Consentimento registrado na auditoria local.",
            fg=COLORS["accent"],
        )

    # --------------------------------------------------------------- instagram
    def _build_instagram_page(self, page: tk.Frame) -> None:
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)
        header = self._page_header(
            page,
            "Instagram assistido",
            "Leitura pública, rascunhos e confirmação humana por ação",
        )
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(22, 14))
        tk.Label(
            header,
            text="●  Sem execução automática",
            bg=COLORS["amber_soft"],
            fg=COLORS["amber"],
            font=_font(9, bold=True),
            padx=12,
            pady=7,
        ).pack(side="right", anchor="n")

        body = tk.Frame(page, bg=COLORS["bg"])
        body.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 18))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, minsize=440)
        body.grid_rowconfigure(0, weight=1)

        left = _card(body)
        left.grid(row=0, column=0, sticky="nsew")
        left_inner = tk.Frame(left, bg=COLORS["surface"])
        left_inner.pack(fill="both", expand=True, padx=16, pady=14)
        tk.Label(
            left_inner,
            text="Perfil público",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=_font(12, bold=True),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            left_inner,
            text=(
                "Informe @perfil ou a URL do perfil. A leitura usa o BrowserOS e "
                "somente o conteúdo público visível; nenhuma ação é executada."
            ),
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=_font(8),
            anchor="w",
            justify="left",
            wraplength=520,
        ).pack(anchor="w", pady=(3, 8))
        profile_row = tk.Frame(left_inner, bg=COLORS["surface"])
        profile_row.pack(fill="x")
        profile_row.grid_columnconfigure(0, weight=1)
        self.ig_profile = _entry(profile_row)
        self.ig_profile.grid(row=0, column=0, sticky="ew", padx=(0, 8), ipady=4)
        self.ig_read_button = _button(
            profile_row,
            "Ler perfil",
            self.read_instagram_profile,
        )
        self.ig_read_button.grid(row=0, column=1, sticky="e")
        self.ig_status = tk.Label(
            left_inner,
            text="Perfil ainda não lido.",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=_font(8),
            anchor="w",
            justify="left",
            wraplength=520,
        )
        self.ig_status.pack(anchor="w", pady=(8, 6))
        self.ig_text = _text(left_inner, height=12, state="disabled")
        self.ig_text.pack(fill="both", expand=True)
        actions = tk.Frame(left_inner, bg=COLORS["surface"])
        actions.pack(fill="x", pady=(9, 0))
        self.ig_plan_button = _button(
            actions,
            "Gerar plano",
            self.generate_instagram_plan,
            kind="secondary",
        )
        self.ig_plan_button.configure(state="disabled")
        self.ig_plan_button.pack(side="left")
        self.ig_clear_button = _button(
            actions,
            "Limpar leitura",
            self.clear_instagram,
            kind="ghost",
        )
        self.ig_clear_button.pack(side="left", padx=(8, 0))
        tk.Label(
            left_inner,
            text=(
                "Privacidade: a leitura é pontual e auditada. O agente não observa "
                "suas abas, cliques ou teclas em segundo plano."
            ),
            bg=COLORS["surface"],
            fg=COLORS["muted_2"],
            font=_font(8),
            anchor="w",
            justify="left",
            wraplength=520,
        ).pack(anchor="w", pady=(9, 0))

        right = _card(body)
        right.grid(row=0, column=1, sticky="nsew", padx=(14, 0))
        right_inner = tk.Frame(right, bg=COLORS["surface"])
        right_inner.pack(fill="both", expand=True, padx=16, pady=14)
        tk.Label(
            right_inner,
            text="Plano assistido",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=_font(12, bold=True),
            anchor="w",
        ).pack(anchor="w")
        self.ig_summary = tk.Label(
            right_inner,
            text="Gere um plano após ler um perfil.",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=_font(8),
            anchor="w",
            justify="left",
            wraplength=400,
        )
        self.ig_summary.pack(anchor="w", pady=(3, 8))
        for label, attribute, height in (
            ("Mensagem inicial (DM)", "ig_message", 3),
            ("Comentário sugerido", "ig_comment", 3),
            ("Objeção: já usa outro app", "ig_objection", 3),
            ("Ritmo, checklist e limites", "ig_notes", 4),
        ):
            tk.Label(
                right_inner,
                text=label,
                bg=COLORS["surface"],
                fg=COLORS["muted_2"],
                font=_font(8, bold=True),
                anchor="w",
            ).pack(anchor="w", pady=(5, 2))
            widget = _text(right_inner, height=height, state="disabled")
            widget.pack(fill="x")
            setattr(self, attribute, widget)
        plan_actions = tk.Frame(right_inner, bg=COLORS["surface"])
        plan_actions.pack(fill="x", pady=(9, 0))
        self.ig_prepare_button = _button(
            plan_actions,
            "Preparar ações pendentes",
            self.prepare_instagram_actions,
        )
        self.ig_prepare_button.configure(state="disabled")
        self.ig_prepare_button.pack(side="left")
        _button(
            plan_actions,
            "Copiar DM",
            lambda: self.copy_instagram_message(),
            kind="ghost",
        ).pack(side="left", padx=(8, 0))
        self.ig_hint = tk.Label(
            right_inner,
            text="A aprovação registra a decisão; o envio continua manual.",
            bg=COLORS["surface"],
            fg=COLORS["muted_2"],
            font=_font(8),
            anchor="w",
            justify="left",
            wraplength=400,
        )
        self.ig_hint.pack(anchor="w", pady=(8, 0))

        pending = _card(body)
        pending.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(12, 0))
        pending_header = tk.Frame(pending, bg=COLORS["surface"])
        pending_header.pack(fill="x", padx=14, pady=(10, 4))
        tk.Label(
            pending_header,
            text="Ações pendentes de confirmação",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=_font(10, bold=True),
        ).pack(side="left")
        self.ig_pending_hint = tk.Label(
            pending_header,
            text="",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=_font(8),
        )
        self.ig_pending_hint.pack(side="right")
        pending_body = tk.Frame(pending, bg=COLORS["surface"])
        pending_body.pack(fill="x", padx=12, pady=(0, 10))
        pending_body.grid_columnconfigure(0, weight=1)
        self.ig_pending_tree = ttk.Treeview(
            pending_body,
            columns=("id", "created", "action", "target", "status"),
            show="headings",
            selectmode="browse",
            height=4,
        )
        for column, (label, width) in (
            ("id", ("ID", 44)),
            ("created", ("Hora", 120)),
            ("action", ("Ação", 120)),
            ("target", ("Contexto", 360)),
            ("status", ("Status", 90)),
        ):
            self.ig_pending_tree.heading(column, text=label, anchor="w")
            self.ig_pending_tree.column(column, width=width, minwidth=40, anchor="w")
        self.ig_pending_tree.grid(row=0, column=0, sticky="ew")
        pending_buttons = tk.Frame(pending_body, bg=COLORS["surface"])
        pending_buttons.grid(row=0, column=1, sticky="e", padx=(10, 0))
        _button(
            pending_buttons,
            "Aprovar",
            lambda: self.decide_pending(True),
            kind="secondary",
        ).pack(pady=(0, 5))
        _button(
            pending_buttons,
            "Rejeitar",
            lambda: self.decide_pending(False),
            kind="danger",
        ).pack(pady=(0, 5))
        _button(
            pending_buttons,
            "Atualizar",
            self.refresh_pending_actions,
            kind="ghost",
        ).pack()

    def read_instagram_profile(self) -> None:
        raw = self.ig_profile.get().strip()
        try:
            url = normalize_profile_url(raw)
        except ValueError as exc:
            self.ig_status.configure(text=str(exc), fg=COLORS["red"])
            return
        confirmed = messagebox.askyesno(
            "Ler perfil público",
            f"Abrir e ler o perfil abaixo no BrowserOS?\n\n{url}\n\n"
            "A ação é somente leitura e será registrada na auditoria. "
            "Nenhum follow, comentário, repost ou DM será executado.",
            parent=self,
        )
        if not confirmed:
            return
        self.ig_read_button.configure(state="disabled")
        self.ig_status.configure(text="Lendo perfil público…", fg=COLORS["amber"])
        self.ig_profile.delete(0, "end")

        def worker() -> None:
            try:
                result = self.agent.read_page(url, explicit=True)
            except Exception as exc:
                self._post(self._instagram_read_failed, str(exc))
            else:
                self._post(self._instagram_read_done, result, url)

        threading.Thread(target=worker, daemon=True).start()

    def _instagram_read_done(self, result, url: str) -> None:
        if self._closing:
            return
        self.ig_read_button.configure(state="normal")
        self._instagram_text = str(result.text or "")
        self._instagram_url = url
        _set_text(
            self.ig_text,
            self._instagram_text or "A página não retornou texto legível.",
            disabled=True,
        )
        self.ig_status.configure(
            text=f"Perfil lido: {url} • {len(self._instagram_text)} caracteres.",
            fg=COLORS["accent"],
        )
        self.ig_plan_button.configure(state="normal")
        self.ig_summary.configure(
            text="Leitura concluída. Gere o plano para ver os rascunhos.",
            fg=COLORS["muted"],
        )
        self._instagram_plan = None
        self.ig_prepare_button.configure(state="disabled")
        self.refresh_audit()
        self._update_instagram_notes()

    def _instagram_read_failed(self, message: str) -> None:
        if self._closing:
            return
        self.ig_read_button.configure(state="normal")
        self.ig_status.configure(text=f"Falha na leitura: {message[:220]}", fg=COLORS["red"])
        self.refresh_audit()

    def generate_instagram_plan(self) -> None:
        if not self._instagram_text or not self._instagram_url:
            self.ig_status.configure(
                text="Leia um perfil antes de gerar o plano.", fg=COLORS["red"]
            )
            return
        try:
            style = analyze_style(self.memory.style_texts(50))
            plan = build_plan(
                self._instagram_url,
                self._instagram_text,
                product=self.config_obj.product_name,
                hour=datetime.now().hour,
                style=style,
                custom_knowledge=self.memory.knowledge_entries(100),
            )
        except Exception as exc:
            self.ig_status.configure(text=f"Falha ao gerar plano: {exc}", fg=COLORS["red"])
            return
        self._instagram_plan = plan
        self.ig_summary.configure(text=plan.summary(), fg=COLORS["text"])
        _set_text(self.ig_message, plan.initial_message, disabled=True)
        _set_text(self.ig_comment, plan.comment_draft, disabled=True)
        _set_text(self.ig_objection, plan.objection_guidance, disabled=True)
        notes = [
            f"Saudação atual: {greeting_for_hour()}.",
            f"Ritmo estimado de digitação: {plan.delay_seconds}s. Nada é enviado automaticamente.",
            "Checklist de comparativo:",
            *[f"• {item}" for item in plan.checklist],
        ]
        if plan.notes:
            notes.extend(["", "Observações:", *[f"• {item}" for item in plan.notes]])
        _set_text(self.ig_notes, "\n".join(notes), disabled=True)
        self.ig_prepare_button.configure(state="normal")
        self.ig_hint.configure(
            text=(
                "Plano gerado. Ao preparar, cada ação vira uma pendência de confirmação; "
                "o app não executa follow, comentário, repost ou DM."
            ),
            fg=COLORS["muted"],
        )
        self.memory.audit(
            "instagram.plan",
            plan.insight.url[:300],
            "ok",
            f"handle={plan.insight.handle}; actions={len(plan.actions)}; execution=disabled",
        )

    def prepare_instagram_actions(self) -> None:
        plan = self._instagram_plan
        if plan is None:
            self.ig_hint.configure(text="Gere um plano antes de preparar ações.", fg=COLORS["red"])
            return
        existing = {
            str(row[3]) for row in self.memory.list_pending_actions("pending")
        }
        created = 0
        for action in plan.actions:
            payload = action.payload(plan.insight)
            marker = f'"action": "{action.action}"'
            if any(plan.insight.handle in item and marker in item for item in existing):
                continue
            self.memory.create_pending_action(
                action.action,
                payload,
                action.rationale,
            )
            created += 1
        self.refresh_pending_actions()
        self.ig_hint.configure(
            text=(
                f"{created} ação(ões) registrada(s) como pendente(s). "
                "Aprovar apenas registra a decisão; execução externa desativada."
            ),
            fg=COLORS["amber"],
        )

    def refresh_pending_actions(self) -> None:
        if not hasattr(self, "ig_pending_tree"):
            return
        for item in self.ig_pending_tree.get_children():
            self.ig_pending_tree.delete(item)
        rows = self.memory.list_pending_actions("pending")
        for row in rows:
            pending_id, created, action, payload, _rationale, status = row
            self.ig_pending_tree.insert(
                "",
                "end",
                values=(
                    pending_id,
                    _format_time(str(created)),
                    action,
                    str(payload)[:180],
                    status,
                ),
            )
        self.ig_pending_hint.configure(
            text=f"{len(rows)} pendência(s). Execução externa desativada."
        )

    def decide_pending(self, approved: bool) -> None:
        selection = self.ig_pending_tree.selection()
        if not selection:
            self.ig_hint.configure(text="Selecione uma pendência.", fg=COLORS["red"])
            return
        values = self.ig_pending_tree.item(selection[0], "values")
        try:
            pending_id = int(values[0])
        except (IndexError, TypeError, ValueError):
            return
        verb = "aprovar" if approved else "rejeitar"
        if not messagebox.askyesno(
            "Confirmar decisão",
            f"Deseja {verb} a pendência #{pending_id}?\n\n"
            "A decisão será auditada. Nenhuma ação externa será executada nesta versão.",
            parent=self,
        ):
            return
        self.memory.decide_pending_action(
            pending_id,
            approved,
            f"{'Aprovada' if approved else 'Rejeitada'} na interface; execução externa desativada",
        )
        self.refresh_pending_actions()
        self.refresh_audit()
        self.ig_hint.configure(
            text=(
                f"Pendência #{pending_id} {'aprovada' if approved else 'rejeitada'} e auditada. "
                "Nenhum envio foi realizado."
            ),
            fg=COLORS["accent"] if approved else COLORS["amber"],
        )

    def copy_instagram_message(self) -> None:
        if self._instagram_plan is None:
            self.ig_hint.configure(text="Gere um plano antes de copiar.", fg=COLORS["red"])
            return
        self.clipboard_clear()
        self.clipboard_append(self._instagram_plan.initial_message)
        self.ig_hint.configure(text="Mensagem copiada para a área de transferência.", fg=COLORS["accent"])

    def clear_instagram(self) -> None:
        self._instagram_plan = None
        self._instagram_text = ""
        self._instagram_url = ""
        _set_text(self.ig_text, "", disabled=True)
        _set_text(self.ig_message, "", disabled=True)
        _set_text(self.ig_comment, "", disabled=True)
        _set_text(self.ig_objection, "", disabled=True)
        _set_text(self.ig_notes, "", disabled=True)
        self.ig_status.configure(text="Perfil ainda não lido.", fg=COLORS["muted"])
        self.ig_summary.configure(text="Gere um plano após ler um perfil.", fg=COLORS["muted"])
        self.ig_plan_button.configure(state="disabled")
        self.ig_prepare_button.configure(state="disabled")
        self.ig_hint.configure(
            text="A aprovação registra a decisão; o envio continua manual.",
            fg=COLORS["muted_2"],
        )

    def _update_instagram_notes(self) -> None:
        if not hasattr(self, "ig_notes"):
            return
        if self._instagram_plan is not None:
            return
        style = analyze_style(self.memory.style_texts(50))
        _set_text(
            self.ig_notes,
            (
                f"Saudação atual: {greeting_for_hour()}.\n"
                f"Estilo aprendido: {style.sample_count} amostra(s) autorizada(s).\n"
                "Checklist de comparativo:\n"
                + "\n".join(f"• {item}" for item in comparison_checklist())
            ),
            disabled=True,
        )

    # -------------------------------------------------------------- aprendizado
    def _build_learning_page(self, page: tk.Frame) -> None:
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)
        header = self._page_header(
            page,
            "Aprendizado e playbook",
            "Estilo autorizado, objeções, ganchos e limites éticos",
        )
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(22, 14))
        body = tk.Frame(page, bg=COLORS["bg"])
        body.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 18))
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, minsize=500)
        body.grid_rowconfigure(0, weight=1)

        style_card = _card(body)
        style_card.grid(row=0, column=0, sticky="nsew")
        style_inner = tk.Frame(style_card, bg=COLORS["surface"])
        style_inner.pack(fill="both", expand=True, padx=16, pady=14)
        tk.Label(
            style_inner,
            text="Estilo de escrita (opt-in)",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=_font(12, bold=True),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            style_inner,
            text=(
                "Salve exemplos que você autoriza. O perfil orienta apenas rascunhos. "
                "O agente não captura teclas, abas ou navegação em segundo plano."
            ),
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=_font(8),
            anchor="w",
            justify="left",
            wraplength=520,
        ).pack(anchor="w", pady=(3, 8))
        self.style_input = _text(style_inner, height=8)
        self.style_input.pack(fill="x")
        style_actions = tk.Frame(style_inner, bg=COLORS["surface"])
        style_actions.pack(fill="x", pady=(8, 0))
        _button(style_actions, "Salvar amostra", self.save_style_sample).pack(side="left")
        _button(
            style_actions,
            "Importar minhas mensagens",
            self.import_style_messages,
            kind="secondary",
        ).pack(side="left", padx=(8, 0))
        _button(
            style_actions,
            "Limpar amostras",
            self.clear_style_samples,
            kind="danger",
        ).pack(side="right")
        self.style_summary = tk.Label(
            style_inner,
            text="Nenhuma amostra salva.",
            bg=COLORS["input"],
            fg=COLORS["muted"],
            font=_font(9),
            anchor="w",
            justify="left",
            wraplength=520,
            padx=10,
            pady=9,
        )
        self.style_summary.pack(fill="x", pady=(10, 0))
        tk.Label(
            style_inner,
            text=(
                "Limite: o estilo é uma referência de tom e tamanho. Ele não autoriza "
                "personificar você nem copiar dados pessoais das amostras."
            ),
            bg=COLORS["surface"],
            fg=COLORS["muted_2"],
            font=_font(8),
            anchor="w",
            justify="left",
            wraplength=520,
        ).pack(anchor="w", pady=(8, 0))

        knowledge_card = _card(body)
        knowledge_card.grid(row=0, column=1, sticky="nsew", padx=(14, 0))
        knowledge_inner = tk.Frame(knowledge_card, bg=COLORS["surface"])
        knowledge_inner.pack(fill="both", expand=True, padx=16, pady=14)
        tk.Label(
            knowledge_inner,
            text="Conhecimento comercial",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=_font(12, bold=True),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            knowledge_inner,
            text=(
                "Adicione objeções, ganchos e informações verificáveis. O playbook "
                "embutido traz orientações éticas; o modelo não inventa preço, "
                "escassez ou comparativo."
            ),
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=_font(8),
            anchor="w",
            justify="left",
            wraplength=460,
        ).pack(anchor="w", pady=(3, 8))
        form = tk.Frame(knowledge_inner, bg=COLORS["surface"])
        form.pack(fill="x")
        form.grid_columnconfigure(1, weight=1)
        tk.Label(form, text="Título", bg=COLORS["surface"], fg=COLORS["muted"], font=_font(8)).grid(
            row=0, column=0, sticky="w", padx=(0, 6)
        )
        self.knowledge_title = _entry(form)
        self.knowledge_title.grid(row=0, column=1, sticky="ew", ipady=3)
        tk.Label(form, text="Tags", bg=COLORS["surface"], fg=COLORS["muted"], font=_font(8)).grid(
            row=0, column=2, sticky="w", padx=(10, 6)
        )
        self.knowledge_tags = _entry(form, 18)
        self.knowledge_tags.grid(row=0, column=3, sticky="ew", ipady=3)
        self.knowledge_content = _text(knowledge_inner, height=5)
        self.knowledge_content.pack(fill="x", pady=(7, 6))
        knowledge_actions = tk.Frame(knowledge_inner, bg=COLORS["surface"])
        knowledge_actions.pack(fill="x")
        _button(knowledge_actions, "Adicionar conhecimento", self.add_knowledge).pack(side="left")
        _button(
            knowledge_actions,
            "Desativar selecionado",
            self.disable_knowledge,
            kind="ghost",
        ).pack(side="right")
        self.knowledge_tree = ttk.Treeview(
            knowledge_inner,
            columns=("id", "title", "tags"),
            show="headings",
            selectmode="browse",
            height=6,
        )
        for column, (label, width) in (
            ("id", ("ID", 42)),
            ("title", ("Título", 250)),
            ("tags", ("Tags", 150)),
        ):
            self.knowledge_tree.heading(column, text=label, anchor="w")
            self.knowledge_tree.column(column, width=width, minwidth=40, anchor="w")
        self.knowledge_tree.pack(fill="x", pady=(8, 6))
        self.builtin_summary = tk.Label(
            knowledge_inner,
            text="",
            bg=COLORS["input"],
            fg=COLORS["muted"],
            font=_font(8),
            anchor="w",
            justify="left",
            wraplength=460,
            padx=9,
            pady=7,
        )
        self.builtin_summary.pack(fill="x")

    def save_style_sample(self) -> None:
        text = _get_text(self.style_input)
        if not text:
            self.style_summary.configure(
                text="Escreva ou cole uma amostra antes de salvar.", fg=COLORS["red"]
            )
            return
        try:
            self.memory.add_style_sample(text, "manual")
        except ValueError as exc:
            self.style_summary.configure(text=str(exc), fg=COLORS["red"])
            return
        self.style_input.delete("1.0", "end")
        self.refresh_learning()
        self.style_summary.configure(
            text=f"Amostra salva. {analyze_style(self.memory.style_texts(50)).summary()}",
            fg=COLORS["accent"],
        )
        self._update_instagram_notes()

    def import_style_messages(self) -> None:
        messages = self.memory.recent_user_messages(20)
        if not messages:
            self.style_summary.configure(
                text="Ainda não há mensagens suas no histórico para importar.",
                fg=COLORS["muted"],
            )
            return
        if not messagebox.askyesno(
            "Importar mensagens",
            f"Importar {len(messages)} mensagem(ns) suas do histórico local?\n\n"
            "As amostras ficam no SQLite desta máquina e podem ser apagadas a qualquer momento.",
            parent=self,
        ):
            return
        added = 0
        for message in messages:
            try:
                self.memory.add_style_sample(message, "historico")
            except ValueError:
                continue
            added += 1
        self.refresh_learning()
        self.style_summary.configure(
            text=f"{added} amostra(s) importada(s) do histórico. Revise e apague se necessário.",
            fg=COLORS["accent"],
        )
        self._update_instagram_notes()

    def clear_style_samples(self) -> None:
        if not messagebox.askyesno(
            "Limpar amostras",
            "Apagar todas as amostras de estilo salvas neste computador?",
            parent=self,
        ):
            return
        removed = self.memory.clear_style_samples()
        self.refresh_learning()
        self.style_summary.configure(
            text=f"{removed} amostra(s) removida(s). O agente volta à persona padrão.",
            fg=COLORS["amber"],
        )
        self._update_instagram_notes()

    def refresh_learning(self) -> None:
        if not hasattr(self, "style_summary"):
            return
        profile = analyze_style(self.memory.style_texts(50))
        self.style_summary.configure(text=profile.summary(), fg=COLORS["text"])
        for item in self.knowledge_tree.get_children():
            self.knowledge_tree.delete(item)
        for row in self.memory.list_knowledge(100):
            if not row[4]:
                continue
            self.knowledge_tree.insert("", "end", values=(row[0], row[1], row[2] or "—"))
        categories: dict[str, int] = {}
        for entry in BUILTIN_ENTRIES:
            categories[entry.category] = categories.get(entry.category, 0) + 1
        summary = "Playbook embutido: " + ", ".join(
            f"{count} {category}" for category, count in sorted(categories.items())
        )
        summary += (
            ". Gatilhos só podem ser usados quando forem verdadeiros; escassez, "
            "prova social e comparações exigem evidência e confirmação humana."
        )
        self.builtin_summary.configure(text=summary)

    def add_knowledge(self) -> None:
        title = self.knowledge_title.get().strip()
        content = _get_text(self.knowledge_content)
        tags = self.knowledge_tags.get().strip()
        try:
            self.memory.add_knowledge(title, content, tags)
        except ValueError as exc:
            self.builtin_summary.configure(text=str(exc), fg=COLORS["red"])
            return
        self.knowledge_title.delete(0, "end")
        self.knowledge_tags.delete(0, "end")
        self.knowledge_content.delete("1.0", "end")
        self.refresh_learning()
        self.builtin_summary.configure(
            text="Conhecimento salvo localmente e disponível para os próximos rascunhos.",
            fg=COLORS["accent"],
        )

    def disable_knowledge(self) -> None:
        selection = self.knowledge_tree.selection()
        if not selection:
            self.builtin_summary.configure(
                text="Selecione um conhecimento para desativar.", fg=COLORS["red"]
            )
            return
        values = self.knowledge_tree.item(selection[0], "values")
        try:
            knowledge_id = int(values[0])
        except (IndexError, TypeError, ValueError):
            return
        if not messagebox.askyesno(
            "Desativar conhecimento",
            f"Desativar o conhecimento #{knowledge_id}? Ele deixará de orientar o agente.",
            parent=self,
        ):
            return
        self.memory.delete_knowledge(knowledge_id)
        self.refresh_learning()
        self.builtin_summary.configure(text="Conhecimento desativado.", fg=COLORS["amber"])

    # ------------------------------------------------------------------ status
    def _build_status_page(self, page: tk.Frame) -> None:
        page.grid_rowconfigure(1, weight=1)
        page.grid_columnconfigure(0, weight=1)
        header = self._page_header(
            page,
            "Status dos serviços",
            "Diagnóstico local, privacidade e auditoria",
        )
        header.grid(row=0, column=0, sticky="ew", padx=24, pady=(22, 14))
        actions = tk.Frame(header, bg=COLORS["bg"])
        actions.pack(side="right", anchor="n")
        _button(actions, "Atualizar status", self.refresh_health_async).pack(side="left")
        _button(
            actions,
            "Iniciar serviços",
            self.start_services_async,
            kind="secondary",
        ).pack(side="left", padx=(8, 0))
        _button(
            actions,
            "Executar análise REA",
            self.run_rea_async,
            kind="secondary",
        ).pack(side="left", padx=(8, 0))
        body = tk.Frame(page, bg=COLORS["bg"])
        body.grid(row=1, column=0, sticky="nsew", padx=24, pady=(0, 18))
        body.grid_columnconfigure(0, weight=1)
        body.grid_rowconfigure(1, weight=1)
        health_grid = tk.Frame(body, bg=COLORS["bg"])
        health_grid.grid(row=0, column=0, sticky="ew")
        for column in range(3):
            health_grid.grid_columnconfigure(column, weight=1, uniform="health")
        self.health_cards: dict[str, dict[str, Any]] = {}
        cards = (
            ("ollama", "Ollama", "API local"),
            ("model", "Modelo", self.config_obj.ollama_model),
            ("browseros", "BrowserOS MCP", "Navegador do agente"),
            ("memory", "Memória SQLite", "Banco local"),
            ("rea", "REA", "Análise local"),
            ("instagram", "Instagram/Meta", "Graph API oficial"),
            ("privacy", "Privacidade", "Dados processados localmente"),
        )
        for index, (key, title, detail) in enumerate(cards):
            card = _card(health_grid)
            card.grid(
                row=index // 3,
                column=index % 3,
                sticky="nsew",
                padx=(0 if index % 3 == 0 else 7, 7 if index % 3 < 2 else 0),
                pady=(0, 10),
            )
            inner = tk.Frame(card, bg=COLORS["surface"])
            inner.pack(fill="both", expand=True, padx=14, pady=12)
            top = tk.Frame(inner, bg=COLORS["surface"])
            top.pack(fill="x")
            dot = Dot(top)
            dot.pack(side="left")
            tk.Label(
                top,
                text=title,
                bg=COLORS["surface"],
                fg=COLORS["text"],
                font=_font(10, bold=True),
                anchor="w",
            ).pack(side="left", padx=(7, 0))
            status_label = tk.Label(
                top,
                text="Verificando…",
                bg=COLORS["surface"],
                fg=COLORS["muted"],
                font=_font(8, bold=True),
                anchor="e",
            )
            status_label.pack(side="right")
            detail_label = tk.Label(
                inner,
                text=detail,
                bg=COLORS["surface"],
                fg=COLORS["muted"],
                font=_font(8),
                anchor="w",
                justify="left",
                wraplength=280,
            )
            detail_label.pack(anchor="w", pady=(8, 0))
            self.health_cards[key] = {
                "dot": dot,
                "status": status_label,
                "detail": detail_label,
            }
        lower = tk.Frame(body, bg=COLORS["bg"])
        lower.grid(row=1, column=0, sticky="nsew", pady=(6, 0))
        lower.grid_columnconfigure(0, weight=1)
        lower.grid_columnconfigure(1, minsize=400)
        lower.grid_rowconfigure(0, weight=1)
        audit_card = _card(lower)
        audit_card.grid(row=0, column=0, sticky="nsew")
        audit_header = tk.Frame(audit_card, bg=COLORS["surface"])
        audit_header.pack(fill="x", padx=14, pady=(12, 6))
        tk.Label(
            audit_header,
            text="Auditoria recente",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=_font(11, bold=True),
        ).pack(side="left")
        self.status_hint = tk.Label(
            audit_header,
            text="",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=_font(8),
        )
        self.status_hint.pack(side="right")
        audit_holder = tk.Frame(audit_card, bg=COLORS["surface"])
        audit_holder.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.audit_tree = ttk.Treeview(
            audit_holder,
            columns=("time", "action", "target", "status"),
            show="headings",
            selectmode="browse",
        )
        for column, (label, width) in (
            ("time", ("Hora", 120)),
            ("action", ("Evento", 190)),
            ("target", ("Alvo", 200)),
            ("status", ("Status", 90)),
        ):
            self.audit_tree.heading(column, text=label, anchor="w")
            self.audit_tree.column(column, width=width, minwidth=60, anchor="w")
        self.audit_tree.tag_configure("error", foreground=COLORS["red"])
        self.audit_tree.tag_configure("pending", foreground=COLORS["amber"])
        self.audit_tree.tag_configure("ok", foreground=COLORS["text"])
        audit_scroll = ttk.Scrollbar(
            audit_holder,
            orient="vertical",
            command=self.audit_tree.yview,
            style="Vertical.TScrollbar",
        )
        self.audit_tree.configure(yscrollcommand=audit_scroll.set)
        self.audit_tree.pack(side="left", fill="both", expand=True)
        audit_scroll.pack(side="right", fill="y")
        rea_card = _card(lower)
        rea_card.grid(row=0, column=1, sticky="nsew", padx=(14, 0))
        rea_inner = tk.Frame(rea_card, bg=COLORS["surface"])
        rea_inner.pack(fill="both", expand=True, padx=16, pady=14)
        tk.Label(
            rea_inner,
            text="Evidências REA",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=_font(11, bold=True),
            anchor="w",
        ).pack(anchor="w")
        tk.Label(
            rea_inner,
            text="Inventário local com hashes, allowlist e limitações explícitas.",
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=_font(8),
            anchor="w",
            justify="left",
            wraplength=340,
        ).pack(anchor="w", pady=(4, 10))
        self.rea_text = tk.Label(
            rea_inner,
            text="Nenhuma análise REA executada ainda.",
            bg=COLORS["input"],
            fg=COLORS["muted"],
            font=_font(9),
            anchor="w",
            justify="left",
            wraplength=340,
            padx=10,
            pady=9,
        )
        self.rea_text.pack(fill="x")
        self._update_rea_text()

    def _apply_health(self, health: dict[str, dict]) -> None:
        self.health_data = health
        for key, card in self.health_cards.items():
            item = health.get(key, {})
            status = str(item.get("status", "unavailable"))
            color = STATUS_COLORS.get(status, COLORS["muted"])
            card["dot"].set(color)
            card["status"].configure(
                text=STATUS_LABELS.get(status, "Indisponível"),
                fg=color,
            )
            card["detail"].configure(text=str(item.get("detail", "Sem informação.")))
        model = health.get("model", {})
        if model:
            self.sidebar_model.configure(
                text=self.config_obj.ollama_model,
                fg=STATUS_COLORS.get(str(model.get("status")), COLORS["text"]),
            )
        self.status_hint.configure(text="Status atualizado.", fg=COLORS["muted"])

    def refresh_health_async(self) -> None:
        if self._health_busy:
            return
        self._health_busy = True
        self.status_hint.configure(text="Verificando serviços…", fg=COLORS["muted"])
        for card in self.health_cards.values():
            card["status"].configure(text="Verificando…", fg=COLORS["muted"])
            card["dot"].set(COLORS["muted_2"])
        threading.Thread(target=self._health_worker, daemon=True).start()

    def _health_worker(self) -> None:
        try:
            health = self.supervisor.health(deep=True)
        except Exception as exc:
            self._post(self._health_failed, str(exc))
        else:
            self._post(self._health_done, health)

    def _health_done(self, health: dict[str, dict]) -> None:
        self._health_busy = False
        if not self._closing:
            self._apply_health(health)

    def _health_failed(self, message: str) -> None:
        self._health_busy = False
        if not self._closing:
            self.status_hint.configure(text=f"Falha no diagnóstico: {message}", fg=COLORS["red"])

    def start_services_async(self) -> None:
        confirmed = messagebox.askyesno(
            "Iniciar serviços locais",
            "Deseja tentar iniciar Ollama e BrowserOS se ainda não estiverem em execução?\n\n"
            "Processos já ativos não serão duplicados.",
            parent=self,
        )
        if not confirmed:
            return
        self.status_hint.configure(text="Iniciando serviços locais…", fg=COLORS["amber"])
        threading.Thread(target=self._start_services_worker, daemon=True).start()

    def _start_services_worker(self) -> None:
        try:
            results = self.supervisor.start_services()
        except Exception as exc:
            self._post(self._start_services_failed, str(exc))
        else:
            self._post(self._start_services_done, results)

    def _start_services_done(self, results: list[dict[str, str]]) -> None:
        if self._closing:
            return
        text = "; ".join(f"{item['name']}: {item['detail']}" for item in results)
        self.status_hint.configure(text=text, fg=COLORS["muted"])
        self.refresh_audit()
        self.after(800, self.refresh_health_async)

    def _start_services_failed(self, message: str) -> None:
        if not self._closing:
            self.status_hint.configure(
                text=f"Falha ao iniciar serviços: {message[:160]}",
                fg=COLORS["red"],
            )

    def run_rea_async(self) -> None:
        self.status_hint.configure(text="Executando análise REA local…", fg=COLORS["amber"])
        self.rea_text.configure(text="Analisando componentes locais…", fg=COLORS["muted"])
        threading.Thread(target=self._rea_worker, daemon=True).start()

    def _rea_worker(self) -> None:
        try:
            result = analyze_project(config=self.config_obj)
        except Exception as exc:
            self._post(self._rea_failed, str(exc))
        else:
            self._post(self._rea_done, result)

    def _rea_done(self, result: dict) -> None:
        if self._closing:
            return
        report = result["report"]
        self.rea_text.configure(
            text=f"{rea_summary(report)}\n\nRelatório: {result['path']}",
            fg=COLORS["text"],
        )
        self.status_hint.configure(text="Análise REA concluída.", fg=COLORS["accent"])
        self.refresh_audit()

    def _rea_failed(self, message: str) -> None:
        if self._closing:
            return
        self.rea_text.configure(text=f"Falha na análise: {message}", fg=COLORS["red"])
        self.status_hint.configure(text="Falha na análise REA.", fg=COLORS["red"])

    def _update_rea_text(self) -> None:
        if not hasattr(self, "rea_text"):
            return
        report = latest_report(self.config_obj)
        if report:
            self.rea_text.configure(
                text=rea_summary(report),
                fg=COLORS["text"],
            )
        else:
            self.rea_text.configure(
                text="Nenhuma análise REA executada ainda. Use o botão acima.",
                fg=COLORS["muted"],
            )

    def refresh_audit(self) -> None:
        if not hasattr(self, "audit_tree"):
            return
        for item in self.audit_tree.get_children():
            self.audit_tree.delete(item)
        for row in self.memory.list_audit(30):
            created, _actor, action, target, status, _detail = row
            tag = "error" if status in {"error", "blocked"} else "pending" if status in {"pending", "attention"} else "ok"
            self.audit_tree.insert(
                "",
                "end",
                values=(_format_time(str(created)), action, target or "—", status),
                tags=(tag,),
            )

    # ------------------------------------------------------------------ janela
    def _enable_dark_titlebar(self) -> None:
        try:
            import ctypes

            hwnd = ctypes.windll.user32.GetParent(self.winfo_id())
            value = ctypes.c_int(1)
            ctypes.windll.dwmapi.DwmSetWindowAttribute(
                hwnd,
                20,
                ctypes.byref(value),
                ctypes.sizeof(value),
            )
        except Exception:
            pass

    def _on_close(self) -> None:
        self._closing = True
        try:
            self.memory.close()
        except Exception:
            pass
        self.destroy()


def run() -> None:
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    app = App()
    app.mainloop()
