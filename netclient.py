"""Client-side network layer. UI-agnostic on purpose.

A background thread owns the socket and keeps a copy of the latest game
snapshot the server sent. The UI (terminal now, pygame later) just reads
`client.snapshot` to draw, and calls `client.send_move()` to act. Nothing
here imports pygame or print()s -- so the very same class backs both the
terminal test client and the future graphical client.
"""

import socket
import threading

from game import protocol


class NetworkClient:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.stream = protocol.MessageStream()

        # Shared state, guarded by a lock since the net thread writes it
        # while the UI thread reads it.
        self._lock = threading.Lock()
        self.player_id = None
        self.symbol = None
        self.snapshot = None       # latest STATE message, or None
        self.last_error = None
        self.connected = False
        self.connect_error = None  # set if the initial connect() failed

        # Optional callback fired whenever a new snapshot arrives, so a UI
        # can react instead of polling. Signature: callback(snapshot_dict).
        self.on_update = None

    def connect(self, timeout: float = 6.0):
        """Open the socket. Raises OSError if the server can't be reached
        (refused, unreachable, or no answer within `timeout` seconds)."""
        try:
            self.sock.settimeout(timeout)
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(None)   # back to blocking for recv
        except OSError as e:
            self.connect_error = str(e)
            raise
        self.connected = True
        threading.Thread(target=self._recv_loop, daemon=True).start()

    def _recv_loop(self):
        try:
            while True:
                data = self.sock.recv(4096)
                if not data:
                    break
                for message in self.stream.feed(data):
                    self._handle(message)
        except OSError:
            pass
        finally:
            self.connected = False
            if self.on_update:
                self.on_update(None)  # signal disconnect

    def _handle(self, message: dict):
        mtype = message.get("type")
        with self._lock:
            if mtype == protocol.WELCOME:
                self.player_id = message["player_id"]
                self.symbol = message["symbol"]
            elif mtype == protocol.STATE:
                self.snapshot = message
            elif mtype == protocol.ERROR:
                self.last_error = message.get("message")
        if self.on_update and mtype == protocol.STATE:
            self.on_update(message)

    # --- actions the UI calls ---

    def send_move(self, x: int, y: int):
        try:
            self.sock.sendall(protocol.encode({"type": protocol.MOVE, "x": x, "y": y}))
        except OSError:
            self.connected = False

    def get_snapshot(self):
        with self._lock:
            return self.snapshot

    def close(self):
        try:
            self.sock.close()
        except OSError:
            pass
