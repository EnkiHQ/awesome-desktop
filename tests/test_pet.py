"""The command that pokes the desktop person. No window required."""
import socket
import threading
import unittest

from pet import ACTIONS
from pet.__main__ import send


class CommandTests(unittest.TestCase):
    def test_known_actions_and_reject_unknown(self):
        self.assertEqual(ACTIONS, ('type', 'click', 'idle'))
        received = []

        def serve(sock):
            conn, _ = sock.accept()
            received.append(conn.recv(32))
            conn.close()

        server = socket.socket()
        server.bind(('127.0.0.1', 0))
        server.listen(1)
        port = server.getsockname()[1]
        thread = threading.Thread(target=serve, args=(server,))
        thread.start()
        self.addCleanup(server.close)
        send('type', port)
        thread.join(2)
        self.assertEqual(received, [b'type\n'])
        with self.assertRaises(ValueError):
            send('dance', port)


if __name__ == '__main__':
    unittest.main()
