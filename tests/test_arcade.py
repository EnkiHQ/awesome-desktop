"""Online match and the game catalogue. These tests do not need Windows."""
import socket
import threading
import time
import unittest

from arcade.games import GAMES, by_id
from arcade.link import NetLink
from arcade.peer import Peer, connect_relay, serve_relay
from arcade.protocol import apply_snapshot, capture
from dib.table import BilliardsMotion


def table(size=(0, 0, 1600, 1000), count=5):
    return BilliardsMotion(size, [(64, 64)] * count)


def pair():
    left, right = socket.socketpair()
    return NetLink('host', peer=Peer(left)), NetLink('guest', peer=Peer(right))


def until(predicate, timeout=2):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def shake(host, guest, host_table, guest_table):
    def pump():
        host.before(host_table, 0)
        guest.before(guest_table, 0)
        return host.peer_ready and guest.peer_ready
    if not until(pump):
        raise AssertionError(f'握手失败 host={host.message!r} guest={guest.message!r}')


class CatalogueTests(unittest.TestCase):
    def test_billiards_is_playable_and_breakout_is_only_planned(self):
        self.assertEqual([game.id for game in GAMES], ['billiards', 'breakout'])
        self.assertTrue(by_id('billiards').playable)
        self.assertFalse(by_id('breakout').playable)
        self.assertIn('横杆', by_id('breakout').summary)


class SnapshotTests(unittest.TestCase):
    def test_roundtrip_keeps_the_shot_on_a_different_resolution(self):
        host = table()
        guest = table((0, 0, 800, 500))
        host.aim = (1., 0.)
        host.shoot(1, 0)
        for frame in range(8):
            host.step(0.05, frame * 0.05)
        apply_snapshot(guest, capture(host))
        host_left, _, host_right, _ = host.bounds
        guest_left, _, guest_right, _ = guest.bounds
        host_ratio = (host.white.x - host_left) / (host_right - host_left)
        guest_ratio = (guest.white.x - guest_left) / (guest_right - guest_left)
        self.assertAlmostEqual(host_ratio, guest_ratio, places=3)
        self.assertEqual(guest.shots, host.shots)
        self.assertEqual(guest.state, host.state)


class MatchTests(unittest.TestCase):
    def test_guest_follows_the_host_shot(self):
        host_table = table()
        guest_table = table((0, 0, 800, 500))
        host, guest = pair()
        self.addCleanup(host.close)
        self.addCleanup(guest.close)
        shake(host, guest, host_table, guest_table)
        self.assertTrue(host.peer_ready)
        self.assertTrue(guest.peer_ready)
        host_table.aim = (1., 0.)
        self.assertTrue(host.allow_local(host_table))
        host_table.shoot(1, 0)
        start = (guest_table.white.x - guest_table.bounds[0]) / guest_table.width

        def frame(now):
            host.before(host_table, now)
            host_table.step(0.05, now)
            host.after(host_table, now)
            guest.before(guest_table, now)
            moved = (guest_table.white.x - guest_table.bounds[0]) / guest_table.width
            return moved > start + 0.02

        self.assertTrue(until(lambda: frame(time.time())))
        self.assertEqual(host_table.shots, 1)

    def test_guest_shot_is_taken_on_the_guest_turn_only(self):
        host_table = table()
        guest_table = table()
        host, guest = pair()
        self.addCleanup(host.close)
        self.addCleanup(guest.close)
        shake(host, guest, host_table, guest_table)
        guest.note_intent({'t': 'shot', 'u': 0.9, 'v': 0.5, 'power': 0.8}, 1)
        self.assertTrue(until(lambda: guest.after(guest_table, 1) or host.before(host_table, 1) or host_table.shots == 0))
        self.assertEqual(host_table.shots, 0)
        self.assertEqual(host_table.state, 'ready')
        host_table.shots = 1
        guest.note_intent({'t': 'shot', 'u': 0.9, 'v': 0.5, 'power': 0.8}, 2)

        def guest_shot():
            guest.after(guest_table, 2)
            host.before(host_table, 2)
            return host_table.shots == 2 and host_table.state == 'stroke'

        self.assertTrue(until(guest_shot))

    def test_different_ball_counts_are_rejected(self):
        host_table = table(count=5)
        guest_table = table(count=6)
        host, guest = pair()
        self.addCleanup(host.close)
        self.addCleanup(guest.close)
        def rejected():
            host.before(host_table, 1)
            guest.before(guest_table, 1)
            return (not host.peer_ready) and ('不一致' in host.message)
        self.assertTrue(until(rejected))


class RelayTests(unittest.TestCase):
    def test_relay_pairs_a_room_and_passes_a_hello(self):
        ready = threading.Event()
        server = serve_relay(0, ready=ready)
        self.addCleanup(server.close)
        ready.wait(2)
        port = server.getsockname()[1]
        address = f'127.0.0.1:{port}'
        host_sock = connect_relay(address, 'host', 'AB12')
        guest_sock = connect_relay(address, 'join', 'AB12')
        host, guest = NetLink('host', peer=Peer(host_sock)), NetLink('guest', peer=Peer(guest_sock))
        self.addCleanup(host.close)
        self.addCleanup(guest.close)
        host_table, guest_table = table(), table()
        shake(host, guest, host_table, guest_table)
        self.assertTrue(host.peer_ready)
        self.assertTrue(guest.peer_ready)
        unknown = socket.create_connection(('127.0.0.1', port), timeout=2)
        self.addCleanup(unknown.close)
        from arcade.protocol import dumps, loads
        unknown.sendall(dumps({'t': 'relay', 'op': 'join', 'code': 'NOPE'}))
        deadline = time.time() + 2
        buf = bytearray()
        unknown.settimeout(0.5)
        while time.time() < deadline and b'\n' not in buf:
            buf += unknown.recv(256)
        self.assertIn('房间不存在', loads(bytes(buf).split(b'\n', 1)[0])['reason'])


if __name__ == '__main__':
    unittest.main()
