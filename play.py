"""Terminal client -- handy for quick testing. With the lobby it auto-matches:
the first instance creates a game, the second joins it. Then play by typing
moves as 'x y'. (The graphical client is gui.py.)

Run:  python3 play.py [host] [port]
"""

import os
import sys
import time

from netclient import NetworkClient

HOST_DEFAULT = "127.0.0.1"
PORT_DEFAULT = 5555


def render(client: NetworkClient):
    os.system("clear")
    print("=== Tölvuleikur (terminal) ===\n")

    if client.mode == "menu":
        games = client.get_lobby() or []
        print(f"You: {client.name}")
        print("In the lobby. Auto-matching…")
        print(f"Open games: {len(games)}")
        return

    snap = client.get_snapshot()
    if not snap:
        print("Loading…")
        return

    size, board, names = snap["size"], snap["board"], snap["names"]
    print("    " + " ".join(str(x) for x in range(size)))
    print("   +" + "-" * (size * 2))
    for y in range(size):
        cells = []
        for x in range(size):
            owner = board[y][x]
            if owner is None:
                cells.append(".")
            else:
                cells.append("X" if snap["players"].index(owner) == 0 else "O")
        print(f" {y} | " + " ".join(cells))

    print()
    status = snap["status"]
    if status == "waiting":
        print("Waiting for opponent to join…")
    elif status == "playing":
        if snap["current_player"] == client.player_id:
            print(">>> YOUR TURN. Enter 'x y' (e.g. '2 3'): ", end="", flush=True)
        else:
            print(f"{names.get(snap['current_player'], 'Opponent')}'s turn…")
    elif status == "finished":
        w = snap["winner"]
        if w == "draw":
            print("Game over: DRAW.")
        elif w == client.player_id:
            print("Game over: YOU WIN!")
        else:
            print(f"Game over: {names.get(w, 'Opponent')} wins.")

    if client.last_error:
        print(f"\n[server: {client.last_error}]")


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else HOST_DEFAULT
    port = int(sys.argv[2]) if len(sys.argv) > 2 else PORT_DEFAULT

    client = NetworkClient(host, port)
    matched = {"done": False}

    def on_update(_msg):
        # Auto-match once: join an open game if there is one, else create.
        if client.mode == "menu" and not matched["done"]:
            games = client.get_lobby() or []
            if games:
                client.join_game(games[0]["id"])
            else:
                client.create_game()
            matched["done"] = True
        render(client)

    client.on_update = on_update
    try:
        client.connect()
    except OSError as e:
        print(f"Could not connect to {host}:{port} -- is the server running? ({e})")
        return

    time.sleep(0.2)
    render(client)

    while client.connected:
        try:
            line = input()
        except (EOFError, KeyboardInterrupt):
            break
        parts = line.split()
        if len(parts) == 2 and all(p.lstrip("-").isdigit() for p in parts):
            client.last_error = None
            client.send_move(int(parts[0]), int(parts[1]))
        else:
            print("Enter a move as two numbers: 'x y'.")

    client.close()
    print("\nDisconnected. Bye!")


if __name__ == "__main__":
    main()
