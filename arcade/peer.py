"""One TCP connection and the room relay that pairs two of them.

The relay reads a single handshake line, then copies bytes both ways.
Game messages stay in :mod:`arcade.protocol`.
"""
import json
import queue
import socket
import threading

from .protocol import dumps, loads


def reader(sock, inbox):
    buf = bytearray()
    try:
        while True:
            if b'\n' not in buf:
                chunk = sock.recv(65536)
                if not chunk:
                    inbox.put(None)
                    return
                buf += chunk
                if len(buf) > 1_000_000:
                    inbox.put({'t': 'error', 'reason': '联机数据过长'})
                    return
            line, newline, rest = buf.partition(b'\n')
            if not newline:
                continue
            buf = bytearray(rest)
            if not line:
                continue
            try:
                inbox.put(loads(line))
            except json.JSONDecodeError:
                inbox.put({'t': 'error', 'reason': '无法解析的联机数据'})
                return
    except OSError:
        inbox.put(None)


class Peer:
    """A connected opponent. ``drain`` is called on the game thread."""

    def __init__(self, sock):
        self.sock = sock
        self.inbox = queue.Queue()
        self.alive = True
        self._lock = threading.Lock()
        try:
            sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass
        threading.Thread(target=reader, args=(sock, self.inbox), name='IconArcadePeer', daemon=True).start()

    def send(self, message):
        data = dumps(message)
        with self._lock:
            self.sock.sendall(data)

    def drain(self):
        messages = []
        while True:
            try:
                messages.append(self.inbox.get_nowait())
            except queue.Empty:
                return messages

    def close(self):
        self.alive = False
        try:
            self.sock.close()
        except OSError:
            pass


def _pipe(source, target):
    try:
        while True:
            data = source.recv(65536)
            if not data:
                break
            target.sendall(data)
    except OSError:
        pass
    finally:
        for sock in (source, target):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def splice(left, right):
    threading.Thread(target=_pipe, args=(left, right), daemon=True).start()
    threading.Thread(target=_pipe, args=(right, left), daemon=True).start()


def _read_one_line(sock, limit=4096):
    buf = bytearray()
    while b'\n' not in buf:
        chunk = sock.recv(1)
        if not chunk:
            return None
        buf += chunk
        if len(buf) > limit:
            raise ValueError('握手过长')
    line, _, _rest = bytes(buf).partition(b'\n')
    return loads(line)


def serve_relay(port=8770, ready=None):
    """Pair ``中继开房`` with ``中继加入``. Returns the listening socket."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('0.0.0.0', port))
    server.listen(16)
    rooms = {}
    lock = threading.Lock()

    def handle(conn):
        try:
            hello = _read_one_line(conn)
            if not hello or hello.get('t') != 'relay':
                conn.sendall(dumps({'t': 'error', 'reason': '中继握手无效'}))
                conn.close()
                return
            code = str(hello.get('code', '')).strip().upper()
            op = hello.get('op')
            if not code or op not in ('host', 'join'):
                conn.sendall(dumps({'t': 'error', 'reason': '中继房间无效'}))
                conn.close()
                return
            if op == 'host':
                holder = {'guest': None, 'event': threading.Event()}
                with lock:
                    previous = rooms.get(code)
                    rooms[code] = holder
                if previous:
                    previous['event'].set()
                conn.sendall(dumps({'t': 'relay', 'ok': True, 'role': 'host', 'code': code}))
                if not holder['event'].wait(3600) or holder['guest'] is None:
                    with lock:
                        if rooms.get(code) is holder:
                            rooms.pop(code, None)
                    conn.close()
                    return
                splice(conn, holder['guest'])
                return
            with lock:
                holder = rooms.get(code)
            if holder is None or holder['guest'] is not None:
                conn.sendall(dumps({'t': 'error', 'reason': '房间不存在或已经有人'}))
                conn.close()
                return
            holder['guest'] = conn
            conn.sendall(dumps({'t': 'relay', 'ok': True, 'role': 'guest', 'code': code}))
            holder['event'].set()
        except Exception:
            try:
                conn.close()
            except OSError:
                pass

    def accept_loop():
        while True:
            try:
                conn, _addr = server.accept()
            except OSError:
                return
            threading.Thread(target=handle, args=(conn,), daemon=True).start()

    threading.Thread(target=accept_loop, name='IconArcadeRelay', daemon=True).start()
    if ready is not None:
        ready.set()
    return server


def connect_relay(address, op, code, timeout=10):
    """Connect to a relay and return the socket after the one-line handshake."""
    host, port = address.rsplit(':', 1)
    sock = socket.create_connection((host, int(port)), timeout=timeout)
    sock.sendall(dumps({'t': 'relay', 'op': op, 'code': code}))
    ack = _read_one_line(sock)
    if not ack or not ack.get('ok'):
        reason = (ack or {}).get('reason', '中继拒绝了连接')
        sock.close()
        raise ConnectionError(reason)
    return sock
