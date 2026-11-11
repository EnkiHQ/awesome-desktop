"""Windows made of plain Tk widgets: the main panel, the round-result dialog and the update dialog.

Only widgets live here. The game logic stays in :mod:`dib.ui`, which fills the string
variables and supplies the callbacks, so every window can also be previewed on its own.

The main panel has three layouts: ``card`` (the full panel), ``bar`` (one slim row to park
along a screen edge) and ``side`` (a slim column), so it can sit outside the table.
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
LAYOUTS = (('card', '卡片'), ('bar', '横条'), ('side', '竖条'))

# kind -> (background, hover, foreground)
KINDS = {
    'primary': (ACCENT, '#86eac8', BG),
    'soft': ('#1f3733', '#294843', TEXT),
    'on': ('#1f5444', '#28695a', '#b6fbe0'),
    'off': ('#25322f', '#2f3f3b', MUTED),
    'ghost': (BG, '#18302c', MUTED),
    'gold': (BG, '#18302c', GOLD),
}


def format_duration(milliseconds):
    """``MM:SS.cc`` (``H:MM:SS.cc`` from one hour) for a round time in whole milliseconds."""
    centiseconds = max(0, int(milliseconds)) // 10
    seconds, centiseconds = divmod(centiseconds, 100)
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    clock = f'{hours}:{minutes:02d}:{seconds:02d}' if hours else f'{minutes:02d}:{seconds:02d}'
    return f'{clock}.{centiseconds:02d}'


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
    """ttk styles for the dialogs (the main window uses plain Tk widgets)."""
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
    """Build the main window in one of three layouts and expose what the game updates.

    String variables live as long as the panel; the widgets are rebuilt when the layout changes,
    so button looks are kept in ``look`` and re-applied by :meth:`set_layout`.
    """

    DEFAULT_LOOK = {
        'guide': {'text': '辅助线 开', 'kind': 'on'},
        'rank': {'text': '排名', 'kind': 'off'},
        'hide': {'text': '隐藏', 'kind': 'soft'},
        'felt': {'text': '台面 开', 'kind': 'ghost'},
        'update': {'text': '检查更新', 'kind': 'ghost'},
    }

    def __init__(self, root, version, callbacks, layout='card', credit=''):
        configure_styles(root)
        root.configure(bg=BG)
        self.root = root
        self.version = version
        self.credit = credit
        self.callbacks = callbacks
        self.shell = None
        self.layout = None
        self.pills = {}
        self.look = {key: dict(value) for key, value in self.DEFAULT_LOOK.items()}
        self.tone = 'ok'
        self.status = tk.StringVar(root, value='正在摆球…')
        self.time_title = tk.StringVar(root, value='本局用时')
        self.time_value = tk.StringVar(root, value='00:00')
        self.count_title = tk.StringVar(root, value='图标入袋')
        self.count_value = tk.StringVar(root, value='—')
        self.remaining_title = tk.StringVar(root, value='剩余图标')
        self.remaining_value = tk.StringVar(root, value='—')
        self.rank_text = tk.StringVar(root)
        self.rank_first = tk.StringVar(root)
        self.update_feedback = tk.StringVar(root)
        self.set_layout(layout)

    # -- look of the buttons ---------------------------------------------------
    def set_look(self, key, text=None, kind=None, enabled=None):
        """Remember and apply a button's text, kind and availability (it survives a layout change)."""
        look = self.look.setdefault(key, {})
        for name, value in (('text', text), ('kind', kind), ('enabled', enabled)):
            if value is not None:
                look[name] = value
        pill = self.pills.get(key)
        if pill is not None and pill.winfo_exists():
            pill.set(text, kind, enabled)

    def is_enabled(self, key):
        return self.look.get(key, {}).get('enabled', True)

    def _pill(self, parent, key, text, command, kind='soft', **options):
        look = self.look.get(key, {})
        pill = Pill(parent, look.get('text', text), command, look.get('kind', kind), **options)
        if 'enabled' in look:
            pill.set(enabled=look['enabled'])
        self.pills[key] = pill
        return pill

    def set_tone(self, tone):
        """Colour the status dot: ``ok`` normally, ``warn`` when something needs the player's attention."""
        self.tone = tone
        self._paint_tone()

    def _paint_tone(self):
        if self.dot is not None and self.dot.winfo_exists():
            self.dot.itemconfigure(self.dot_shape, fill=WARN if self.tone == 'warn' else ACCENT)
            self.status_label.configure(fg=WARN if self.tone == 'warn' else TEXT)

    # -- layouts ---------------------------------------------------------------
    def set_layout(self, layout):
        if layout not in dict(LAYOUTS):
            layout = 'card'
        if self.shell is not None:
            self.shell.destroy()
        self.pills = {}
        self.dot = None
        self.shell = tk.Frame(self.root, bg=BG)
        self.shell.pack(fill='both', expand=True)
        # Compact layouts use the slim tool-window caption, which also keeps them off the taskbar.
        try:
            self.root.attributes('-toolwindow', layout != 'card')
        except tk.TclError:
            pass
        {'card': self._build_card, 'bar': self._build_bar, 'side': self._build_side}[layout]()
        self.layout = layout
        self._paint_tone()
        self.root.update_idletasks()

    def _credit(self, parent, prefix=''):
        """``prefix`` plus the author's handle; clicking the handle opens the author's page."""
        box = tk.Frame(parent, bg=parent.cget('bg'))
        tk.Label(box, text=prefix, font=(FONT, 8), fg=MUTED, bg=parent.cget('bg')).pack(side='left')
        link = tk.Label(box, text=self.credit, font=(FONT, 8), fg=ACCENT, bg=parent.cget('bg'), cursor='hand2')
        link.pack(side='left')
        link.bind('<ButtonRelease-1>', lambda event: self.callbacks['open_credit']())
        return box

    def _status_row(self, parent, wraplength, font_size=9):
        row = tk.Frame(parent, bg=BG)
        self.dot = tk.Canvas(row, width=10, height=10, bg=BG, highlightthickness=0)
        self.dot_shape = self.dot.create_oval(1, 1, 9, 9, fill=ACCENT, outline='')
        self.dot.pack(side='left', padx=(1, 8))
        self.status_label = tk.Label(row, textvariable=self.status, font=(FONT, font_size), fg=TEXT, bg=BG,
                                     anchor='w', justify='left', wraplength=wraplength)
        self.status_label.pack(side='left', fill='x', expand=True)
        return row

    def _stat(self, parent, title, value, *, size, background):
        box = tk.Frame(parent, bg=background)
        tk.Label(box, textvariable=title, font=(FONT, 8), fg=MUTED, bg=background, anchor='w').pack(anchor='w')
        tk.Label(box, textvariable=value, font=(NUMBERS, size), fg=TEXT, bg=background, anchor='w').pack(anchor='w')
        return box

    def _build_card(self):
        callbacks = self.callbacks
        shell = tk.Frame(self.shell, bg=BG, padx=16, pady=14)
        shell.pack(fill='both', expand=True)
        # A fixed content width: texts wrap inside it instead of stretching the window.
        tk.Frame(shell, width=CONTENT_WIDTH, height=0, bg=BG).pack()
        head = tk.Frame(shell, bg=BG)
        head.pack(fill='x')
        tk.Label(head, text='桌面图标台球', font=(FONT, 12, 'bold'), fg=TEXT, bg=BG).pack(side='left')
        self._credit(head, f'v{self.version}  ').pack(side='right', pady=(4, 0))
        self._status_row(shell, CONTENT_WIDTH - 20).pack(fill='x', pady=(8, 10))

        stats = tk.Frame(shell, bg=CARD, padx=14, pady=10)
        stats.pack(fill='x')
        for column, (title, value) in enumerate(((self.time_title, self.time_value),
                                                 (self.count_title, self.count_value),
                                                 (self.remaining_title, self.remaining_value))):
            stats.columnconfigure(column, weight=1, uniform='stats')
            self._stat(stats, title, value, size=19, background=CARD).grid(row=0, column=column, sticky='w')

        info = tk.Frame(shell, bg=CARD, padx=14, pady=9)
        info.pack(fill='x', pady=(8, 0))
        tk.Label(info, textvariable=self.rank_text, font=(FONT, 9), fg=MUTED, bg=CARD, height=3, anchor='nw',
                 justify='left', wraplength=CONTENT_WIDTH - 28).pack(fill='x')

        actions = tk.Frame(shell, bg=BG)
        actions.pack(fill='x', pady=(12, 0))
        for column, weight in enumerate((3, 2, 2, 2)):
            actions.columnconfigure(column, weight=weight, uniform='actions')
        for column, (key, text, command, kind, bold) in enumerate((
                ('restart', '重新开始', callbacks['restart'], 'primary', True),
                ('guide', '辅助线', callbacks['toggle_guide'], 'on', False),
                ('rank', '排名', callbacks['toggle_rank'], 'off', False),
                ('hide', '隐藏', callbacks['toggle_hide'], 'soft', False))):
            self._pill(actions, key, text, command, kind, bold=bold, padx=6).grid(
                row=0, column=column, sticky='ew', padx=(0 if column == 0 else 6, 0))

        foot = tk.Frame(shell, bg=BG)
        foot.pack(fill='x', pady=(10, 0))
        small = {'padx': 6, 'pady': 3}
        self._pill(foot, 'update', '检查更新', callbacks['check_updates'], 'ghost', **small).pack(side='left')
        self._pill(foot, 'donate', '打赏', callbacks['donate'], 'gold', **small).pack(side='left')
        self._pill(foot, 'felt', '台面', callbacks['toggle_felt'], 'ghost', **small).pack(side='left')
        layout_pill = self._pill(foot, 'layout', '布局', lambda: None, 'ghost', **small)
        layout_pill.command = lambda: self._popup(self._layout_menu(), layout_pill)
        layout_pill.pack(side='left')
        self._pill(foot, 'quit', '退出', callbacks['quit'], 'ghost', **small).pack(side='right')
        tk.Label(shell, textvariable=self.update_feedback, font=(FONT, 8), fg=MUTED, bg=BG,
                 anchor='w').pack(fill='x', pady=(2, 0))
        tk.Label(shell, text='Esc / Ctrl+Alt+X 退出并恢复桌面 · Ctrl+Alt+H 隐藏', font=(FONT, 8), fg='#58716a',
                 bg=BG, anchor='w').pack(fill='x', pady=(2, 0))

    def _build_bar(self):
        callbacks = self.callbacks
        shell = tk.Frame(self.shell, bg=BG, padx=12, pady=8)
        shell.pack(fill='both', expand=True)
        left = tk.Frame(shell, bg=BG)
        left.pack(side='left')
        tk.Frame(left, width=250, height=0, bg=BG).pack()
        self._status_row(left, 230).pack(anchor='w')
        tk.Label(left, textvariable=self.rank_first, font=(FONT, 8), fg=MUTED, bg=BG, anchor='w',
                 wraplength=250).pack(anchor='w', padx=(19, 0))
        right = tk.Frame(shell, bg=BG)
        right.pack(side='right')
        buttons = tk.Frame(right, bg=BG)
        buttons.pack()
        self._credit(right).pack(anchor='e', pady=(4, 0))
        more = Pill(buttons, '⋯', lambda: None, 'soft', padx=9, pady=5)
        more.command = lambda: self._popup(self._more_menu(), more)
        for key, text, command, kind, bold in (
                ('restart', '重新开始', callbacks['restart'], 'primary', True),
                ('guide', '辅助线', callbacks['toggle_guide'], 'on', False),
                ('rank', '排名', callbacks['toggle_rank'], 'off', False),
                ('hide', '隐藏', callbacks['toggle_hide'], 'soft', False)):
            self._pill(buttons, key, text, command, kind, bold=bold, padx=10, pady=5).pack(side='left', padx=(6, 0))
        more.pack(side='left', padx=(6, 0))
        for title, value in ((self.time_title, self.time_value), (self.count_title, self.count_value),
                             (self.remaining_title, self.remaining_value)):
            self._stat(shell, title, value, size=14, background=BG).pack(side='left', padx=(18, 0))

    def _build_side(self):
        callbacks = self.callbacks
        shell = tk.Frame(self.shell, bg=BG, padx=12, pady=10)
        shell.pack(fill='both', expand=True)
        tk.Frame(shell, width=148, height=0, bg=BG).pack()
        self._status_row(shell, 128).pack(fill='x', pady=(0, 8))
        stats = tk.Frame(shell, bg=CARD, padx=12, pady=8)
        stats.pack(fill='x')
        for index, (title, value) in enumerate(((self.time_title, self.time_value),
                                                (self.count_title, self.count_value),
                                                (self.remaining_title, self.remaining_value))):
            self._stat(stats, title, value, size=16, background=CARD).pack(anchor='w', pady=(0 if index == 0 else 6, 0))
        tk.Label(shell, textvariable=self.rank_first, font=(FONT, 8), fg=MUTED, bg=BG, anchor='nw', justify='left',
                 wraplength=148).pack(fill='x', pady=(8, 8))
        for key, text, command, kind, bold in (
                ('restart', '重新开始', callbacks['restart'], 'primary', True),
                ('guide', '辅助线', callbacks['toggle_guide'], 'on', False),
                ('rank', '排名', callbacks['toggle_rank'], 'off', False),
                ('hide', '隐藏', callbacks['toggle_hide'], 'soft', False)):
            self._pill(shell, key, text, command, kind, bold=bold, pady=5).pack(fill='x', pady=(0, 5))
        more = Pill(shell, '⋯  更多', lambda: None, 'ghost', pady=4)
        more.command = lambda: self._popup(self._more_menu(), more)
        more.pack(fill='x')
        self._credit(shell).pack(anchor='w', pady=(6, 0))

    # -- menus -----------------------------------------------------------------
    def _new_menu(self):
        return tk.Menu(self.root, tearoff=0, bg=CARD, fg=TEXT, activebackground='#294843', activeforeground=TEXT,
                       bd=0, relief='flat', font=(FONT, 9))

    def _layout_menu(self, parent=None):
        menu = self._new_menu() if parent is None else tk.Menu(parent, tearoff=0, bg=CARD, fg=TEXT,
                                                               activebackground='#294843', activeforeground=TEXT,
                                                               bd=0, relief='flat', font=(FONT, 9))
        for name, label in LAYOUTS:
            menu.add_command(label=('● ' if name == self.layout else '    ') + label,
                             command=lambda name=name: self.callbacks['set_layout'](name))
        return menu

    def _more_menu(self):
        menu = self._new_menu()
        menu.add_command(label=self.look['felt']['text'].replace('台面', '台面框'), command=self.callbacks['toggle_felt'])
        menu.add_command(label='检查更新', command=self.callbacks['check_updates'])
        menu.add_command(label='打赏', command=self.callbacks['donate'])
        menu.add_cascade(label='布局', menu=self._layout_menu(menu))
        menu.add_separator()
        menu.add_command(label='退出', command=self.callbacks['quit'])
        return menu

    @staticmethod
    def _popup(menu, anchor):
        try:
            menu.tk_popup(anchor.winfo_rootx(), anchor.winfo_rooty() + anchor.winfo_height())
        finally:
            menu.grab_release()


