"""Render the main poses of a pack into one picture, without opening a window."""
import os


def preview(name, out, zoom=1.5):
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtCore import QPointF, QRectF, Qt
    from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QPainter

    from . import pack as packs
    from .render import Art, render_image
    from .scene import H, W, Scene

    app = QGuiApplication.instance() or QGuiApplication([])
    data = packs.load(name)
    art = Art(data)
    shots = []
    for facing in [f for f in ('front', 'back') if f in data.views]:
        for pose, label in (('idle', 'idle'), ('type', 'typing'), ('click', 'mouse')):
            scene = Scene(data, facing, seed=3)
            t = 0.0
            scene.cursor_at(0.5, 0.5, t)
            for _ in range(30):
                t += 1 / 60
                scene.step(t, 1 / 60)
            if pose == 'type':
                scene.key('d', True, t)
                scene.key('k', True, t)
            elif pose == 'click':
                scene.cursor_at(0.62, 0.55, t)
                scene.button(True, t)
            for _ in range(20):
                t += 1 / 60
                scene.step(t, 1 / 60)
            shots.append((f'{facing} · {label}', render_image(scene, art, zoom)))
    cell_w, cell_h = int(W * zoom), int(H * zoom)
    columns = 3
    rows = (len(shots) + columns - 1) // columns
    sheet = QImage(cell_w * columns, (cell_h + 28) * rows, QImage.Format_ARGB32_Premultiplied)
    sheet.fill(QColor('#3A3D46'))
    p = QPainter(sheet)
    p.setRenderHints(QPainter.Antialiasing | QPainter.TextAntialiasing)
    font = QFont()
    font.setPixelSize(16)
    p.setFont(font)
    for i, (label, image) in enumerate(shots):
        x, y = (i % columns) * cell_w, (i // columns) * (cell_h + 28)
        p.setPen(QColor('#FFFFFF'))
        p.drawText(QRectF(x, y + 4, cell_w, 22), Qt.AlignCenter, label)
        p.drawImage(QPointF(x, y + 28), image)
    p.end()
    sheet.save(str(out))
    del app
    return out
