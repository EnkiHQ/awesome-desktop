"""The main window: a compact dark panel with status, stats, a summary card and actions.

Only widgets live here. The game logic stays in :mod:`dib.ui`, which fills the string
variables and supplies the button callbacks, so the panel can also be previewed on its own.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

BG = '#0e1a18'
CARD = '#152623'
TEXT = '#e8f5f0'
MUTED = '#8aa69e'
ACCENT = '#69ddb3'
WARN = '#f2b880'
GOLD = '#f2ca87'
FONT = 'Microsoft YaHei UI'
CONTENT_WIDTH = 300
NUMBERS = 'Segoe UI Semibold'

# kind -> (background, hover, foreground)
KINDS = {
    'primary': (ACCENT, '#86eac8', BG),
    'soft': ('#1f3733', '#294843', TEXT),
    'on': ('#1f5444', '#28695a', '#b6fbe0'),
    'off': ('#25322f', '#2f3f3b', MUTED),
    'ghost': (BG, '#18302c', MUTED),
    'gold': (BG, '#18302c', GOLD),
}


class Pill(tk.Label):
    """A flat button with hover feedback; ``set`` changes its text, look and availability."""

    def __init__(self, parent, text, command, kind='soft', *, bold=False, padx=12, pady=6):
        super().__init__(parent, text=text, font=(FONT, 9, 'bold' if bold else 'normal'), cursor='hand2',
                         padx=padx, pady=pady, bd=0)
        self.command = command
        self.kind = kind
        self.enabled = True
        self.hover = False
        self.bind('<Enter>', lambda event: self._hover(True))
        self.bind('<Leave>', lambda event: self._hover(False))
        self.bind('<ButtonRelease-1>', self._release)
        self._paint()

    def set(self, text=None, kind=None, enabled=None):
        if text is not None:
            self.configure(text=text)
        if kind is not None:
            self.kind = kind
        if enabled is not None:
            self.enabled = enabled
        self._paint()

    def _hover(self, value):
        self.hover = value
        self._paint()

    def _release(self, event):
        inside = 0 <= event.x < self.winfo_width() and 0 <= event.y < self.winfo_height()
        if self.enabled and inside and self.command:
            self.command()

    def _paint(self):
        background, hover, foreground = KINDS[self.kind]
        if not self.enabled:
            self.configure(bg=KINDS['off'][0], fg='#5d726c', cursor='arrow')
            return
        self.configure(bg=hover if self.hover else background, fg=foreground, cursor='hand2')


def configure_styles(root):
    """ttk styles for the donation and update dialogs (the main window uses plain Tk widgets)."""
    style = ttk.Style(root)
    style.theme_use('clam')
    style.configure('Panel.TFrame', background=BG)
    style.configure('Table.TLabel', background=BG, foreground=TEXT, font=(FONT, 9))
    style.configure('Table.TButton', padding=(11, 6), font=(FONT, 9), background=CARD, foreground=TEXT,
                    borderwidth=0, focusthickness=1, focuscolor=ACCENT)
    style.map('Table.TButton', background=[('active', '#1d3531'), ('pressed', '#24423c')])
    style.configure('Dark.Vertical.TScrollbar', background='#2b4a44', troughcolor=CARD, bordercolor=CARD,
                    lightcolor='#2b4a44', darkcolor='#2b4a44', arrowcolor=MUTED, relief='flat', gripcount=0)
    style.map('Dark.Vertical.TScrollbar', background=[('active', '#3a645b'), ('pressed', '#3a645b')])


class MainPanel:
    """Build the window and expose the variables and buttons the game updates."""

    def __init__(self, root, version, callbacks):
        configure_styles(root)
        root.configure(bg=BG)
        self.root = root
        self.status = tk.StringVar(root, value='正在摆球…')
        self.time_title = tk.StringVar(root, value='本局用时')
        self.time_value = tk.StringVar(root, value='00:00')
        self.count_title = tk.StringVar(root, value='图标入袋')
        self.count_value = tk.StringVar(root, value='—')
        self.remaining_title = tk.StringVar(root, value='剩余图标')
        self.remaining_value = tk.StringVar(root, value='—')
        self.rank_text = tk.StringVar(root)
        self.update_feedback = tk.StringVar(root)

        shell = tk.Frame(root, bg=BG, padx=16, pady=14)
        shell.pack(fill='both', expand=True)
        # A fixed content width: texts wrap inside it instead of stretching the window.
        tk.Frame(shell, width=CONTENT_WIDTH, height=0, bg=BG).pack()

        head = tk.Frame(shell, bg=BG)
        head.pack(fill='x')
        tk.Label(head, text='桌面图标台球', font=(FONT, 12, 'bold'), fg=TEXT, bg=BG).pack(side='left')
        tk.Label(head, text=f'v{version}', font=(FONT, 8), fg=MUTED, bg=BG).pack(side='right', pady=(4, 0))

        status = tk.Frame(shell, bg=BG)
        status.pack(fill='x', pady=(8, 10))
        self.dot = tk.Canvas(status, width=10, height=10, bg=BG, highlightthickness=0)
        self.dot_shape = self.dot.create_oval(1, 1, 9, 9, fill=ACCENT, outline='')
        self.dot.pack(side='left', padx=(1, 8))
        self.status_label = tk.Label(status, textvariable=self.status, font=(FONT, 9), fg=TEXT, bg=BG,
                                     anchor='w', justify='left', wraplength=CONTENT_WIDTH - 20)
        self.status_label.pack(side='left', fill='x', expand=True)

        stats = tk.Frame(shell, bg=CARD, padx=14, pady=10)
        stats.pack(fill='x')
        for column, (title, value) in enumerate(((self.time_title, self.time_value),
                                                 (self.count_title, self.count_value),
                                                 (self.remaining_title, self.remaining_value))):
            stats.columnconfigure(column, weight=1, uniform='stats')
            tk.Label(stats, textvariable=title, font=(FONT, 8), fg=MUTED, bg=CARD, anchor='w').grid(
                row=0, column=column, sticky='w')
            tk.Label(stats, textvariable=value, font=(NUMBERS, 19), fg=TEXT, bg=CARD, anchor='w').grid(
                row=1, column=column, sticky='w')

        info = tk.Frame(shell, bg=CARD, padx=14, pady=9)
        info.pack(fill='x', pady=(8, 0))
        tk.Label(info, textvariable=self.rank_text, font=(FONT, 9), fg=MUTED, bg=CARD, height=3, anchor='nw',
                 justify='left', wraplength=CONTENT_WIDTH - 28).pack(fill='x')

        actions = tk.Frame(shell, bg=BG)
        actions.pack(fill='x', pady=(12, 0))
        for column, weight in enumerate((3, 2, 2)):
            actions.columnconfigure(column, weight=weight, uniform='actions')
        self.restart_button = Pill(actions, '重新开始', callbacks['restart'], 'primary', bold=True)
        self.restart_button.grid(row=0, column=0, sticky='ew')
        self.guide_button = Pill(actions, '辅助线 开', callbacks['toggle_guide'], 'on')
        self.guide_button.grid(row=0, column=1, sticky='ew', padx=(6, 0))
        self.rank_button = Pill(actions, '排名', callbacks['toggle_rank'], 'off')
        self.rank_button.grid(row=0, column=2, sticky='ew', padx=(6, 0))

        foot = tk.Frame(shell, bg=BG)
        foot.pack(fill='x', pady=(10, 0))
        self.update_button = Pill(foot, '检查更新', lambda: callbacks['check_updates'](), 'ghost', padx=6, pady=3)
        self.update_button.pack(side='left')
        Pill(foot, '打赏', callbacks['donate'], 'gold', padx=6, pady=3).pack(side='left')
        Pill(foot, '退出', callbacks['quit'], 'ghost', padx=6, pady=3).pack(side='right')
        tk.Label(foot, textvariable=self.update_feedback, font=(FONT, 8), fg=MUTED, bg=BG).pack(side='left', padx=6)
        tk.Label(shell, text='Esc / Ctrl+Alt+X 退出并恢复桌面', font=(FONT, 8), fg='#58716a', bg=BG,
                 anchor='w').pack(fill='x', pady=(4, 0))

    def set_tone(self, tone):
        """Colour the status dot: ``ok`` normally, ``warn`` when something needs the player's attention."""
        self.dot.itemconfigure(self.dot_shape, fill=WARN if tone == 'warn' else ACCENT)
        self.status_label.configure(fg=WARN if tone == 'warn' else TEXT)


