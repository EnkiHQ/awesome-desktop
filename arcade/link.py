"""The object the Windows table calls once per frame.

``before`` applies the opponent. ``after`` publishes this side. With no
environment and no ``联机.txt``, :func:`link_from_env` returns None and the
table stays the original local game.
"""
import os
import secrets
import socket
import tempfile
import threading
from pathlib import Path

from .peer import Peer, connect_relay
from .protocol import apply_snapshot, capture, world_point

AIM_INTERVAL = 0.05
SNAP_INTERVAL = 0.05


def _room_file(text):
    path = Path(tempfile.gettempdir()) / 'awesome-desktop-room.txt'
    path.write_text(text, encoding='utf-8')
    return path


class NetLink:
    """One side of a billiards match. The host is the only simulation."""

    def __init__(self, role, peer=None, listener=None):
        self.role = role
        self.peer = peer
        self.listener = listener
        self.peer_ready = False
        self.message = '等待对手'
        self.snapshot = None
        self.pending_aim = None
        self.pending_shot = None
        self._hello_sent = False
        self._queued = None
        self._last_aim_at = 0.0
        self._last_snap_at = -1.0
        self._last_sig = None
        self._closed = False

    def before(self, table, now):
        if self._closed or self.peer is None:
            return
        self._handshake(table)
        self._drain(table, now)
        if self.role == 'guest' and self.peer_ready and self.snapshot is not None:
            apply_snapshot(table, self.snapshot)

    def after(self, table, now):
        if self._closed or self.peer is None or not self.peer_ready:
            return
        try:
            if self.role == 'host':
                self._publish(table, now)
            elif self._queued is not None:
                self.peer.send(self._queued)
                self._queued = None
        except OSError as exc:
            self.peer_ready = False
            self.message = f'联机中断：{exc}'

    def note_intent(self, intent, now):
        """Queue the guest's latest aim, or a shot, to be sent in :meth:`after`."""
        if not intent or not self.peer_ready:
            return
        if intent['t'] == 'aim':
            if now - self._last_aim_at < AIM_INTERVAL:
                return
            self._last_aim_at = now
        self._queued = intent

    def allow_local(self, table):
        """The host may use the mouse on even shot counts. Before anyone joins, play solo."""
        if self.role != 'host' or not self.peer_ready:
            return True
        if table.state != 'ready':
            return True
        return table.shots % 2 == 0

    def close(self):
        self._closed = True
        self.peer_ready = False
        if self.peer is not None:
            self.peer.close()
        if self.listener is not None:
            try:
                self.listener.close()
            except OSError:
                pass

    def _handshake(self, table):
        if self._hello_sent:
            return
        self.peer.send({
            't': 'hello',
            'role': self.role,
            'game': 'billiards',
            'balls': len(table.icons),
        })
        self._hello_sent = True

    def _drain(self, table, now):
        try:
            messages = self.peer.drain()
        except OSError:
            self.peer_ready = False
            return
        for message in messages:
            if message is None:
                self.peer_ready = False
                self.message = '对手已断开'
                return
            kind = message.get('t')
            if kind == 'hello':
                if message.get('game') not in (None, 'billiards'):
                    self._fail(table, '对方不是台球这一局')
                    return
                if message.get('balls') != len(table.icons):
                    self._fail(table, f"图标数量不一致：这边 {len(table.icons)}，对面 {message.get('balls')}")
                    return
                self.peer_ready = True
                self.message = '已连上，轮流击球。偶数杆这边，奇数杆对面。'
            elif kind == 'error':
                self.peer_ready = False
                self.message = message.get('reason') or '联机失败'
            elif kind == 'aim' and self.role == 'host':
                self.pending_aim = message
            elif kind == 'shot' and self.role == 'host':
                self.pending_shot = message
            elif kind == 'snap' and self.role == 'guest':
                self.snapshot = message
        self._apply_guest(table, now)

    def _fail(self, table, reason):
        self.peer_ready = False
        self.message = reason
        try:
            self.peer.send({'t': 'error', 'reason': reason})
        except OSError:
            pass

    def _apply_guest(self, table, now):
        if self.role != 'host' or not self.peer_ready:
            return
        guest_turn = table.state == 'ready' and table.shots % 2 == 1
        if not guest_turn:
            if table.shots % 2 == 0:
                self.pending_shot = None
            return
        aim = self.pending_shot or self.pending_aim
        if aim is not None:
            x, y = world_point(table, aim['u'], aim['v'])
            table.aim_at(x, y)
            if 'power' in aim and aim is self.pending_aim:
                table.charge = aim.get('power') or 0
        if self.pending_shot is not None:
            shot = self.pending_shot
            self.pending_shot = None
            x, y = world_point(table, shot['u'], shot['v'])
            table.aim_at(x, y)
            table.shoot(shot['power'], now)

    def _publish(self, table, now):
        signature = (table.state, table.shots, table.pocketed_icons, round(table.white.x, 1), round(table.white.y, 1))
        if signature == self._last_sig and now - self._last_snap_at < SNAP_INTERVAL:
            return
        self._last_sig = signature
        self._last_snap_at = now
        self.peer.send(capture(table))


