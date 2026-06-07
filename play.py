"""Terminal client -- lets us play and verify the multiplayer right now,
before any graphics exist. Run two of these against one server to test.

Run:  python3 play.py [host] [port]
"""

import os
import sys
import threading
import time

from netclient import NetworkClient

HOST_DEFAULT = "127.0.0.1"
PORT_DEFAULT = 5555


def render(client: NetworkClient):
    snap = client.get_snapshot()
    os.system("clear")
    print("=== Tölvuleikur: claim-the-grid (turn-based multiplayer demo) ===\n")

    if client.player_id:
        print(f"You are: {client.symbol}   (id {client.player_id})")
    if snap is None:
        print("\nConnecting / waiting for game state...")
        return

    size = snap["size"]
    board = snap["board"]
    symbols = snap["symbols"]

    # Column headers
    print("\n    " + " ".join(str(x) for x in range(size)))
    print("   +" + "-" * (size * 2))
    for y in range(size):
        cells = []
        for x in range(size):
            owner = board[y][x]
            cells.append(symbols.get(owner, ".") if owner else ".")
        print(f" {y} | " + " ".join(cells))

    status = snap["status"]
    print()
    if status == "waiting":
        print("Waiting for a second player to join...")
    elif status == "playing":
        if snap["current_player"] == client.player_id:
            print(">>> YOUR TURN. Enter a move as 'x y' (e.g. '2 3'): ", end="", flush=True)
        else:
            print("Opponent's turn. Waiting...")
    elif status == "finished":
        winner = snap["winner"]
        if winner == "draw":
            print("Game over: it's a DRAW.")
        elif winner == client.player_id:
            print("Game over: YOU WIN! 🎉")
        else:
            print(f"Game over: {symbols.get(winner, '?')} wins.")

    if client.last_error:
        print(f"\n[server says: {client.last_error}]")


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else HOST_DEFAULT
    port = int(sys.argv[2]) if len(sys.argv) > 2 else PORT_DEFAULT

    client = NetworkClient(host, port)
    # Re-render whenever the server pushes an update.
    client.on_update = lambda _snap: render(client)

    try:
        client.connect()
    except OSError as e:
        print(f"Could not connect to {host}:{port} -- is the server running? ({e})")
        return

    time.sleep(0.2)
    render(client)

    # Input loop: read moves from the terminal and send them.
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
            print("Enter a move as two numbers: 'x y'. Try again.")

    client.close()
    print("\nDisconnected. Bye!")


if __name__ == "__main__":
    main()