def show_update_dialog(root, current, info, entries, on_download):
    """A dark release-notes dialog. ``entries`` is the display list from ``release_entries``;
    ``on_download(dialog)`` opens the download and closes the dialog when it succeeds."""
    dialog = tk.Toplevel(root)
    dialog.title(f'发现新版本 {info["version"]}')
    dialog.configure(bg=BG)
    dialog.transient(root)
    dialog.resizable(False, False)
    shell = tk.Frame(dialog, bg=BG, padx=18, pady=16)
    shell.pack(fill='both', expand=True)

    tk.Label(shell, text='发现新版本', font=(FONT, 12, 'bold'), fg=TEXT, bg=BG).pack(anchor='w')
    versions = tk.Frame(shell, bg=BG)
    versions.pack(fill='x', pady=(4, 10))
    tk.Label(versions, text=f'v{current}', font=(FONT, 9), fg=MUTED, bg=BG).pack(side='left')
    tk.Label(versions, text='  →  ', font=(FONT, 9), fg=MUTED, bg=BG).pack(side='left')
    tk.Label(versions, text=f'v{info["version"]}', font=(NUMBERS, 11), fg=ACCENT, bg=BG).pack(side='left')

    card = tk.Frame(shell, bg=CARD)
    card.pack(fill='both', expand=True)
    notes = tk.Text(card, width=46, height=12, wrap='word', bg=CARD, fg=TEXT, relief='flat', bd=0,
                    highlightthickness=0, padx=14, pady=10, font=(FONT, 9), spacing3=3, cursor='arrow',
                    insertwidth=0, selectbackground='#2b4a44')
    scrollbar = ttk.Scrollbar(card, orient='vertical', command=notes.yview, style='Dark.Vertical.TScrollbar')
    notes.configure(yscrollcommand=scrollbar.set)
    scrollbar.pack(side='right', fill='y')
    notes.pack(side='left', fill='both', expand=True)
    notes.tag_configure('latest', font=(FONT, 10, 'bold'), foreground=ACCENT, spacing1=0)
    notes.tag_configure('older', font=(FONT, 10, 'bold'), foreground=TEXT, spacing1=8)
    notes.tag_configure('body', foreground='#c4d9d2')
    for index, entry in enumerate(entries):
        notes.insert('end', f'{entry["version"]}\n', 'latest' if index == 0 else 'older')
        notes.insert('end', (entry['notes'] or '暂无更新说明') + '\n', 'body')
    notes.configure(state='disabled')

    buttons = tk.Frame(shell, bg=BG)
    buttons.pack(fill='x', pady=(14, 0))
    Pill(buttons, '去更新', lambda: on_download(dialog), 'primary', bold=True, padx=18).pack(side='right')
    Pill(buttons, '稍后', dialog.destroy, 'soft', padx=16).pack(side='right', padx=(0, 8))
    dialog.bind('<Escape>', lambda event: dialog.destroy())

    # Align the dialog's right edge with the main window, just below it, and keep it on screen.
    dialog.update_idletasks()
    x = max(0, root.winfo_x() + root.winfo_width() - dialog.winfo_reqwidth())
    dialog.geometry(f'+{x}+{root.winfo_y() + root.winfo_height() + 10}')
    return dialog
