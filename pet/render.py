"""Paint one moment of the desk scene with QPainter."""
import math

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QImage, QPainter, QPainterPath, QPen, QPixmap

from .scene import H, W, key_cell

WOOD_TOP = QColor('#C68F55')
WOOD_FRONT = QColor('#955A30')
GRAIN = QColor(60, 30, 10, 55)
KB_BASE = QColor('#2B2D31')
KEY = QColor('#E8E8E8')
KEY_EDGE = QColor('#9EA1A7')
KEY_LIT = QColor('#F6C23A')
PAD = QColor('#3D5B88')
MOUSE = QColor('#F7F7F7')
MOUSE_LINE = QColor('#B9B9B9')
MOUSE_LIT = QColor('#FF7A5C')
MONITOR = QColor('#2F3138')
SCREEN = QColor('#14211A')
CODE = (QColor('#7ED8A5'), QColor('#F6C23A'), QColor('#8DB6FF'), QColor('#FF8D8D'))


class Art:
    """The pack's pictures, rescaled once per zoom so they stay sharp."""

    def __init__(self, pack):
        self.pack = pack
        self.images = {f: QImage(str(v.image)) for f, v in pack.views.items()}
        lids = pack.root / 'lids.png'
        self.lid_image = QImage(str(lids)) if lids.is_file() else None
        self.skin = QColor(pack.skin)
        self.ink = QColor(pack.outline)
        self.cache = {}

    def _scaled(self, key, image, w, h, ratio):
        size = (int(round(w * ratio)), int(round(h * ratio)))
        hit = self.cache.get(key)
        if hit and hit[0] == size:
            return hit[1]
        pixmap = QPixmap.fromImage(image.scaled(size[0], size[1], Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
        self.cache[key] = (size, pixmap)
        return pixmap

    def body(self, facing, rect, ratio):
        return self._scaled(('body', facing), self.images[facing], rect.w, rect.h, ratio)

    def lids(self, rect, ratio):
        if self.lid_image is None or self.lid_image.isNull():
            return None
        return self._scaled(('lids',), self.lid_image, rect.w, rect.h, ratio)


def render(p, scene, art, ratio):
    frame, squash = scene.view()
    p.save()
    if squash < 0.999:
        p.translate(W / 2, H * 0.62)
        p.scale(max(squash, 0.03), 1.0 + (1 - squash) * 0.05)
        p.translate(-W / 2, -H * 0.62)
    if frame.facing == 'front':
        _front(p, scene, frame, art, ratio)
    else:
        _back(p, scene, frame, art, ratio)
    p.restore()


def _pen(art, width, color=None):
    return QPen(color or art.ink, width, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)


def _prop_line(frame):
    return max(1.3, min(3.0, frame.line * 0.8))


def _draw_body(p, frame, art, ratio, oy):
    body = frame.body
    pixmap = art.body(frame.facing, body, ratio)
    p.drawPixmap(QRectF(body.x, body.y + oy, body.w, body.h), pixmap, QRectF(0, 0, pixmap.width(), pixmap.height()))


def _front(p, scene, frame, art, ratio):
    oy = scene.bob()
    _draw_body(p, frame, art, ratio, oy)
    _blink(p, scene, frame, art, ratio, oy)
    _desk(p, frame, art)
    _keyboard(p, scene, frame, art)
    _mouse(p, scene, frame, art)
    _arms(p, scene, frame, art, oy, front=True)


def _back(p, scene, frame, art, ratio):
    oy = scene.bob()
    _monitor(p, scene, frame, art)
    _desk(p, frame, art)
    _keyboard(p, scene, frame, art)
    _mouse(p, scene, frame, art)
    _arms(p, scene, frame, art, oy, front=False)
    _draw_body(p, frame, art, ratio, oy)


def _desk(p, frame, art):
    d = frame.desk
    line = _prop_line(frame)
    p.setPen(_pen(art, line))
    p.setBrush(WOOD_FRONT)
    p.drawRoundedRect(QRectF(d.x, frame.desk_front - 6, d.w, d.bottom - frame.desk_front + 6), 7, 7)
    p.setBrush(WOOD_TOP)
    p.drawRoundedRect(QRectF(d.x, d.y, d.w, frame.desk_front - d.y), 7, 7)
    p.setPen(QPen(GRAIN, max(1.0, line * 0.55), Qt.SolidLine, Qt.RoundCap))
    face = d.bottom - frame.desk_front
    for i, (a, b) in enumerate(((0.08, 0.30), (0.42, 0.71), (0.18, 0.55), (0.66, 0.92))):
        y = frame.desk_front + face * (0.3 + 0.18 * (i % 3))
        if y < d.bottom - 4:
            p.drawLine(QPointF(d.x + d.w * a, y), QPointF(d.x + d.w * b, y))


def _keyboard(p, scene, frame, art):
    kb = frame.keyboard
    line = _prop_line(frame)
    p.setPen(_pen(art, line))
    p.setBrush(KB_BASE)
    p.drawRoundedRect(QRectF(kb.x, kb.y, kb.w, kb.h), 5, 5)
    pad_x, pad_y = kb.w * 0.045, kb.h * 0.09
    row_h = (kb.h - 2 * pad_y) / 5
    key_w = (kb.w - 2 * pad_x) / 12
    gap = min(key_w, row_h) * 0.18
    depth = row_h * 0.2
    p.setPen(Qt.NoPen)
    for row in range(5):
        y = kb.y + pad_y + row * row_h
        if row < 4:
            cells = [((row, c), c, 1) for c in range(12)]
        else:
            cells = [((4, c), c, 1) for c in (0, 1, 2)] + [((4, 'space'), 3, 6)] + [((4, c), c, 1) for c in (9, 10, 11)]
        for cell, col, span in cells:
            rect = QRectF(kb.x + pad_x + col * key_w + gap / 2, y + gap / 2, key_w * span - gap, row_h - gap)
            lit = scene.key_lit(cell)
            radius = min(rect.width(), rect.height()) * 0.28
            p.setBrush(KEY_EDGE)
            p.drawRoundedRect(rect, radius, radius)
            face = QRectF(rect.x(), rect.y() + (depth if lit else 0), rect.width(), rect.height() - depth)
            p.setBrush(KEY_LIT if lit else KEY)
            p.drawRoundedRect(face, radius, radius)


def _mouse(p, scene, frame, art):
    pad = frame.pad
    line = _prop_line(frame)
    p.setPen(_pen(art, line))
    p.setBrush(PAD)
    p.drawRoundedRect(QRectF(pad.x, pad.y, pad.w, pad.h), 8, 8)
    mx, my = scene.mouse_center(frame)
    mw, mh = frame.mouse
    down = scene.mouse_down
    body = QRectF(mx - mw / 2, my - mh / 2 + (1.2 if down else 0), mw, mh - (1.2 if down else 0))
    shape = QPainterPath()
    shape.addRoundedRect(body, mw * 0.46, mw * 0.46)
    p.setBrush(MOUSE)
    p.drawPath(shape)
    split = body.y() + body.height() * 0.42
    if down:
        p.save()
        p.setClipPath(shape)
        p.setPen(Qt.NoPen)
        p.setBrush(MOUSE_LIT)
        p.drawRect(QRectF(body.x(), body.y(), body.width() / 2, split - body.y()))
        p.restore()
        p.setPen(_pen(art, line))
        p.setBrush(Qt.NoBrush)
        p.drawPath(shape)
    p.setPen(QPen(MOUSE_LINE, max(1.0, line * 0.6), Qt.SolidLine, Qt.RoundCap))
    p.drawLine(QPointF(body.center().x(), body.y() + line), QPointF(body.center().x(), split))
    p.drawLine(QPointF(body.x() + line * 1.5, split), QPointF(body.right() - line * 1.5, split))


def _monitor(p, scene, frame, art):
    m = frame.monitor
    if m is None:
        return
    line = _prop_line(frame)
    p.setPen(_pen(art, line))
    p.setBrush(MONITOR)
    p.drawRect(QRectF(m.cx - m.w * 0.05, m.bottom - 4, m.w * 0.10, frame.desk.y - m.bottom + 10))
    p.drawRoundedRect(QRectF(m.cx - m.w * 0.17, frame.desk.y + 1, m.w * 0.34, 9), 4, 4)
    p.drawRoundedRect(QRectF(m.x, m.y, m.w, m.h), 9, 9)
    screen = QRectF(m.x + 9, m.y + 9, m.w - 18, m.h - 18)
    p.setPen(Qt.NoPen)
    p.setBrush(SCREEN)
    p.drawRoundedRect(screen, 4, 4)
    lines = scene.code[-9:]
    lh = screen.height() / 10
    unit = screen.width() * 0.86 / 60
    y = screen.y() + lh * 0.55
    end = (screen.x() + 10, y)
    for row in lines:
        x = screen.x() + 10
        for width, color in row:
            w = width * unit
            if color is not None:
                p.setBrush(CODE[color])
                p.drawRoundedRect(QRectF(x, y, w, lh * 0.48), 2, 2)
            x += w + unit * 0.8
        end = (x, y)
        y += lh
    if int(scene.now * 2.2) % 2 == 0:
        p.setBrush(CODE[0])
        p.drawRect(QRectF(end[0], end[1], unit * 2.2, lh * 0.48))


def _arms(p, scene, frame, art, oy, front):
    points = scene.hand_points(frame)
    width = frame.arm
    line = frame.line
    strokes = []
    for i, (hx, hy, press) in enumerate(points):
        sx, sy = frame.shoulders[i]
        side = -1 if i == 0 else 1
        if front:
            sx -= side * width * 0.32
            sy += oy + width * 0.25
        else:
            sx -= side * width * 0.55
            sy += oy + width * 0.3
        dx, dy = hx - sx, hy - sy
        length = math.hypot(dx, dy) or 1.0
        nx, ny = -dy / length, dx / length
        if nx * side < 0:
            nx, ny = -nx, -ny
        bulge = length * (0.2 if front else 0.14)
        drop = length * (0.06 if front else 0.3)
        cx = (sx + hx) / 2 + nx * bulge
        cy = (sy + hy) / 2 + ny * bulge + drop
        path = QPainterPath(QPointF(sx, sy))
        path.quadTo(QPointF(cx, cy), QPointF(hx, hy))
        rx = width * 0.64 * (1 + 0.1 * press)
        ry = width * 0.58 * (1 - 0.16 * press)
        strokes.append((path, QRectF(hx - rx, hy - ry, rx * 2, ry * 2)))
    p.setBrush(Qt.NoBrush)
    for path, hand in strokes:
        p.setPen(_pen(art, width + line * 2))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(art.ink)
        p.drawEllipse(hand.adjusted(-line, -line, line, line))
        p.setBrush(Qt.NoBrush)
    for path, hand in strokes:
        p.setPen(_pen(art, width, art.skin))
        p.drawPath(path)
        p.setPen(Qt.NoPen)
        p.setBrush(art.skin)
        p.drawEllipse(hand)
        p.setBrush(Qt.NoBrush)


def _blink(p, scene, frame, art, ratio, oy):
    amount = scene.blink()
    if amount <= 0 or not frame.eyes:
        return
    lids = art.lids(frame.body, ratio)
    if lids is None:
        return
    body = frame.body
    target = QRectF(body.x, body.y + oy, body.w, body.h)
    source = QRectF(0, 0, lids.width(), lids.height())
    for x, y, w, h in frame.eyes:
        y += oy
        p.save()
        p.setClipRect(QRectF(x - 3, y - 3, w + 6, h * amount + 3))
        p.drawPixmap(target, lids, source)
        p.restore()
        edge = y + h * min(amount, 0.8)
        oval = QPainterPath()
        oval.addEllipse(QRectF(x, y, w, h))
        p.save()
        p.setClipPath(oval)
        p.setPen(_pen(art, frame.line * 0.9))
        lash = QPainterPath(QPointF(x, edge))
        lash.quadTo(QPointF(x + w / 2, edge + h * 0.14 * amount), QPointF(x + w, edge))
        p.drawPath(lash)
        p.restore()


def render_image(scene, art, zoom=1.0, ratio=1.0):
    image = QImage(int(round(W * zoom * ratio)), int(round(H * zoom * ratio)), QImage.Format_ARGB32_Premultiplied)
    image.setDevicePixelRatio(ratio)
    image.fill(Qt.transparent)
    p = QPainter(image)
    p.setRenderHints(QPainter.Antialiasing | QPainter.SmoothPixmapTransform)
    p.scale(zoom, zoom)
    render(p, scene, art, zoom * ratio)
    p.end()
    return image
