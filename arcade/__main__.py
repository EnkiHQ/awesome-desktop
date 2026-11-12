"""``python -m arcade`` prints the games. ``python -m arcade relay [端口]`` runs the room relay."""
import sys

from . import SUITE_NAME, SUITE_NAME_EN, __version__
from .games import GAMES


def main(argv):
    if len(argv) >= 2 and argv[1] == 'relay':
        from .peer import serve_relay

        port = int(argv[2]) if len(argv) > 2 else 8770
        serve_relay(port)
        print(f'{SUITE_NAME}中继已在 {port} 端口等待房间', flush=True)
        try:
            threading_wait()
        except KeyboardInterrupt:
            return 0
    print(f'{SUITE_NAME} {SUITE_NAME_EN} {__version__}')
    for game in GAMES:
        state = '可玩' if game.playable else '以后做'
        print(f'- {game.name}（{state}）{game.summary}')
    print('联机说明见 游乐场.md')
    return 0


def threading_wait():
    import threading
    threading.Event().wait()


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
