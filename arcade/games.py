"""The catalogue of desktop-icon games.

A playable entry is wired to the current Windows table. A planned entry is a
slot for a later game that reuses the same online match, not a pretend implementation.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class GameType:
    """One way to play with the desktop icons."""

    id: str
    name: str
    status: str
    summary: str

    @property
    def playable(self):
        return self.status == 'playable'


GAMES = (
    GameType(
        'billiards',
        '台球',
        'playable',
        '图标摆成球阵。鼠标瞄准，按住左键蓄力，松手击球，进袋消失。联机时两人轮流击球。',
    ),
    GameType(
        'breakout',
        '弹砖',
        'planned',
        '底部一根横杆左右移动，把球弹上去，碰到的图标消失。还没做。',
    ),
    GameType(
        'mirror',
        '小人',
        'playable',
        '你按键盘它按键盘，你按鼠标它按鼠标。千问只要能在这台电脑执行命令，也能让它动。',
    ),
)


def by_id(game_id):
    for game in GAMES:
        if game.id == game_id:
            return game
    raise KeyError(game_id)
