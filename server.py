"""Turn-based game server with a lobby.

The server hosts many independent game rooms at once. A freshly connected
client lands in the *lobby* (the main menu): it can create a new game and
wait, or join a game someone else created. When a room has two players it
starts. Every room keeps its own authoritative GameState; clients only ever
render what the server sends them.

Concurrency: one reader thread per client, one lock guarding all shared
state (clients + games), and the server broadcasts after every change.

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
        self.name = f"Player-{self.player_id[:4]}"
        self.game_id = None          # which room they're in, or None = lobby
        self.stream = protocol.MessageStream()

    def send(self, message: dict):
        try:
            self.conn.sendall(protocol.encode(message))
        except OSError:
            pass  # gone; the reader thread will clean up


class Game:
    """One game room: a GameState plus the display names of its players."""

    def __init__(self, game_id: int, host: Client):
        self.id = game_id
        self.host_name = host.name
        self.state = GameState()
        self.names = {}              # player_id -> display name

    def add(self, client: Client) -> str:
        symbol = self.state.add_player(client.player_id)
        self.names[client.player_id] = client.name
        return symbol

    @property
    def is_joinable(self) -> bool:
        return self.state.status == "waiting" and len(self.state.players) < 2


class GameServer:
    def __init__(self, host: str, port: int):
        self.host = host
        self.port = port
        self.clients: dict[str, Client] = {}
        self.games: dict[int, Game] = {}
        self._next_game_id = 1
        self.lock = threading.Lock()

    # --- snapshots / broadcasting (all called with self.lock held) ---

    def lobby_message(self) -> dict:
        games = [
            {"id": g.id, "host_name": g.host_name,
             "players": len(g.state.players)}
            for g in self.games.values() if g.is_joinable
        ]
        return {"type": protocol.LOBBY, "games": games}

    def broadcast_lobby(self):
        """Send the open-games list to everyone currently in the menu."""
        for client in self.clients.values():
            if client.game_id is None:
                msg = self.lobby_message()
                msg["your_name"] = client.name
                client.send(msg)

    def game_message(self, game: Game) -> dict:
        return {
            "type": protocol.STATE,
            "game_id": game.id,
            "names": game.names,
            **game.state.snapshot(),
        }

    def broadcast_game(self, game: Game):
        msg = self.game_message(game)
        for client in self.clients.values():
            if client.game_id == game.id:
                client.send(msg)

    # --- room lifecycle (called with self.lock held) ---

    def create_game(self, client: Client):
        if client.game_id is not None:
            return
        game = Game(self._next_game_id, client)
        self._next_game_id += 1
        self.games[game.id] = game
        game.add(client)
        client.game_id = game.id
        self.broadcast_game(game)     # creator -> game view (waiting)
        self.broadcast_lobby()        # others see the new open game
        print(f"[room {game.id}] created by {client.name}")

    def join_game(self, client: Client, game_id: int):
        game = self.games.get(game_id)
        if client.game_id is not None:
            return
        if game is None or not game.is_joinable:
            client.send({"type": protocol.ERROR,
                         "message": "that game is no longer available"})
            self.broadcast_lobby()
            return
        game.add(client)
        client.game_id = game.id
        self.broadcast_game(game)     # both players -> game view (now playing)
        self.broadcast_lobby()        # game is full, drops off the open list
        print(f"[room {game.id}] {client.name} joined")

    def leave_game(self, client: Client, reason_for_others: str | None = None):
        """Remove `client` from its room; return any remaining player to the
        lobby and destroy the room (a 2-player game can't continue 1-handed)."""
        gid = client.game_id
        client.game_id = None
        game = self.games.pop(gid, None) if gid is not None else None
        if game is not None:
            for other in self.clients.values():
                if other.game_id == gid:
                    other.game_id = None
                    if reason_for_others:
                        other.send({"type": protocol.ERROR,
                                    "message": reason_for_others})
            print(f"[room {gid}] closed")
        self.broadcast_lobby()

    # --- per-client handling ---

    def handle_client(self, client: Client):
        with self.lock:
            self.clients[client.player_id] = client
            client.send({"type": protocol.WELCOME,
                         "player_id": client.player_id, "name": client.name})
            msg = self.lobby_message()
            msg["your_name"] = client.name
            client.send(msg)
        print(f"[+] {client.addr} connected as {client.name}")

        try:
            while True:
                data = client.conn.recv(4096)
                if not data:
                    break
                for message in client.stream.feed(data):
                    self.handle_message(client, message)
        except (OSError, ValueError) as e:
            print(f"[!] {client.name} error: {e}")
        finally:
            self.disconnect(client)

    def handle_message(self, client: Client, message: dict):
        mtype = message.get("type")
        with self.lock:
            if mtype == protocol.SET_NAME:
                name = str(message.get("name", "")).strip()[:16]
                if name:
                    client.name = name
                    # if they're hosting an open game, refresh its title
                    game = self.games.get(client.game_id)
                    if game is not None:
                        game.host_name = game.names.get(client.player_id, name)
                        if client.player_id in game.names:
                            game.names[client.player_id] = name
                    self.broadcast_lobby()

            elif mtype == protocol.CREATE_GAME:
                self.create_game(client)

            elif mtype == protocol.JOIN_GAME:
                try:
                    self.join_game(client, int(message["game_id"]))
                except (KeyError, ValueError, TypeError):
                    client.send({"type": protocol.ERROR,
                                 "message": "bad game id"})

            elif mtype == protocol.LEAVE_GAME:
                self.leave_game(client, reason_for_others="opponent left the game")

            elif mtype == protocol.MOVE:
                game = self.games.get(client.game_id)
                if game is None:
                    return
                try:
                    game.state.apply_move(
                        client.player_id, int(message["x"]), int(message["y"]))
                except (ValueError, KeyError, TypeError) as e:
                    client.send({"type": protocol.ERROR, "message": str(e)})
                    return
                self.broadcast_game(game)

            else:
                client.send({"type": protocol.ERROR,
                             "message": f"unknown message type: {mtype!r}"})

    def disconnect(self, client: Client):
        with self.lock:
            self.clients.pop(client.player_id, None)
            self.leave_game(client, reason_for_others="opponent left the game")
        try:
            client.conn.close()
        except OSError:
            pass
        print(f"[-] {client.name} disconnected")

    # --- main loop ---

    def serve_forever(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as srv:
            srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            srv.bind((self.host, self.port))
            srv.listen()
            print(f"Listening on {self.host}:{self.port} -- lobby open.")
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
