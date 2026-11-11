"""Tk window, game lifecycle, and single-instance handling."""
from __future__ import annotations

import ctypes
import json
import os
import queue
import subprocess
import sys
import threading
import time
import traceback
import webbrowser
from ctypes import wintypes

import tkinter as tk
import win32api
import win32con
from PIL import Image, ImageTk
from tkinter import messagebox, scrolledtext, ttk

from . import config, diag
from .display import dpi_context
from .instance import acquire_instance, claim_instance_mutex, publish_version
from .overlay import BilliardsOverlay
from .panel import MainPanel
from .paths import runtime_directory
from .rank import RankApi, RankController, RankSettings, data_directory
from .runner import BilliardsRunner
from .shell import LayoutSession, ShellDesktop
from .update import fetch_update, release_entries


HINTS = {
    'ready': '瞄准 · 长按蓄力 · 松手击球',
    'stroke': '击球',
    'rolling': '图标滚动中',
    'return_white': '白球入袋 · 正在摆回',
    'ball_in_hand': '白球入袋 · 点击空处摆球',
    'finished': '清台 · 本局完成',
}

RANK_CONSENT = (
    '开启后，每局清台时会向排名服务器提交：\n'
    '  • 本局用时、图标数量、击球次数\n'
    '  • 一个匿名设备标识（由本机系统 ID 加盐哈希得到，无法还原）\n\n'
    '不会上传图标名称、桌面截图或任何个人文件信息。可随时在主窗口关闭。\n\n'
    '是否开启全球排名？'
)
RANK_INTRO = '现在可以和全球玩家比谁清台更快了。\n\n' + RANK_CONSENT


def _write_log(name, text):
    try:
        (runtime_directory() / name).write_text(text, encoding='utf-8')
    except OSError:
        pass


