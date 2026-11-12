"""Global keyboard and mouse input, and platform window tweaks.

Events go into a queue as ('key', label, down, repeat) or ('button', down).
macOS uses a listen-only Quartz event tap; other systems use pynput.
"""
import sys
import threading
import time

from . import keys

_keep = []


def start(events):
    if sys.platform == 'darwin':
        return _mac(events)
    return _pynput(events)


def _mac(events):
    try:
        import Quartz
    except ImportError:
        return None
    pressed = set()
    state = {}

    def callback(proxy, kind, event, refcon):
        try:
            if kind in (Quartz.kCGEventTapDisabledByTimeout, Quartz.kCGEventTapDisabledByUserInput):
                Quartz.CGEventTapEnable(state['tap'], True)
            elif kind in (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp):
                code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
                repeat = bool(Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventAutorepeat))
                events.put(('key', keys.mac_label(code), kind == Quartz.kCGEventKeyDown, repeat))
            elif kind == Quartz.kCGEventFlagsChanged:
                code = Quartz.CGEventGetIntegerValueField(event, Quartz.kCGKeyboardEventKeycode)
                down = code not in pressed
                (pressed.add if down else pressed.discard)(code)
                events.put(('key', keys.mac_label(code), down, False))
            elif kind in (Quartz.kCGEventLeftMouseDown, Quartz.kCGEventRightMouseDown):
                events.put(('button', True))
            elif kind in (Quartz.kCGEventLeftMouseUp, Quartz.kCGEventRightMouseUp):
                events.put(('button', False))
        except Exception:
            pass
        return event

    mask = 0
    for kind in (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp, Quartz.kCGEventFlagsChanged,
                 Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp,
                 Quartz.kCGEventRightMouseDown, Quartz.kCGEventRightMouseUp):
        mask |= Quartz.CGEventMaskBit(kind)
    tap = Quartz.CGEventTapCreate(Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
                                  Quartz.kCGEventTapOptionListenOnly, mask, callback, None)
    if tap is None:
        return _mac_poll(events)
    state['tap'] = tap
    source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)

    def loop():
        Quartz.CFRunLoopAddSource(Quartz.CFRunLoopGetCurrent(), source, Quartz.kCFRunLoopCommonModes)
        Quartz.CGEventTapEnable(tap, True)
        Quartz.CFRunLoopRun()

    threading.Thread(target=loop, name='pet-input', daemon=True).start()
    _keep.extend([tap, source, callback])
    return 'tap'


def _mac_poll(events):
    """Fallback when the event tap is refused: poll key and button state."""
    import Quartz

    session = Quartz.kCGEventSourceStateCombinedSessionState
    codes = list(keys.MAC)

    def loop():
        down = set()
        button = False
        while True:
            for code in codes:
                now = bool(Quartz.CGEventSourceKeyState(session, code))
                if now != (code in down):
                    (down.add if now else down.discard)(code)
                    events.put(('key', keys.mac_label(code), now, False))
            now = bool(Quartz.CGEventSourceButtonState(session, Quartz.kCGMouseButtonLeft)) or \
                bool(Quartz.CGEventSourceButtonState(session, Quartz.kCGMouseButtonRight))
            if now != button:
                button = now
                events.put(('button', now))
            time.sleep(1 / 60)

    threading.Thread(target=loop, name='pet-poll', daemon=True).start()
    return 'poll'


def _pynput(events):
    try:
        from pynput import keyboard, mouse
    except ImportError:
        return None
    held = set()

    def label(key):
        if isinstance(key, keyboard.Key):
            return key.name
        vk = getattr(key, 'vk', None)
        if vk is not None and sys.platform == 'win32':
            name = keys.win_label(vk)
            if name:
                return name
        char = getattr(key, 'char', None)
        return char.lower() if char else None

    def press(key):
        name = label(key)
        events.put(('key', name, True, name in held))
        held.add(name)

    def release(key):
        name = label(key)
        held.discard(name)
        events.put(('key', name, False, False))

    keyboard.Listener(on_press=press, on_release=release, daemon=True).start()
    mouse.Listener(on_click=lambda x, y, button, down: events.put(('button', down)), daemon=True).start()
    return 'pynput'


class Window:
    """Click-through switching and macOS window behaviour for one Qt window."""

    def __init__(self, widget):
        self.widget = widget
        self.ns = None
        self.through = None
        if sys.platform == 'darwin':
            try:
                import objc

                view = objc.objc_object(c_void_p=int(widget.winId()))
                self.ns = view.window()
                self.ns.setCollectionBehavior_(1 | 16 | 256)
                self.ns.setHidesOnDeactivate_(False)
            except Exception:
                self.ns = None

    def set_through(self, through):
        if through == self.through:
            return
        self.through = through
        if self.ns is not None:
            self.ns.setIgnoresMouseEvents_(bool(through))
        elif sys.platform == 'win32':
            try:
                import ctypes

                user32 = ctypes.windll.user32
                hwnd = int(self.widget.winId())
                style = user32.GetWindowLongW(hwnd, -20)
                if style & 0x80000:
                    style = style | 0x20 if through else style & ~0x20
                    user32.SetWindowLongW(hwnd, -20, style)
            except Exception:
                pass


def hide_dock_icon():
    if sys.platform != 'darwin':
        return
    try:
        import AppKit

        AppKit.NSApplication.sharedApplication().setActivationPolicy_(AppKit.NSApplicationActivationPolicyAccessory)
    except Exception:
        pass
