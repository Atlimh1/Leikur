"""Turn-based game server.

One process holds the authoritative GameState. Each connected client gets a
thread that reads its messages; a shared lock guards the game state so two
moves can't be applied at once. After any change, the server broadcasts a
fresh snapshot to everyone -- clients never compute game logic themselves,
they just render what the server tells them. This "authoritative server"
model is what keeps multiplayer games consistent and cheat-resistant.

Run:  python3 server.py [host] [port]
"""

import socket
import sys
import threading
import uuid

from game import protocol
from game.state import GameState

HOST_DEFAULT = "0.0.0.0"
PORT_DEFAULT = 5555


class Client:
    """Server-side handle for one connected player."""

    def __init__(self, conn: socket.socket, addr):
        self.conn = conn
        self.addr = addr
        self.player_id = uuid.uuid4().hex[:8]
        self.stream = protocol.MessageStream()

    def send(self, message: dict):
        try:
            self.conn.sendall(protocol.encode(message))
        except OSError:
            pass  # client went away; the reader thread will clean it up


class GameServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.state = GameState()
        self.clients: dict[str, Client] = {}   # player_id -> Client
        self.lock = threading.Lock()           # guards state + clients

    # --- broadcasting ---

    def broadcast_state(self):
        snapshot = {"type": protocol.STATE, **self.state.snapshot()}
        for client in list(self.clients.values()):
            client.send(snapshot)

    # --- per-client handling ---

    def handle_client(self, client: Client):
        with self.lock:
            self.clients[client.player_id] = client
            symbol = self.state.add_player(client.player_id)
            client.send({
                "type": protocol.WELCOME,
                "player_id": client.player_id,
                "symbol": symbol,
            })
            self.broadcast_state()
        print(f"[+] {client.addr} joined as {client.player_id} ({symbol})")

        try:
            while True:
                data = client.conn.recv(4096)
                if not data:
                    break  # clean disconnect
                for message in client.stream.feed(data):
                    self.handle_message(client, message)
        except (OSError, ValueError) as e:
            print(f"[!] {client.player_id} error: {e}")
        finally:
            self.disconnect(client)

    def handle_message(self, client: Client, message: dict):
        mtype = message.get("type")

        if mtype == protocol.MOVE:
            with self.lock:
                try:
                    self.state.apply_move(
                        client.player_id, int(message["x"]), int(message["y"])
                    )
                except (ValueError, KeyError, TypeError) as e:
                    client.send({"type": protocol.ERROR, "message": str(e)})
                    return
                self.broadcast_state()
        else:
            client.send({
                "type": protocol.ERROR,
                "message": f"unknown message type: {mtype!r}",
            })

    def disconnect(self, client: Client):
        with self.lock:
            self.clients.pop(client.player_id, None)
        try:
            client.conn.close()
        except OSError:
            pass
        print(f"[-] {client.player_id} disconnected")

    # --- main loop ---

    def serve_forever(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((self.host, self.port))
            srv.listen()
            print(f"Listening on {self.host}:{self.port} -- waiting for players...")
            while True:
                conn, addr = srv.accept()
                client = Client(conn, addr)
                threading.Thread(
                    target=self.handle_client, args=(client,), daemon=True
                ).start()


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else HOST_DEFAULT
    port = int(sys.argv[2]) if len(sys.argv) > 2 else PORT_DEFAULT
    try:
        GameServer(host, port).serve_forever()
    except KeyboardInterrupt:
        print("\nServer shutting down.")


if __name__ == "__main__":
    main()
