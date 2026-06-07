# Tölvuleikur — turn-based multiplayer game

A native desktop, turn-based multiplayer game in Python. We're building the
**networking foundation first**; graphics (pygame) come next.

## The demo game

"Claim the grid": a 5×5 board, two players take turns claiming one empty cell
each. When the board fills up, whoever owns the most cells wins. It's small,
but it exercises every part of multiplayer: turn order, move validation,
shared state, and an end condition.

## Architecture

The golden rule: **the server is authoritative.** Clients never run game
logic — they send moves and render whatever snapshot the server broadcasts.
That's what keeps a multiplayer game consistent and cheat-resistant.

```
game/protocol.py   shared wire format — newline-delimited JSON over TCP
game/state.py      pure game logic (no networking, fully unit-testable)
server.py          TCP server: one thread per client, authoritative state
netclient.py       client network layer — UI-agnostic (no terminal/pygame code)
play.py            terminal client to play & test right now
```

`netclient.py` is deliberately UI-free, so the future pygame client will reuse
the exact same network layer as the terminal client.

## How to run

Open three terminals.

**1. Start the server:**
```bash
python3 server.py
```

**2. Player one:**
```bash
python3 play.py
```

**3. Player two:**
```bash
python3 play.py
```

The game starts automatically once the second player connects. On your turn,
type a move as two numbers — e.g. `2 3` — and press Enter.

Playing across machines on the same network? Pass the server's IP:
`python3 play.py 192.168.1.50 5555`.

## Next steps

- [ ] Swap the terminal frontend for a pygame window (reusing `netclient.py`)
- [ ] Lobby / rematch flow
- [ ] Reconnect handling and player-disconnect mid-game
