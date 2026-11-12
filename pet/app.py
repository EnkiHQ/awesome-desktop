"""The pet window: a frameless, transparent, always-on-top desk scene."""
import argparse
import json
import queue
import socket
import sys
import threading
import time

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAction, QCursor, QGuiApplication, QImage, QPainter
from PySide6.QtWidgets import QApplication, QMenu, QWidget

from . import PORT, hooks
from . import pack as packs
from .paths import state_file
from .render import Art, render
from .scene import H, W, Scene


def load_state():
    try:
        return json.loads(state_file().read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}


def save_state(state):
    try:
        state_file().write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    except OSError:
        pass


class Pet(QWidget):
    def __init__(self, state, events):
        super().__init__(None, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool | Qt.NoDropShadowWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setWindowTitle('awesome-desktop pet')
        self.state = state
        self.events = events
        try:
            data = packs.load(state.get('pet', 'default'))
        except Exception:
            data = packs.load('default')
            state['pet'] = 'default'
        self.art = Art(data)
        self.scene = Scene(data, state.get('facing', 'front'))
        self.zoom = min(3.0, max(0.4, float(state.get('zoom', 1.0))))
        self.image = None
        self.drag = None
        self.window_glue = None
        self.last = time.monotonic()
        self.resize(round(W * self.zoom), round(H * self.zoom))
        self._place()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.PreciseTimer)
        self.timer.timeout.connect(self.tick)
        self.timer.start(16)

    def _place(self):
        area = QGuiApplication.primaryScreen().availableGeometry()
        x = self.state.get('x')
        y = self.state.get('y')
        if x is None or y is None:
            x = area.right() - self.width() - 24
            y = area.bottom() - self.height() - 12
        desktop = QGuiApplication.primaryScreen().virtualGeometry()
        x = max(desktop.left() - self.width() // 2, min(int(x), desktop.right() - self.width() // 2))
        y = max(desktop.top(), min(int(y), desktop.bottom() - self.height() // 3))
        self.move(x, y)

    def showEvent(self, event):
        super().showEvent(event)
        if self.window_glue is None:
            self.window_glue = hooks.Window(self)

    # -- loop --------------------------------------------------------------
    def tick(self):
        now = time.monotonic()
        dt = min(0.05, max(0.0, now - self.last))
        self.last = now
        self._drain(now)
        pos = QCursor.pos()
        desk = QGuiApplication.primaryScreen().virtualGeometry()
        self.scene.cursor_at((pos.x() - desk.x()) / max(1, desk.width()), (pos.y() - desk.y()) / max(1, desk.height()), now)
        self.scene.step(now, dt)
        self._draw()
        self.update()
        self._follow(pos)

    def _drain(self, now):
        while True:
            try:
                item = self.events.get_nowait()
            except queue.Empty:
                return
            if item[0] == 'key' and item[1]:
                self.scene.key(item[1], item[2], now, item[3])
            elif item[0] == 'button':
                self.scene.button(item[1], now)
            elif item[0] == 'cmd':
                self.command(item[1], now)

    def _draw(self):
        ratio = self.devicePixelRatioF()
        image = QImage(max(1, round(self.width() * ratio)), max(1, round(self.height() * ratio)),
                       QImage.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        image.fill(Qt.transparent)
        p = QPainter(image)
        p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
        p.scale(self.zoom, self.zoom)
        render(p, self.scene, self.art, self.zoom * ratio)
        p.end()
        self.image = image

    def paintEvent(self, event):
        if self.image is None:
            return
        p = QPainter(self)
        p.setCompositionMode(QPainter.CompositionMode_Source)
        p.drawImage(0, 0, self.image)
        p.end()

    def _follow(self, pos):
        if self.window_glue is None or self.image is None:
            return
        local = self.mapFromGlobal(pos)
        solid = False
        if self.rect().contains(local):
            ratio = self.image.devicePixelRatio()
            x = min(self.image.width() - 1, int(local.x() * ratio))
            y = min(self.image.height() - 1, int(local.y() * ratio))
            solid = self.image.pixelColor(x, y).alpha() > 24
        self.window_glue.set_through(not (solid or self.drag is not None))

    # -- commands ----------------------------------------------------------
    def command(self, text, now):
        parts = text.split()
        if not parts:
            return
        word, args = parts[0].lower(), parts[1:]
        if word == 'type':
            self.scene.tap(now, args[0] if args else None)
        elif word == 'click':
            self.scene.click(now)
        elif word in ('front', 'back'):
            self.scene.turn(now, word)
            self.remember()
        elif word in ('flip', 'turn'):
            self.scene.turn(now)
            self.remember()
        elif word in ('bigger', 'smaller'):
            self.set_zoom(self.zoom * (1.15 if word == 'bigger' else 1 / 1.15))
        elif word == 'zoom' and args:
            self.set_zoom(float(args[0]))
        elif word == 'pet' and args:
            self.use_pack(args[0])
        elif word == 'move' and len(args) == 2:
            self.move(int(float(args[0])), int(float(args[1])))
            self.remember()
        elif word == 'show':
            self.show()
            self.raise_()
        elif word == 'quit':
            QApplication.instance().quit()

    def use_pack(self, name):
        data = packs.load(name)
        self.art = Art(data)
        self.scene.set_pack(data)
        self.state['pet'] = name
        self.remember()

    def set_zoom(self, zoom):
        zoom = min(3.0, max(0.4, zoom))
        old = self.geometry()
        self.zoom = zoom
        w, h = round(W * zoom), round(H * zoom)
        self.setGeometry(old.center().x() - w // 2, old.bottom() - h, w, h)
        self.remember()

    def remember(self):
        self.state.update(x=self.x(), y=self.y(), zoom=round(self.zoom, 3), facing=self.scene.facing)
        save_state(self.state)

    # -- mouse on the pet --------------------------------------------------
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
        elif event.button() == Qt.RightButton:
            self.menu(event.globalPosition().toPoint())

    def mouseMoveEvent(self, event):
        if self.drag is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.drag is not None:
            self.drag = None
            self.remember()

    def mouseDoubleClickEvent(self, event):
        self.scene.turn(time.monotonic())
        self.remember()

    def wheelEvent(self, event):
        delta = event.angleDelta().y() or event.pixelDelta().y() * 4
        if delta:
            self.set_zoom(self.zoom * (1.0 + 0.1 * delta / 120))

    def menu(self, at):
        menu = QMenu(self)
        for label, facing in (('面朝我', 'front'), ('背朝我', 'back')):
            action = QAction(label, menu, checkable=True, checked=self.scene.facing == facing)
            action.setEnabled(facing in self.scene.frames)
            action.triggered.connect(lambda _=False, f=facing: (self.scene.turn(time.monotonic(), f), self.remember()))
            menu.addAction(action)
        menu.addSeparator()
        menu.addAction('放大', lambda: self.set_zoom(self.zoom * 1.15))
        menu.addAction('缩小', lambda: self.set_zoom(self.zoom / 1.15))
        looks = menu.addMenu('换形象')
        for name, title in packs.available().items():
            action = QAction(title, looks, checkable=True, checked=self.state.get('pet') == name)
            action.triggered.connect(lambda _=False, n=name: self.use_pack(n))
            looks.addAction(action)
        menu.addSeparator()
        menu.addAction('退出', QApplication.instance().quit)
        menu.exec(at)


def serve(sock, events):
    while True:
        try:
            conn, _ = sock.accept()
        except OSError:
            return
        with conn:
            conn.settimeout(2)
            try:
                data = conn.recv(4096).decode('utf-8', 'ignore')
                for line in data.splitlines():
                    if line.strip():
                        events.put(('cmd', line.strip()))
                conn.sendall(b'ok\n')
            except OSError:
                pass


def main(argv=None):
    parser = argparse.ArgumentParser(prog='awesome-pet run')
    parser.add_argument('--pet')
    parser.add_argument('--facing', choices=('front', 'back'))
    parser.add_argument('--zoom', type=float)
    args = parser.parse_args(argv)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    if sys.platform != 'win32':
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(('127.0.0.1', PORT))
    except OSError:
        print('小人已经在屏幕上了', flush=True)
        return 0
    sock.listen(8)
    state = load_state()
    for key in ('pet', 'facing', 'zoom'):
        if getattr(args, key) is not None:
            state[key] = getattr(args, key)
    save_state(state)
    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    hooks.hide_dock_icon()
    events = queue.SimpleQueue()
    threading.Thread(target=serve, args=(sock, events), name='pet-control', daemon=True).start()
    pet = Pet(state, events)
    pet.show()
    mode = hooks.start(events)
    print(f'小人已启动，键盘鼠标监听：{mode or "无"}', flush=True)
    code = app.exec()
    pet.remember()
    sock.close()
    return code
