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
from tkinter import messagebox, ttk

from . import config, diag
from .display import dpi_context
from .instance import acquire_instance, claim_instance_mutex, publish_version
from .overlay import BilliardsOverlay
from .panel import MainPanel, ResultDialog, format_duration, show_update_dialog
from .paths import runtime_directory
from .rank import RankApi, RankController, RankSettings, average_seconds, data_directory
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
        self.hidden = False
        self.result_dialog = None
        self.result_serial = None
        self.update_results = queue.SimpleQueue()
        self.settings = self.make_settings()
        self.felt_enabled = bool(self.settings.get('felt', True))
        self.panel = panel = MainPanel(root, config.VERSION, {
            'restart': self.restart, 'toggle_guide': self.toggle_guide, 'toggle_rank': self.toggle_rank,
            'check_updates': lambda: self.check_updates(manual=True), 'donate': self.show_donation,
            'quit': self.close, 'toggle_hide': self.toggle_hide, 'toggle_felt': self.toggle_felt,
            'set_layout': self.apply_layout, 'open_credit': self.open_credit,
        }, self.settings.get('layout', 'card'), config.CREDIT)
        self.status, self.rank_text, self.update_feedback = panel.status, panel.rank_text, panel.update_feedback
        self.time_title, self.time_value = panel.time_title, panel.time_value
        self.count_title, self.count_value = panel.count_title, panel.count_value
        self.remaining_value = panel.remaining_value
        self.refresh_buttons()
        root.protocol('WM_DELETE_WINDOW', self.close)
        root.bind('<Escape>', lambda event: self.close())
        self.place_window(panel.layout)
        self.hotkey = bool(ctypes.windll.user32.RegisterHotKey(
            None, config.HOTKEY_ID, config.HOTKEY_MODIFIERS, config.HOTKEY_VK))
        self.hide_hotkey = bool(ctypes.windll.user32.RegisterHotKey(
            None, config.HIDE_HOTKEY_ID, config.HOTKEY_MODIFIERS, config.HIDE_HOTKEY_VK))
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

    @staticmethod
    def make_settings():
        """Window layout and position, and the table-frame switch (kept across runs)."""
        try:
            return RankSettings(data_directory() / 'ui.json')
        except OSError:
            return RankSettings(runtime_directory() / 'ui.json')

    def refresh_rank_button(self):
        if not self.rank.available:
            self.panel.set_look('rank', '排名 —', 'off', enabled=False)
            return
        on = self.rank.enabled
        self.panel.set_look('rank', '排名 开' if on else '排名 关', 'on' if on else 'off', enabled=True)

    def refresh_buttons(self):
        self.refresh_rank_button()
        self.panel.set_look('guide', '辅助线 开' if self.guide_enabled else '辅助线 关',
                            'on' if self.guide_enabled else 'off')
        self.panel.set_look('felt', '台面 开' if self.felt_enabled else '台面 关')
        self.panel.set_look('hide', '显示' if self.hidden else '隐藏')

    # -- window placement and layout ---------------------------------------
    def place_window(self, layout):
        """Restore the saved position of this layout, or dock it at a default spot."""
        root = self.root
        root.update_idletasks()
        width = root.winfo_reqwidth()
        monitor = win32api.MonitorFromPoint((0, 0), win32con.MONITOR_DEFAULTTOPRIMARY)
        left, top, right, _ = win32api.GetMonitorInfo(monitor)['Work']
        x, y = self.settings.get(f'{layout}_x'), self.settings.get(f'{layout}_y')
        vx, vy, vw, vh = (win32api.GetSystemMetrics(index) for index in (76, 77, 78, 79))
        if not (isinstance(x, int) and isinstance(y, int)
                and vx - 20 <= x <= vx + vw - 80 and vy <= y <= vy + vh - 40):
            if layout == 'bar':
                x, y = left + max(0, (right - left - width) // 2), top + 2
            elif layout == 'side':
                x, y = right - width - 6, top + 8
            else:
                x, y = max(left, right - width - 18), top + 8
        root.geometry(f'+{x}+{y}')

    def remember_position(self):
        if self.root.state() == 'normal':
            self.settings.update(**{f'{self.panel.layout}_x': self.root.winfo_x(),
                                    f'{self.panel.layout}_y': self.root.winfo_y()})

    def apply_layout(self, name):
        if name == self.panel.layout:
            return
        self.remember_position()
        self.panel.set_layout(name)
        self.refresh_buttons()
        self.place_window(name)
        self.settings.update(layout=name)

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
        if self.closing or not self.panel.is_enabled('update'):
            return
        self.panel.set_look('update', '检查中…', enabled=False)
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
        self.panel.set_look('update', '检查更新', enabled=True)
        if info:
            self.show_update(info)
        elif manual:
            self.update_feedback.set('已是最新版' if success else '检查失败，请稍后重试')

    def show_update(self, info):
        def download(dialog):
            if webbrowser.open(info['download_url']):
                dialog.destroy()
            else:
                messagebox.showerror('打开下载失败', '请检查默认浏览器设置。', parent=dialog)

        show_update_dialog(self.root, config.VERSION, info, release_entries(info), download)

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
                overlay.want_felt = self.felt_enabled
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
            if self.hotkey or self.hide_hotkey:
                message = wintypes.MSG()
                while ctypes.windll.user32.PeekMessageW(ctypes.byref(message), None, 0x312, 0x312, 1):
                    if message.wParam == config.HOTKEY_ID:
                        self.close()
                        return
                    if message.wParam == config.HIDE_HOTKEY_ID:
                        self.toggle_hide()
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
                    self.panel.rank_first.set(lines[0] if lines else '')
                    self.update_result_dialog(overlay, table, finished)
                except Exception:
                    # Ranking and dialogs must never interrupt a game or the desktop restore.
                    _write_log('rank.log', traceback.format_exc())
            self.root.after(50, self.poll)
        except Exception as exc:
            self.fail(exc)

    def restart(self):
        if self.runner and self.runner.shown.is_set():
            self.runner.overlay.request_restart()

    def toggle_guide(self):
        self.guide_enabled = not self.guide_enabled
        self.refresh_buttons()
        if self.runner:
            self.runner.overlay.guide_enabled = self.guide_enabled

    def toggle_felt(self):
        """Show or hide the table frame, pockets and wallpaper panel."""
        self.felt_enabled = not self.felt_enabled
        self.settings.update(felt=self.felt_enabled)
        self.refresh_buttons()
        if self.runner:
            self.runner.overlay.want_felt = self.felt_enabled

    def toggle_hide(self):
        """Boss key: hide the game and this window, show the real desktop, pause the round."""
        if not (self.runner and self.runner.shown.is_set()) or self.runner.overlay.transition:
            return
        self.hidden = not self.hidden
        self.runner.overlay.want_hidden = self.hidden
        if self.hidden:
            self.remember_position()
            self.root.withdraw()
        else:
            self.root.deiconify()
            self.root.lift()
        self.refresh_buttons()

    # -- round result ------------------------------------------------------
    def update_result_dialog(self, overlay, table, finished):
        """Open the result window once per cleared round and keep its numbers current."""
        if finished and self.result_serial != table.round_serial and not self.hidden:
            self.result_serial = table.round_serial
            self.result_dialog = ResultDialog(self.root, {'again': self.play_again,
                                                          'enable_rank': self.enable_rank_from_dialog,
                                                          'open_credit': self.open_credit}, config.CREDIT)
        dialog = self.result_dialog
        if dialog is None:
            return
        if not dialog.alive():
            self.result_dialog = None
        elif not finished or table.round_serial != self.result_serial:
            dialog.close()  # a new round has begun
            self.result_dialog = None
        else:
            count = len(table.icons)
            dialog.update({
                'time': format_duration(table.play_ms),
                'average': f'{average_seconds(table.play_ms, count):.2f}',
                'balls': str(count),
                'shots': str(table.shots),
                'note': overlay.ball_info,
                'rank': self.rank.view(table),
            })

    @staticmethod
    def open_credit():
        webbrowser.open(config.CREDIT_URL)

    def play_again(self):
        if self.result_dialog is not None:
            self.result_dialog.close()
            self.result_dialog = None
        self.restart()

    def enable_rank_from_dialog(self):
        if self.rank.available and not self.rank.enabled:
            self.toggle_rank()

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
        self.remember_position()
        if self.hotkey:
            ctypes.windll.user32.UnregisterHotKey(None, config.HOTKEY_ID)
        if self.hide_hotkey:
            ctypes.windll.user32.UnregisterHotKey(None, config.HIDE_HOTKEY_ID)
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
