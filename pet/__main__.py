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
APP = ROOT / 'pet' / 'bin' / 'MirrorPet.app'
BINARY = APP / 'Contents' / 'MacOS' / 'MirrorPet'
PLIST = '''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>MirrorPet</string>
<key>CFBundleIdentifier</key><string>com.enkihq.awesome-desktop.pet</string>
<key>CFBundleName</key><string>MirrorPet</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>LSUIElement</key><true/>
</dict></plist>
'''


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
    (APP / 'Contents').joinpath('Info.plist').write_text(PLIST, encoding='utf-8')
    if not BINARY.exists() or BINARY.stat().st_mtime < SOURCE.stat().st_mtime:
        subprocess.run(
            ['swiftc', '-O', '-framework', 'AppKit', '-framework', 'ApplicationServices', '-framework', 'Network', '-o', str(BINARY), str(SOURCE)],
            check=True,
        )
    return APP


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
    app = compile_binary()
    raise SystemExit(subprocess.call(['open', str(app), '--args', str(ROOT)]))


if __name__ == '__main__':
    raise SystemExit(main(sys.argv))
