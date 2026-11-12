"""awesome-pet: start, stop and steer the desktop character from any shell or agent."""
import argparse
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

from . import PORT
from .paths import home, log_file

INSTALL_HINT = (
    '这个 Python 里没有 PySide6。用下面任一方式装好再运行：\n'
    '  uv tool install "awesome-desktop @ git+https://github.com/EnkiHQ/awesome-desktop"\n'
    '  python -m pip install "awesome-desktop @ git+https://github.com/EnkiHQ/awesome-desktop"'
)


def send(text, timeout=1.0, port=PORT):
    with socket.create_connection(('127.0.0.1', port), timeout) as sock:
        sock.sendall((text + '\n').encode('utf-8'))
        sock.settimeout(timeout)
        try:
            return sock.recv(64).decode('utf-8', 'ignore').strip()
        except socket.timeout:
            return ''


def running():
    try:
        send('ping', 0.5)
    except OSError:
        return False
    return True


def _spawn(extra):
    env = dict(os.environ)
    package_root = str(Path(__file__).resolve().parents[1])
    env['PYTHONPATH'] = package_root + (os.pathsep + env['PYTHONPATH'] if env.get('PYTHONPATH') else '')
    python = sys.executable
    if os.name == 'nt':
        windowed = Path(python).with_name('pythonw.exe')
        if windowed.exists():
            python = str(windowed)
    log = open(log_file(), 'ab')
    command = [python, '-m', 'pet', 'run', *extra]
    options = dict(stdin=subprocess.DEVNULL, stdout=log, stderr=log, cwd=str(home()), env=env, close_fds=True)
    if os.name == 'nt':
        flags = 0x00000008 | 0x00000200
        try:
            subprocess.Popen(command, creationflags=flags | 0x01000000, **options)
        except OSError:
            subprocess.Popen(command, creationflags=flags, **options)
    else:
        subprocess.Popen(command, start_new_session=True, **options)


def _tail(path, lines=12):
    try:
        return '\n'.join(path.read_text(encoding='utf-8', errors='ignore').splitlines()[-lines:])
    except OSError:
        return ''


def cmd_start(args):
    extra = []
    if args.pet:
        extra += ['--pet', args.pet]
    if args.facing:
        extra += ['--facing', args.facing]
    if args.zoom:
        extra += ['--zoom', str(args.zoom)]
    if running():
        if args.pet:
            send(f'pet {args.pet}')
        if args.facing:
            send(args.facing)
        if args.zoom:
            send(f'zoom {args.zoom}')
        print('小人已经在屏幕上。')
        return 0
    try:
        import PySide6  # noqa: F401
    except ImportError:
        print(INSTALL_HINT, file=sys.stderr)
        return 3
    if args.foreground:
        from .app import main as run_app
        return run_app(extra)
    _spawn(extra)
    deadline = time.time() + 20
    while time.time() < deadline:
        if running():
            print('小人已经出现在屏幕右下角。它和终端分开运行，关掉终端或助手也不会消失。')
            print('关掉它：awesome-pet stop')
            return 0
        time.sleep(0.3)
    print(f'小人没有起来，日志 {log_file()}：\n{_tail(log_file())}', file=sys.stderr)
    return 1


def cmd_stop(args):
    if not running():
        print('小人没有在运行。')
        return 0
    send('quit')
    for _ in range(30):
        if not running():
            print('已关掉。')
            return 0
        time.sleep(0.2)
    print('关闭命令已发出，但它还在。', file=sys.stderr)
    return 1


def cmd_status(args):
    print('运行中' if running() else '没有运行')
    return 0


def cmd_act(args):
    text = ' '.join(args.words) or 'type'
    try:
        send(text)
    except OSError:
        print('小人还没开。先运行：awesome-pet start', file=sys.stderr)
        return 1
    return 0


def cmd_preview(args):
    from .preview import preview

    out = preview(args.pet or 'default', Path(args.out).expanduser())
    print(out)
    return 0


def cmd_pack(args):
    from . import pack

    if args.action == 'list':
        for name, title in pack.available().items():
            print(f'{name}\t{title}')
        return 0
    if args.action == 'make':
        if not args.name or not args.front:
            print('用法：awesome-pet pack make 名字 --front 正面.png [--back 背面.png] [--title 显示名]', file=sys.stderr)
            return 2
        root = pack.make(args.name, args.front, args.back, args.title)
        print(root)
        return 0
    if args.action == 'add':
        print(pack.add(args.name))
        return 0
    if args.action == 'export':
        print(pack.export(args.name, args.out or f'{args.name}.zip'))
        return 0
    return 2


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ['run']:
        from .app import main as run_app
        return run_app(argv[1:])
    parser = argparse.ArgumentParser(prog='awesome-pet', description='桌面小人：你按键盘它按键盘，你按鼠标它按鼠标。')
    sub = parser.add_subparsers(dest='command')

    start = sub.add_parser('start', help='在桌面上放出小人（后台运行）')
    start.add_argument('--pet', help='形象名，或形象文件夹路径')
    start.add_argument('--facing', choices=('front', 'back'), help='front 面朝你，back 背朝你')
    start.add_argument('--zoom', type=float, help='大小，1 是默认')
    start.add_argument('--foreground', action='store_true', help='在当前终端里运行，调试用')
    start.set_defaults(func=cmd_start)

    sub.add_parser('stop', help='关掉小人').set_defaults(func=cmd_stop)
    sub.add_parser('status', help='看小人在不在').set_defaults(func=cmd_status)

    act = sub.add_parser('act', help='让小人动：type / click / front / back / flip / bigger / smaller / zoom 1.2 / pet 名字')
    act.add_argument('words', nargs='*')
    act.set_defaults(func=cmd_act)

    prev = sub.add_parser('preview', help='把各个姿势画成一张图，检查形象用')
    prev.add_argument('--pet')
    prev.add_argument('--out', default='pet-preview.png')
    prev.set_defaults(func=cmd_preview)

    pk = sub.add_parser('pack', help='形象：list / make / add / export')
    pk.add_argument('action', choices=('list', 'make', 'add', 'export'))
    pk.add_argument('name', nargs='?')
    pk.add_argument('--front')
    pk.add_argument('--back')
    pk.add_argument('--title')
    pk.add_argument('--out')
    pk.set_defaults(func=cmd_pack)

    args = parser.parse_args(argv)
    if not getattr(args, 'func', None):
        if argv and argv[0] in ('type', 'click', 'idle', 'front', 'back'):
            return cmd_act(argparse.Namespace(words=argv))
        parser.print_help()
        return 0
    return args.func(args) or 0


if __name__ == '__main__':
    raise SystemExit(main())
