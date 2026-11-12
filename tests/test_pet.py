"""Desktop character logic that runs without opening a window."""
import socket
import threading
import unittest
from types import SimpleNamespace

from pet import keys
from pet.cli import send
from pet.pack import View, guess
from pet.scene import Scene


def fake_pack():
    view = View(image=None, size=(400, 600), shoulders=[(160, 300), (240, 300)], arm=20.0, line=4.0, desk=360.0)
    back = View(image=None, size=(400, 600), shoulders=[(160, 300), (240, 300)], arm=20.0, line=4.0)
    return SimpleNamespace(views={'front': view, 'back': back}, skin='#F4C7AE', outline='#151515')


class KeyTests(unittest.TestCase):
    def test_letters_map_to_the_side_of_the_keyboard_they_sit_on(self):
        row, frac = keys.position('a')
        self.assertEqual(row, 2)
        self.assertTrue(keys.left_hand(row, frac))
        row, frac = keys.position('p')
        self.assertEqual(row, 1)
        self.assertFalse(keys.left_hand(row, frac))
        self.assertEqual(keys.position('space')[0], 4)
        self.assertEqual(keys.position('A'), keys.position('a'))
        self.assertEqual(keys.position('!'), keys.position('1'))

    def test_platform_codes(self):
        self.assertEqual(keys.mac_label(0), 'a')
        self.assertEqual(keys.mac_label(111), 'f12')
        self.assertEqual(keys.win_label(0x41), 'a')
        self.assertEqual(keys.win_label(0x20), 'space')


class SceneTests(unittest.TestCase):
    def test_left_keys_use_the_left_hand_and_right_keys_the_right_hand(self):
        scene = Scene(fake_pack(), seed=1)
        scene.key('a', True, 0.0)
        self.assertAlmostEqual(scene.left.tu, keys.position('a')[1])
        self.assertEqual(scene.left.press_target, 1.0)
        scene.key('p', True, 0.0)
        self.assertAlmostEqual(scene.right.tu, keys.position('p')[1])
        self.assertEqual(scene.right.tm, 0.0)
        self.assertTrue(scene.key_lit((2, 1)))

    def test_hand_lifts_after_release_and_mouse_hand_follows_the_mouse(self):
        scene = Scene(fake_pack(), seed=1)
        scene.key('d', True, 0.0)
        scene.key('d', False, 0.02)
        t = 0.0
        for _ in range(60):
            t += 1 / 60
            scene.step(t, 1 / 60)
        self.assertLess(scene.left.press, 0.05)
        scene.cursor_at(0.5, 0.5, t)
        scene.cursor_at(0.8, 0.6, t)
        self.assertEqual(scene.right.tm, 1.0)
        scene.button(True, t)
        self.assertTrue(scene.mouse_down)

    def test_f12_turns_the_character_around(self):
        scene = Scene(fake_pack(), seed=1)
        scene.key('f12', True, 0.0)
        self.assertEqual(scene.facing, 'back')
        frame, squash = scene.view()
        self.assertEqual(frame.facing, 'front')
        self.assertAlmostEqual(squash, 1.0)


class GuessTests(unittest.TestCase):
    def test_shoulders_sit_at_the_top_corners_of_the_body_under_the_head(self):
        from PIL import Image, ImageDraw

        image = Image.new('RGBA', (300, 420), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.ellipse((40, 10, 260, 230), fill=(240, 200, 170, 255), outline=(10, 10, 10, 255), width=6)
        draw.rectangle((115, 228, 185, 400), fill=(120, 170, 230, 255), outline=(10, 10, 10, 255), width=6)
        spec = guess(image)
        (lx, ly), (rx, ry) = spec['shoulders']
        self.assertTrue(225 <= ly <= 260, ly)
        self.assertAlmostEqual(lx, 115, delta=6)
        self.assertAlmostEqual(rx, 185, delta=6)
        self.assertAlmostEqual(spec['line'], 6, delta=2)


class CommandTests(unittest.TestCase):
    def test_send_writes_one_line(self):
        received = []
        server = socket.socket()
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        self.addCleanup(server.close)

        def serve():
            conn, _ = server.accept()
            received.append(conn.recv(64))
            conn.sendall(b'ok\n')
            conn.close()

        thread = threading.Thread(target=serve)
        thread.start()
        self.assertEqual(send('type a', port=server.getsockname()[1]), 'ok')
        thread.join(2)
        self.assertEqual(received, [b'type a\n'])


if __name__ == '__main__':
    unittest.main()