def _accept(link):
    while link.peer is None and not link._closed and link.listener is not None:
        try:
            conn, _addr = link.listener.accept()
        except socket.timeout:
            continue
        except OSError:
            return
        link.peer = Peer(conn)
        link.message = '对手已连上，等待问候'
        return


def listen_host(port):
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', port))
    server.listen(1)
    server.settimeout(0.5)
    link = NetLink('host', listener=server)
    link.message = f'本机开房，端口 {port}'
    threading.Thread(target=_accept, args=(link,), name='IconArcadeAccept', daemon=True).start()
    _room_file(f'开房\n端口 {port}\n把这台电脑的 IP 和端口告诉对方。\n对方在联机.txt 写：加入 IP:{port}\n')
    return link


def connect_guest(address, timeout=10):
    host, port = address.rsplit(':', 1)
    sock = socket.create_connection((host, int(port)), timeout=timeout)
    link = NetLink('guest', peer=Peer(sock))
    link.message = f'已连接 {address}'
    return link


def _parse_file(text):
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        parts = line.split()
        command = parts[0]
        if command == '开房':
            return ('host', int(parts[1]) if len(parts) > 1 else 8766)
        if command == '加入' and len(parts) > 1:
            return ('join', parts[1])
        if command == '中继开房' and len(parts) > 1:
            return ('relay-host', parts[1], parts[2] if len(parts) > 2 else secrets.token_hex(2).upper())
        if command == '中继加入' and len(parts) > 2:
            return ('relay-join', parts[2], parts[1].upper())
    return None


def _from_env():
    relay = os.environ.get('ARCADE_RELAY', '').strip()
    if relay:
        # host@地址  or  join:房间@地址
        if relay.startswith('join:'):
            code, address = relay[5:].split('@', 1)
            return ('relay-join', address, code.upper())
        address = relay.split('@', 1)[-1]
        code = relay.split('@', 1)[0] if '@' in relay and not relay.startswith('host') else secrets.token_hex(2).upper()
        if code in ('', 'host'):
            code = secrets.token_hex(2).upper()
        return ('relay-host', address, code)
    host = os.environ.get('ARCADE_HOST', '').strip()
    if host:
        return ('host', int(host) if host.isdigit() else 8766)
    join = os.environ.get('ARCADE_JOIN', '').strip()
    if join:
        return ('join', join)
    return None


def link_from_env(base=None):
    """Build a match from the environment or from ``联机.txt``. None means local play."""
    choice = _from_env()
    if choice is None and base is not None:
        for path in (Path(base) / '联机.txt', Path.cwd() / '联机.txt'):
            if path.is_file():
                choice = _parse_file(path.read_text(encoding='utf-8'))
                if choice:
                    break
    if choice is None:
        return None
    kind = choice[0]
    if kind == 'host':
        return listen_host(choice[1])
    if kind == 'join':
        return connect_guest(choice[1])
    if kind == 'relay-host':
        _address, code = choice[1], choice[2]
        sock = connect_relay(_address, 'host', code)
        link = NetLink('host', peer=Peer(sock))
        link.message = f'中继房间 {code}'
        _room_file(f'中继开房\n房间 {code}\n中继 {_address}\n对方写：中继加入 {code} {_address}\n')
        print(f'awesome-desktop 房间 {code}  中继 {_address}', flush=True)
        return link
    if kind == 'relay-join':
        _address, code = choice[1], choice[2]
        sock = connect_relay(_address, 'join', code)
        link = NetLink('guest', peer=Peer(sock))
        link.message = f'加入房间 {code}'
        return link
    raise ValueError(f'无法识别的联机设置：{choice!r}')
