"""Layout and motion of the desk scene, without any drawing code.

Coordinates are in a fixed 360 x 420 canvas; the window scales it. Hands live
in keyboard space (fraction across the keyboard, row) so they keep their place
when the character turns around.
"""
import math
import random
from dataclasses import dataclass

from . import keys

W, H = 360.0, 420.0
FLIP_SECONDS = 0.34


@dataclass
class Rect:
    x: float
    y: float
    w: float
    h: float

    @property
    def cx(self):
        return self.x + self.w / 2

    @property
    def cy(self):
        return self.y + self.h / 2

    @property
    def right(self):
        return self.x + self.w

    @property
    def bottom(self):
        return self.y + self.h


@dataclass
class Frame:
    facing: str
    scale: float
    body: Rect
    shoulders: tuple
    arm: float
    line: float
    desk: Rect
    desk_front: float
    keyboard: Rect
    pad: Rect
    mouse: tuple
    monitor: Rect = None
    eyes: tuple = ()


def build_frame(view, facing):
    iw, ih = view.size
    if facing == 'front':
        desk_top, desk_front, desk_bottom = H * 0.60, H * 0.79, H * 0.985
        desk_line = view.desk if view.desk else ih * 0.62
        s = min((desk_top - H * 0.03) / desk_line, W * 0.98 / iw)
        body = Rect((W - iw * s) / 2, desk_top - desk_line * s, iw * s, ih * s)
        keyboard = Rect(W * 0.18, desk_top + (desk_front - desk_top) * 0.13, W * 0.48, (desk_front - desk_top) * 0.74)
        pad = Rect(W * 0.70, desk_top + (desk_front - desk_top) * 0.12, W * 0.24, (desk_front - desk_top) * 0.76)
        desk = Rect(W * 0.02, desk_top, W * 0.96, desk_bottom - desk_top)
        monitor = None
    else:
        s = min(H * 0.62 / ih, W * 0.70 / iw)
        body = Rect((W - iw * s) / 2, H * 0.985 - ih * s, iw * s, ih * s)
        shoulder_y = body.y + view.shoulders[0][1] * s
        torso = (view.shoulders[1][0] - view.shoulders[0][0]) * s
        desk_top = shoulder_y + torso * 0.3
        desk_front = desk_top + H * 0.11
        desk_bottom = min(H * 0.985, desk_front + H * 0.1)
        band = desk_front - desk_top
        desk = Rect(W * 0.02, desk_top, W * 0.96, desk_bottom - desk_top)
        keyboard = Rect(W * 0.22, desk_top + band * 0.12, W * 0.5, band * 0.76)
        pad = Rect(W * 0.74, desk_top + band * 0.1, W * 0.2, band * 0.8)
        monitor = Rect(W * 0.08, desk_top - H * 0.52, W * 0.84, H * 0.5)
    shoulders = tuple((body.x + x * s, body.y + y * s) for x, y in view.shoulders)
    mouse = (pad.w * 0.42, pad.h * 0.62)
    eyes = tuple((body.x + x0 * s, body.y + y0 * s, (x1 - x0) * s, (y1 - y0) * s) for x0, y0, x1, y1 in view.eyes)
    return Frame(facing, s, body, shoulders, view.arm * s, max(1.4, view.line * s), desk,
                 desk_front, keyboard, pad, mouse, monitor, eyes)


def keyboard_point(kb, row, frac):
    pad_x, pad_y = kb.w * 0.045, kb.h * 0.09
    row_h = (kb.h - 2 * pad_y) / 5
    return kb.x + pad_x + frac * (kb.w - 2 * pad_x), kb.y + pad_y + (row + 0.5) * row_h


def key_cell(row, frac):
    col = max(0, min(11, int(frac * 12)))
    if row == 4 and 3 <= col <= 8:
        return (4, 'space')
    return (row, col)


class Hand:
    def __init__(self, frac, row):
        self.u = self.tu = frac
        self.v = self.tv = row
        self.m = self.tm = 0.0
        self.press = 0.0
        self.press_target = 0.0
        self.release_at = None
        self.pressed_at = -1e9
        self.last = -1e9


