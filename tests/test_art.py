"""Drawing tests for the table, the balls, the particles and the cue."""
import math
import unittest

from PIL import Image, ImageFont, ImageStat

from dib.art import charge_art, cue_art, pocket_particles, table_art, white_art
from dib.table import BilliardsMotion


class TableArtTests(unittest.TestCase):
    def test_frame_covers_the_work_area_with_transparent_felt_and_dark_pockets(self):
        work = (-1920, -120, 0, 960)
        game = BilliardsMotion(work, [(64, 64)] * 2)
        frame, origin_x, origin_y = table_art(game)
        self.assertEqual(frame.mode, 'RGBA')
        self.assertEqual(frame.size, (work[2] - work[0], work[3] - work[1]))
        left, top, right, bottom = game.bounds
        center = ((left + right) // 2 - origin_x, (top + bottom) // 2 - origin_y)
        self.assertEqual(frame.getpixel(center)[3], 0)
        # The desktop area around the rails keeps a faint tint so the table reads.
        self.assertGreater(frame.getpixel((1, 1))[3], 0)
        for px, py in game.pockets:
            self.assertGreater(frame.getpixel((px - origin_x, py - origin_y))[3], 200)

    def test_frame_origin_is_the_work_area_origin(self):
        game = BilliardsMotion((100, 50, 1700, 1050), [(64, 64)] * 2)
        frame, origin_x, origin_y = table_art(game)
        self.assertEqual((origin_x, origin_y), (100, 50))
        self.assertEqual(frame.size, (1600, 1000))

    def test_wallpaper_blurs_inside_the_table_only(self):
        game = BilliardsMotion((0, 0, 640, 480), [(32, 32)])
        wallpaper = Image.new('RGB', (640, 480), 'black')
        wallpaper.paste('white', (320, 0, 640, 480))
        frame, _, _ = table_art(game, wallpaper)
        edge = frame.getpixel((319, 240))
        self.assertEqual(edge[3], 255)
        self.assertGreater(edge[0], 60)
        self.assertLess(edge[0], 195)
        self.assertLess(frame.getpixel((1, 1))[3], 255)


class ChargeArtTests(unittest.TestCase):
    def test_bar_fills_from_left_to_right(self):
        font = ImageFont.load_default(size=16)
        empty, half, full = [charge_art(percent, font) for percent in (0, 50, 100)]
        self.assertEqual(empty.size, full.size)
        for x, half_is_filled in ((60, True), (105, False)):
            point = x, full.height // 2
            expected = full if half_is_filled else empty
            self.assertNotEqual(empty.getpixel(point), full.getpixel(point))
            self.assertEqual(half.getpixel(point), expected.getpixel(point))


class WhiteArtTests(unittest.TestCase):
    def test_shaded_ball_is_round_and_transparent_at_the_corners(self):
        ball = white_art(25, shaded=True)
        self.assertEqual(ball.mode, 'RGBA')
        expected = max(3, math.ceil(25 * 2) + 4)
        self.assertEqual(ball.size, (expected, expected))
        self.assertEqual(ball.getpixel((0, 0))[3], 0)
        self.assertGreater(ball.getpixel((expected // 2, expected // 2))[3], 200)

    def test_unshaded_ball_is_drawn_as_an_opaque_disc(self):
        ball = white_art(12)
        expected = max(3, math.ceil(12 * 2) + 4)
        self.assertEqual(ball.size, (expected, expected))
        self.assertEqual(ball.getpixel((0, 0))[3], 0)
        center = ball.getpixel((expected // 2, expected // 2))
        self.assertEqual(center[3], 255)
        self.assertGreater(center[0], 200)


class ParticleArtTests(unittest.TestCase):
    def test_fading_particles_only_paint_inside_the_frame(self):
        base = Image.new('RGBA', (64, 64))
        halo = pocket_particles(base, 1, .5)
        self.assertEqual(halo.size, base.size)
        self.assertGreater(halo.getchannel('A').getextrema()[1], 0)
        self.assertEqual(base.getchannel('A').getextrema()[1], 0)
        invisible = pocket_particles(base, 0, 0.)
        self.assertEqual(invisible.getchannel('A').getextrema()[1], 0)


class CueArtTests(unittest.TestCase):
    def test_cue_frame_contains_the_tip_and_tail(self):
        cue = ((110., 60.), (10., 55.))
        frame, x, y = cue_art(cue)
        side = math.ceil(math.dist(cue[0], cue[1])) + 18
        self.assertEqual(frame.mode, 'RGBA')
        self.assertEqual(frame.size, (side, side))
        self.assertEqual((x, y), (round((110 + 10 - side) / 2), round((60 + 55 - side) / 2)))
        tip = (round(cue[0][0] - x), round(cue[0][1] - y))
        self.assertEqual(frame.getpixel(tip), (126, 207, 228, 255))
        self.assertEqual(frame.getpixel((0, 0))[3], 0)

    def test_thicker_cue_draws_a_bigger_tip(self):
        cue = ((100., 100.), (20., 100.))
        thin = cue_art(cue, 1)[0]
        thick = cue_art(cue, 2)[0]
        self.assertEqual(thin.size, thick.size)
        thin_alpha = ImageStat.Stat(thin.getchannel('A')).sum[0]
        thick_alpha = ImageStat.Stat(thick.getchannel('A')).sum[0]
        self.assertGreater(thick_alpha, thin_alpha)


if __name__ == '__main__':
    unittest.main()
