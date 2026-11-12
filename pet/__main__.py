"""Start the desktop person, or poke a person that is already on screen.

    python3 -m pet
    python3 -m pet act type
    python3 -m pet act click
"""
import socket
import subprocess
import sys
from pathlib import Path

from pet import ACTIONS, PORT

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'pet' / 'MirrorPet.swift'
BINARY = ROOT / 'pet' / 'bin' / 'MirrorPet'


def send(action, port=PORT, timeout=1):
    if action not in ACTIONS:
        raise ValueError(f'动作只能是 {"、".join(ACTIONS)}')
    with socket.create_connection(('127.0.0.1', port), timeout) as sock:
        sock.sendall((action + '\n').encode())


def running(port=PORT):
    try:
        send('idle', port, timeout=0.3)
    except OSError:
        return False
    return True


def compile_binary():
    BINARY.parent.mkdir(parents=True, exist_ok=True)
    if BINARY.exists() and BINARY.stat().st_mtime >= SOURCE.stat().st_mtime:
        return BINARY
    subprocess.run(
        ['swiftc', '-O', '-framework', 'AppKit', '-framework', 'Network', '-o', str(BINARY), str(SOURCE)],
        check=True,
    )
    return BINARY


def main(argv):
    if len(argv) >= 2 and argv[1] == 'act':
        action = argv[2] if len(argv) > 2 else 'type'
        try:
            send(action)
        except OSError:
            print('小人还没开。先运行 python3 -m pet', file=sys.stderr)
            return 1
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 2
        return 0
    if running():
        print(f'小人已经在屏幕上。另开一条命令：python3 -m pet act type')
        return 0
    binary = compile_binary()
    raise SystemExit(subprocess.call([str(binary), str(ROOT)]))


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