class Scene:
    def __init__(self, pack, facing='front', seed=None):
        self.rng = random.Random(seed)
        self.pack = pack
        self.frames = {f: build_frame(v, f) for f, v in pack.views.items()}
        self.facing = facing if facing in self.frames else 'front'
        self.flip_from = self.facing
        self.flip_start = None
        self.rest_left = keys.position('f')
        self.rest_right = keys.position('j')
        self.left = Hand(self.rest_left[1], self.rest_left[0])
        self.right = Hand(self.rest_right[1], self.rest_right[0])
        self.held = {}
        self.lit = {}
        self.mouse_down = False
        self.cursor = None
        self.vmouse = [0.0, 0.0]
        self.vmouse_target = [0.0, 0.0]
        self.dip = 0.0
        self.blink_at = 1.5
        self.blink_start = None
        self.code = [[]]
        self.space_hand = 'left'
        self.pending = []
        self.now = 0.0

    def set_pack(self, pack):
        self.pack = pack
        self.frames = {f: build_frame(v, f) for f, v in pack.views.items()}
        if self.facing not in self.frames:
            self.facing = 'front'
        self.flip_start = None

    # -- input -------------------------------------------------------------
    def key(self, label, down, now, repeat=False):
        if label == 'f12':
            if down and not repeat:
                self.turn(now)
            return
        pos = keys.position(label)
        if pos is None:
            pos = (2, self.rng.uniform(0.2, 0.8))
        row, frac = pos
        if down:
            if row == 4 and label == 'space':
                hand = self.left if self.right.tm > 0.5 or self.space_hand == 'right' else self.right
                self.space_hand = 'left' if hand is self.left else 'right'
            else:
                hand = self.left if keys.left_hand(row, frac) else self.right
            if hand is self.right:
                self.right.tm = 0.0
            hand.tu, hand.tv = frac, row
            hand.press_target = 1.0
            hand.pressed_at = now
            hand.release_at = None
            hand.last = now
            cell = key_cell(row, frac)
            self.lit[cell] = [True, 0.0]
            self.held[label] = (hand, cell)
            self.dip = 1.0 if not repeat else max(self.dip, 0.6)
            if not repeat:
                self._type_code(label)
        else:
            entry = self.held.pop(label, None)
            if entry:
                hand, cell = entry
                hand.release_at = max(now, hand.pressed_at + 0.07)
                self.lit[cell] = [False, max(now, hand.pressed_at + 0.07) + 0.06]

    def button(self, down, now):
        self.mouse_down = down
        self.right.tm = 1.0
        self.right.last = now
        if down:
            self.right.press_target = 1.0
            self.right.pressed_at = now
            self.right.release_at = None
        else:
            self.right.release_at = max(now, self.right.pressed_at + 0.08)

    def cursor_at(self, fx, fy, now):
        if self.cursor is not None:
            moved = abs(fx - self.cursor[0]) + abs(fy - self.cursor[1])
            if moved > 0.0025:
                self.right.tm = 1.0
                self.right.last = now
        self.cursor = (fx, fy)
        self.vmouse_target = [(fx - 0.5) * 0.62, (fy - 0.5) * 0.5]

    def tap(self, now, label=None):
        label = label or self.rng.choice('asdfjkl;ghqweruiop')
        self.key(label, True, now)
        self.pending.append((now + 0.11, lambda t: self.key(label, False, t)))

    def click(self, now):
        self.button(True, now)
        self.pending.append((now + 0.14, lambda t: self.button(False, t)))

    def turn(self, now, facing=None):
        target = facing or ('back' if self.facing == 'front' else 'front')
        if target not in self.frames or target == self.facing:
            return
        self.flip_from = self.facing
        self.facing = target
        self.flip_start = now

    # -- motion ------------------------------------------------------------
    def step(self, now, dt):
        self.now = now
        due = [p for p in self.pending if p[0] <= now]
        self.pending = [p for p in self.pending if p[0] > now]
        for _, action in due:
            action(now)
        move = 1 - math.exp(-dt * 24)
        blend = 1 - math.exp(-dt * 13)
        snap = 1 - math.exp(-dt * 48)
        for hand, rest in ((self.left, self.rest_left), (self.right, self.rest_right)):
            busy = any(h is hand for h, _ in self.held.values())
            if hand.release_at is not None and now >= hand.release_at and not busy:
                if not (hand is self.right and self.mouse_down):
                    hand.press_target = 0.0
                hand.release_at = None
            if not busy and now - hand.last > 0.9 and hand.press_target == 0.0:
                hand.tu, hand.tv = rest[1], rest[0]
            hand.u += (hand.tu - hand.u) * move
            hand.v += (hand.tv - hand.v) * move
            hand.m += (hand.tm - hand.m) * blend
            hand.press += (hand.press_target - hand.press) * snap
        self.vmouse[0] += (self.vmouse_target[0] - self.vmouse[0]) * (1 - math.exp(-dt * 30))
        self.vmouse[1] += (self.vmouse_target[1] - self.vmouse[1]) * (1 - math.exp(-dt * 30))
        self.dip *= math.exp(-dt * 9)
        for cell in [c for c, (held, until) in self.lit.items() if not held and until <= now]:
            del self.lit[cell]
        if now >= self.blink_at and self.blink_start is None:
            self.blink_start = now
        if self.blink_start is not None and now - self.blink_start > 0.16:
            self.blink_start = None
            self.blink_at = now + self.rng.uniform(2.2, 5.5)
        if self.flip_start is not None and now - self.flip_start > FLIP_SECONDS:
            self.flip_start = None

    # -- what to draw ------------------------------------------------------
    def view(self):
        """Return (frame, horizontal squash) for the current moment of a turn."""
        if self.flip_start is None:
            return self.frames[self.facing], 1.0
        p = min(1.0, (self.now - self.flip_start) / FLIP_SECONDS)
        facing = self.flip_from if p < 0.5 else self.facing
        return self.frames[facing], abs(math.cos(math.pi * p))

    def bob(self):
        return 1.2 * math.sin(self.now * 2 * math.pi / 3.4) + 2.2 * self.dip

    def blink(self):
        if self.blink_start is None:
            return 0.0
        t = (self.now - self.blink_start) / 0.16
        return max(0.0, 1 - abs(2 * t - 1) * 1.15)

    def mouse_center(self, frame):
        return frame.pad.cx + self.vmouse[0] * frame.pad.w, frame.pad.cy + self.vmouse[1] * frame.pad.h

    def hand_points(self, frame):
        points = []
        for hand in (self.left, self.right):
            kx, ky = keyboard_point(frame.keyboard, hand.v, hand.u)
            mx, my = self.mouse_center(frame)
            if frame.facing == 'front':
                ky -= frame.keyboard.h * 0.06
                my -= frame.mouse[1] * 0.18
            x = kx + (mx - kx) * hand.m
            y = ky + (my - ky) * hand.m + hand.press * frame.arm * 0.12
            points.append((x, y, hand.press))
        return points

    def key_lit(self, cell):
        return cell in self.lit

    def _type_code(self, label):
        if label in keys.MODIFIERS or label.startswith('f') and label[1:].isdigit() or label in ('left', 'right', 'up', 'down', 'esc'):
            return
        line = self.code[-1]
        if label == 'enter':
            self.code.append([])
        elif label in ('backspace', 'delete'):
            if line:
                line.pop()
            elif len(self.code) > 1:
                self.code.pop()
        elif label == 'space':
            line.append((self.rng.uniform(2.5, 4.0), None))
        else:
            line.append((self.rng.uniform(3.0, 7.5), self.rng.randrange(4)))
            if sum(w for w, _ in line) > 60:
                self.code.append([])
        if len(self.code) > 9:
            self.code = self.code[-9:]
