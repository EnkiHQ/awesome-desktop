"""Where a real key sits on the little keyboard, so the hand reaches the same spot.

Positions are (row, fraction): row 0 is the number row, 4 is the space row,
fraction runs from the left edge (0) to the right edge (1) of the keyboard.
"""

ROWS = (
    ('`1234567890-=', 0.0),
    ('qwertyuiop[]\\', 1.5),
    ("asdfghjkl;'", 1.75),
    ('zxcvbnm,./', 2.25),
)
UNITS = 15.0

SPECIAL = {
    'esc': (0, 0.02), 'backspace': (0, 0.96), 'delete': (0, 0.98),
    'tab': (1, 0.05), 'caps_lock': (2, 0.06), 'enter': (2, 0.93),
    'shift': (3, 0.07), 'shift_l': (3, 0.07), 'shift_r': (3, 0.92),
    'space': (4, 0.5),
    'fn': (4, 0.02), 'ctrl': (4, 0.07), 'ctrl_l': (4, 0.07), 'alt': (4, 0.16), 'alt_l': (4, 0.16),
    'cmd': (4, 0.25), 'cmd_l': (4, 0.25), 'cmd_r': (4, 0.75), 'alt_r': (4, 0.83), 'ctrl_r': (4, 0.9),
    'left': (4, 0.88), 'down': (4, 0.93), 'right': (4, 0.98), 'up': (3, 0.93),
}
for _n in range(1, 13):
    SPECIAL[f'f{_n}'] = (0, (_n + 0.5) / 13.5)

MODIFIERS = {'shift', 'shift_l', 'shift_r', 'ctrl', 'ctrl_l', 'ctrl_r', 'alt', 'alt_l', 'alt_r',
             'cmd', 'cmd_l', 'cmd_r', 'fn', 'caps_lock'}

_POS = {}
for _row, (_keys, _start) in enumerate(ROWS):
    for _i, _ch in enumerate(_keys):
        _POS[_ch] = (_row, (_start + _i + 0.5) / UNITS)
_POS.update(SPECIAL)

MAC = {
    0: 'a', 1: 's', 2: 'd', 3: 'f', 4: 'h', 5: 'g', 6: 'z', 7: 'x', 8: 'c', 9: 'v', 11: 'b',
    12: 'q', 13: 'w', 14: 'e', 15: 'r', 16: 'y', 17: 't', 18: '1', 19: '2', 20: '3', 21: '4',
    22: '6', 23: '5', 24: '=', 25: '9', 26: '7', 27: '-', 28: '8', 29: '0', 30: ']', 31: 'o',
    32: 'u', 33: '[', 34: 'i', 35: 'p', 36: 'enter', 37: 'l', 38: 'j', 39: "'", 40: 'k', 41: ';',
    42: '\\', 43: ',', 44: '/', 45: 'n', 46: 'm', 47: '.', 48: 'tab', 49: 'space', 50: '`',
    51: 'backspace', 53: 'esc', 54: 'cmd_r', 55: 'cmd', 56: 'shift', 57: 'caps_lock', 58: 'alt',
    59: 'ctrl', 60: 'shift_r', 61: 'alt_r', 62: 'ctrl_r', 63: 'fn', 76: 'enter', 117: 'delete',
    122: 'f1', 120: 'f2', 99: 'f3', 118: 'f4', 96: 'f5', 97: 'f6', 98: 'f7', 100: 'f8',
    101: 'f9', 109: 'f10', 103: 'f11', 111: 'f12',
    123: 'left', 124: 'right', 125: 'down', 126: 'up',
}
MAC_MODIFIERS = {54, 55, 56, 57, 58, 59, 60, 61, 62, 63}

WIN = {
    0x08: 'backspace', 0x09: 'tab', 0x0D: 'enter', 0x10: 'shift', 0x11: 'ctrl', 0x12: 'alt',
    0x14: 'caps_lock', 0x1B: 'esc', 0x20: 'space', 0x25: 'left', 0x26: 'up', 0x27: 'right',
    0x28: 'down', 0x2E: 'delete', 0x5B: 'cmd', 0x5C: 'cmd_r', 0xA0: 'shift', 0xA1: 'shift_r',
    0xA2: 'ctrl', 0xA3: 'ctrl_r', 0xA4: 'alt', 0xA5: 'alt_r',
    0xBA: ';', 0xBB: '=', 0xBC: ',', 0xBD: '-', 0xBE: '.', 0xBF: '/', 0xC0: '`',
    0xDB: '[', 0xDC: '\\', 0xDD: ']', 0xDE: "'",
}
for _vk in range(0x41, 0x5B):
    WIN[_vk] = chr(_vk).lower()
for _vk in range(0x30, 0x3A):
    WIN[_vk] = chr(_vk)
for _n in range(1, 13):
    WIN[0x6F + _n] = f'f{_n}'

SHIFTED = dict(zip('~!@#$%^&*()_+{}|:"<>?', '`1234567890-=[]\\;\',./'))


def position(label):
    """Return (row, fraction) for a key label, or None when the key has no place."""
    if not label:
        return None
    label = SHIFTED.get(label, label)
    if len(label) == 1:
        label = label.lower()
    return _POS.get(label)


def left_hand(row, fraction):
    return fraction < 0.47


def mac_label(code):
    return MAC.get(int(code))


def win_label(vk):
    return WIN.get(int(vk))