class ResultDialog:
    """The round-end window: the numbers that matter, large, plus the ranking outcome.

    :meth:`update` takes a ``view`` dict and may be called every frame; widgets only change
    when a value does. Keys: ``time``, ``average``, ``balls``, ``shots``, ``note`` and
    ``rank`` (phase ``off`` / ``unavailable`` / ``skipped`` / ``pending`` / ``ok`` / ``error``).
    """

    def __init__(self, root, callbacks, credit=''):
        self.callbacks = callbacks
        self.top = tk.Toplevel(root)
        top = self.top
        top.title('清台完成')
        top.configure(bg=BG)
        top.transient(root)
        top.resizable(False, False)
        self.vars = {name: tk.StringVar(top) for name in ('time', 'average', 'balls', 'shots', 'note', 'big', 'sub',
                                                          'best', 'message')}
        shell = tk.Frame(top, bg=BG, padx=22, pady=18)
        shell.pack(fill='both', expand=True)
        tk.Frame(shell, width=340, height=0, bg=BG).pack()
        title = tk.Frame(shell, bg=BG)
        title.pack(fill='x')
        tk.Label(title, text='清台完成', font=(FONT, 11, 'bold'), fg=ACCENT, bg=BG).pack(side='left')
        if credit:
            link = tk.Label(title, text=credit, font=(FONT, 8), fg=MUTED, bg=BG, cursor='hand2')
            link.pack(side='right', pady=(3, 0))
            link.bind('<ButtonRelease-1>', lambda event: callbacks['open_credit']())
        tk.Label(shell, textvariable=self.vars['time'], font=(NUMBERS, 34), fg=TEXT, bg=BG).pack(anchor='w', pady=(2, 0))
        tk.Label(shell, text='总用时', font=(FONT, 8), fg=MUTED, bg=BG).pack(anchor='w')

        tiles = tk.Frame(shell, bg=CARD, padx=14, pady=10)
        tiles.pack(fill='x', pady=(12, 0))
        for column, (title, name, size) in enumerate((('平均每颗（秒）', 'average', 17), ('图标', 'balls', 17),
                                                      ('击球', 'shots', 17))):
            tiles.columnconfigure(column, weight=1, uniform='tiles')
            box = tk.Frame(tiles, bg=CARD)
            box.grid(row=0, column=column, sticky='w')
            tk.Label(box, text=title, font=(FONT, 8), fg=MUTED, bg=CARD).pack(anchor='w')
            tk.Label(box, textvariable=self.vars[name], font=(NUMBERS, size), fg=TEXT, bg=CARD).pack(anchor='w')
        tk.Label(shell, textvariable=self.vars['note'], font=(FONT, 8), fg=MUTED, bg=BG, anchor='w').pack(
            fill='x', pady=(4, 0))

        self.rank_box = tk.Frame(shell, bg=CARD, padx=14, pady=12)
        self.rank_box.pack(fill='x', pady=(12, 0))
        tk.Label(self.rank_box, text='全球排名', font=(FONT, 8), fg=MUTED, bg=CARD).pack(anchor='w')
        self.big = tk.Label(self.rank_box, textvariable=self.vars['big'], font=(NUMBERS, 24), fg=ACCENT, bg=CARD)
        self.sub = tk.Label(self.rank_box, textvariable=self.vars['sub'], font=(FONT, 9), fg=TEXT, bg=CARD)
        self.best = tk.Label(self.rank_box, textvariable=self.vars['best'], font=(FONT, 9), fg=MUTED, bg=CARD)
        self.message = tk.Label(self.rank_box, textvariable=self.vars['message'], font=(FONT, 9), fg=MUTED, bg=CARD,
                                justify='left', wraplength=300)
        self.offer = Pill(self.rank_box, '开启全球排名', callbacks['enable_rank'], 'on', padx=12, pady=5)

        buttons = tk.Frame(shell, bg=BG)
        buttons.pack(fill='x', pady=(16, 0))
        Pill(buttons, '再来一局', callbacks['again'], 'primary', bold=True, padx=18).pack(side='right')
        Pill(buttons, '关闭', self.close, 'soft', padx=16).pack(side='right', padx=(0, 8))
        top.bind('<Escape>', lambda event: self.close())
        top.protocol('WM_DELETE_WINDOW', self.close)
        self.last = None
        self.phase = None
        top.update_idletasks()
        width = top.winfo_reqwidth()
        left = max(0, (top.winfo_screenwidth() - width) // 2)
        top.geometry(f'+{left}+{max(20, top.winfo_screenheight() // 7)}')
        top.lift()

    def alive(self):
        return self.top is not None and self.top.winfo_exists()

    def close(self):
        if self.alive():
            self.top.destroy()
        self.top = None

    def update(self, view):
        if not self.alive() or view == self.last:
            return
        self.last = view
        for name in ('time', 'average', 'balls', 'shots', 'note'):
            self.vars[name].set(view[name])
        rank = view['rank']
        phase = rank['phase']
        for widget in (self.big, self.sub, self.best, self.message, self.offer):
            widget.pack_forget()
        if phase == 'unavailable':
            self.rank_box.pack_forget()
            return
        if not self.rank_box.winfo_manager():
            self.rank_box.pack(fill='x', pady=(12, 0), before=self.rank_box.master.winfo_children()[-1])
        if phase == 'ok':
            self.vars['big'].set(rank['rank_text'])
            self.vars['sub'].set(rank['percentile_text'])
            self.vars['best'].set(rank['best_text'])
            self.big.pack(anchor='w')
            self.sub.pack(anchor='w')
            self.best.configure(fg=ACCENT if rank.get('new_best') else MUTED)
            self.best.pack(anchor='w', pady=(2, 0))
            return
        messages = {'pending': '正在提交成绩…', 'off': '全球排名未开启，开启后可以和其他玩家比较。'}
        self.vars['message'].set(rank.get('message') or messages.get(phase, ''))
        self.message.pack(anchor='w', pady=(4, 0))
        if phase == 'off':
            self.offer.pack(anchor='w', pady=(8, 0))


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