class DesktopBilliardsApp:
    """Own the Tk window, the layout journal and the animation runner."""

    def __init__(self, root, instance_handle):
        self.root = root
        self.instance_handle = instance_handle
        self.runner = None
        self.session = None
        self.watchdog = None
        self.donation = None
        self.closing = False
        self.deadline = 0.0
        self.journal = runtime_directory() / 'layout.json'
        root.title(config.WINDOW_TITLE)
        root.resizable(False, False)
        try:
            root.iconbitmap(str(config.ICON_PATH))
        except tk.TclError:
            pass
        ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-2))
        publish_version(root, config.VERSION)
        self.rank = self.make_rank()
        self.rank_offered = False
        self.guide_enabled = True
        self.update_results = queue.SimpleQueue()
        self.panel = panel = MainPanel(root, config.VERSION, {
            'restart': self.restart, 'toggle_guide': self.toggle_guide, 'toggle_rank': self.toggle_rank,
            'check_updates': lambda: self.check_updates(manual=True), 'donate': self.show_donation,
            'quit': self.close,
        })
        self.status, self.rank_text, self.update_feedback = panel.status, panel.rank_text, panel.update_feedback
        self.time_title, self.time_value = panel.time_title, panel.time_value
        self.count_title, self.count_value = panel.count_title, panel.count_value
        self.remaining_value = panel.remaining_value
        self.guide_button, self.update_button, self.rank_button = panel.guide_button, panel.update_button, panel.rank_button
        self.refresh_rank_button()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.bind('<Escape>', lambda event: self.close())
        root.update_idletasks()
        monitor = win32api.MonitorFromPoint((0, 0), win32con.MONITOR_DEFAULTTOPRIMARY)
        left, top, right, _ = win32api.GetMonitorInfo(monitor)['Work']
        root.geometry(f'+{max(left, right - root.winfo_reqwidth() - 18)}+{top + 8}')
        self.hotkey = bool(ctypes.windll.user32.RegisterHotKey(
            None, config.HOTKEY_ID, config.HOTKEY_MODIFIERS, config.HOTKEY_VK))
        root.after(20, self.start)
        root.after(1500, self.check_updates)

    @staticmethod
    def make_rank():
        """Ranking is optional: a missing or invalid server address just disables it."""
        if config.RANK_URL:
            try:
                api = RankApi(config.RANK_URL, config.VERSION)
                return RankController(api, RankSettings(data_directory() / 'rank.json'))
            except (ValueError, OSError):
                _write_log('rank.log', traceback.format_exc())
        return RankController(None, None)

    def refresh_rank_button(self):
        if not self.rank.available:
            self.rank_button.set('排名 —', 'off', enabled=False)
            return
        on = self.rank.enabled
        self.rank_button.set('排名 开' if on else '排名 关', 'on' if on else 'off', enabled=True)

    def offer_rank(self):
        """Ask once, on the first run after the feature exists, whether to join the ranking."""
        if self.closing or not self.rank.needs_prompt:
            return
        self.rank.mark_prompted()
        if messagebox.askyesno('全球排名', RANK_INTRO, parent=self.root):
            self.rank.set_enabled(True)
        self.refresh_rank_button()

    def toggle_rank(self):
        if not self.rank.available:
            return
        if self.rank.enabled:
            self.rank.set_enabled(False)
        elif messagebox.askokcancel('全球排名', RANK_CONSENT, parent=self.root):
            self.rank.set_enabled(True)
        self.refresh_rank_button()

    def show_donation(self):
        if self.donation is not None and self.donation.winfo_exists():
            self.donation.lift()
            return
        try:
            with Image.open(config.ASSETS / 'donation.jpg') as source:
                image = source.convert('RGB')
            image.thumbnail((340, 340), Image.Resampling.LANCZOS)
        except OSError:
            messagebox.showwarning('打赏', '暂时无法打开赞赏图片。', parent=self.root)
            return
        self.donation = dialog = tk.Toplevel(self.root)
        dialog.title('打赏')
        dialog.transient(self.root)
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=14, style='Panel.TFrame')
        body.pack()
        ttk.Label(body, text='微信扫码赞赏，感谢支持！', style='Table.TLabel').pack(pady=(0, 10))
        photo = ImageTk.PhotoImage(image, master=dialog)
        label = ttk.Label(body, image=photo)
        label.image = photo
        label.pack()
        ttk.Button(body, text='关闭', command=dialog.destroy, style='Table.TButton').pack(pady=(10, 0))
        dialog.bind('<Escape>', lambda event: dialog.destroy())

    def check_updates(self, manual=False):
        if self.closing or not self.update_button.enabled:
            return
        self.update_button.set('检查中…', enabled=False)
        self.update_feedback.set('')

        def fetch():
            try:
                info = fetch_update(config.UPDATE_URL, config.VERSION)
            except Exception:
                _write_log('update.log', traceback.format_exc())
                self.update_results.put((False, None))
            else:
                self.update_results.put((True, info))

        threading.Thread(target=fetch, name='Billiards-update', daemon=True).start()
        self.root.after(100, self.finish_update_check, manual)

    def finish_update_check(self, manual):
        if self.closing:
            return
        try:
            success, info = self.update_results.get_nowait()
        except queue.Empty:
            self.root.after(100, self.finish_update_check, manual)
            return
        self.update_button.set('检查更新', enabled=True)
        if info:
            self.show_update(info)
        elif manual:
            self.update_feedback.set('已是最新版' if success else '检查失败，请稍后重试')

    def show_update(self, info):
        dialog = tk.Toplevel(self.root)
        dialog.title(f'发现新版本 {info["version"]}')
        dialog.transient(self.root)
        body = ttk.Frame(dialog, padding=14)
        body.pack(fill='both', expand=True)
        notes = scrolledtext.ScrolledText(body, width=46, height=12, wrap='word')
        notes.pack(fill='both', expand=True)
        notes.tag_configure('latest', font=('Microsoft YaHei UI', 10, 'bold'))
        for index, entry in enumerate(release_entries(info)):
            notes.insert('end', f'{entry["version"]}\n', 'latest' if index == 0 else ())
            notes.insert('end', (entry['notes'] or '暂无更新说明') + '\n\n')
        notes.configure(state='disabled')

        def download():
            if webbrowser.open(info['download_url']):
                dialog.destroy()
            else:
                messagebox.showerror('打开下载失败', '请检查默认浏览器设置。', parent=dialog)

        ttk.Button(body, text='去更新', command=download).pack(side='right', pady=(10, 0))
        ttk.Button(body, text='稍后', command=dialog.destroy).pack(side='right', padx=6, pady=(10, 0))
        dialog.geometry(f'+{self.root.winfo_x()}+{self.root.winfo_y()+self.root.winfo_height()+10}')

    # -- game lifecycle ----------------------------------------------------
    def start(self):
        if self.closing:
            return
        diag.start_session(config.VERSION)
        try:
            desktop = ShellDesktop()
            # Recover a journal left behind by an earlier crash before starting.
            self.session = LayoutSession(desktop, self.journal)
            self.session.restore()
            self.session = LayoutSession(desktop, self.journal)
            items = self.session.begin(overlay_only=True)
            for item in items:
                item['name'] = desktop.folder.GetDisplayNameOf(
                    [desktop.cache[item['id']]], desktop.shellcon.SHGDN_NORMAL)
            with dpi_context(-4):
                overlay = BilliardsOverlay(desktop, items)
                overlay.guide_enabled = self.guide_enabled
            self.watchdog = self.spawn_watchdog()
            self.runner = BilliardsRunner(overlay)
            self.runner.start()
            self.deadline = time.monotonic() + 30
            self.poll()
        except Exception as exc:
            self.fail(exc)

    def spawn_watchdog(self):
        frozen = bool(getattr(sys, 'frozen', False))
        command = [sys.executable]
        if not frozen:
            command.append(str(config.BASE / 'app.pyw'))
        command.extend(['--watchdog', str(self.journal), self.session.snapshot['session_id'], str(os.getpid())])
        environment = {**os.environ, 'PYINSTALLER_RESET_ENVIRONMENT': '1'}
        return subprocess.Popen(command, env=environment,
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL, creationflags=subprocess.CREATE_NO_WINDOW,
                                cwd=str(runtime_directory()))

    def poll(self):
        if self.closing:
            return
        try:
            if self.hotkey:
                message = wintypes.MSG()
                if ctypes.windll.user32.PeekMessageW(ctypes.byref(message), None, 0x312, 0x312, 1) \
                        and message.wParam == config.HOTKEY_ID:
                    self.close()
                    return
            if self.runner.error:
                raise self.runner.error
            if not self.runner.shown.is_set():
                if time.monotonic() > self.deadline:
                    raise RuntimeError('等待桌面恢复守护就绪超时。')
                ready = self.journal.with_name(self.journal.stem + '.watchdog.json')
                if ready.exists():
                    data = json.loads(ready.read_text(encoding='utf-8'))
                    if data.get('session_id') == self.session.snapshot['session_id'] and self.runner.prepared.is_set():
                        if not data.get('ready'):
                            raise RuntimeError('无法启动桌面恢复守护。')
                        self.runner.request_show(self.session.snapshot, self.journal)
            else:
                if not self.rank_offered:
                    self.rank_offered = True
                    self.root.after(800, self.offer_rank)
                overlay = self.runner.overlay
                table = overlay.table
                state = table.state
                label = HINTS.get(state, state)
                if overlay.transition:
                    label = '正在摆球…'
                elif state == 'rolling' and table.white_sunk:
                    label = '白球入袋 · 等其他球停稳'
                elif state == 'ready' and table.charge:
                    label = '松手击球'
                blocked = bool(overlay.blocked_by and not overlay.transition)
                if blocked:
                    label = f'鼠标被「{overlay.blocked_by}」挡住，无法击球'
                self.status.set(label)
                self.panel.set_tone('warn' if blocked else 'ok')
                minutes, seconds = divmod(table.round_seconds, 60)
                self.time_value.set(f'{minutes:02d}:{seconds:02d}')
                total = len(table.icons)
                pocketed = table.pocketed_icons
                finished = state == 'finished'
                self.time_title.set('总用时' if finished else '本局用时')
                self.count_title.set('图标总数' if finished else '图标入袋')
                self.count_value.set(str(total) if finished else f'{pocketed}/{total}')
                self.remaining_value.set(str(total - pocketed))
                try:
                    self.rank.observe(table)
                    lines = self.rank.lines(table)
                    if not finished:  # the finished summary already states the ball count
                        lines = [overlay.ball_info, *lines]
                    self.rank_text.set('\n'.join(lines))
                except Exception:
                    # Ranking must never interrupt a game or the desktop restore.
                    _write_log('rank.log', traceback.format_exc())
            self.root.after(50, self.poll)
        except Exception as exc:
            self.fail(exc)

    def restart(self):
        if self.runner and self.runner.shown.is_set():
            self.runner.overlay.request_restart()

    def toggle_guide(self):
        self.guide_enabled = not self.guide_enabled
        self.guide_button.set('辅助线 开' if self.guide_enabled else '辅助线 关',
                              'on' if self.guide_enabled else 'off')
        if self.runner:
            self.runner.overlay.guide_enabled = self.guide_enabled

    def fail(self, error):
        try:
            self.restore()
        except Exception as exc:
            self.status.set('请再次点击退出')
            messagebox.showerror(config.PRODUCT_NAME, f'{error}\n\n{exc}', parent=self.root)
            return
        _write_log('error.log', traceback.format_exc())
        messagebox.showerror(config.PRODUCT_NAME, str(error), parent=self.root)
        self.close()

    def restore(self):
        if self.runner:
            self.runner.stop()
            self.runner = None
        if self.session:
            self.session.restore()
            self.session = None

    def close(self):
        if self.closing:
            return
        try:
            self.restore()
        except Exception as exc:
            self.status.set(str(exc))
            messagebox.showwarning(config.PRODUCT_NAME, f'桌面恢复未完成：{exc}\n\n请重试退出。',
                                   parent=self.root)
            return
        self.closing = True
        self.rank.close()
        if self.hotkey:
            ctypes.windll.user32.UnregisterHotKey(None, config.HOTKEY_ID)
        ctypes.windll.kernel32.CloseHandle(self.instance_handle)
        self.root.destroy()


def main():
    ctypes.windll.shcore.SetProcessDpiAwareness(1)
    app = None
    desktop_guard = None
    try:
        handle = acquire_instance(config.VERSION)
        desktop_guard = claim_instance_mutex(config.DESKTOP_GUARD)
        if desktop_guard is None:
            ctypes.windll.kernel32.CloseHandle(handle)
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo(config.PRODUCT_NAME,
                                '检测到「桌面蹦迪」正在运行。\n请先退出它，再打开桌面图标台球。',
                                parent=root)
            root.destroy()
            return
        root = tk.Tk()
        app = DesktopBilliardsApp(root, handle)
        root.mainloop()
    except SystemExit:
        raise
    except Exception:
        _write_log('error.log', traceback.format_exc())
        if app is not None:
            try:
                app.close()
            except Exception:
                pass
        else:
            try:
                messagebox.showerror(config.PRODUCT_NAME, '启动失败，详情已写入日志。')
            except Exception:
                pass
        raise
    finally:
        if desktop_guard:
            ctypes.windll.kernel32.CloseHandle(desktop_guard)
