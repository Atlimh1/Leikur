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
gui.py             graphical client (pygame) — clickable grid, colors, scores
play.py            terminal client (handy for quick testing)
```

`netclient.py` is deliberately UI-free, so **both** clients — terminal and
pygame — reuse the exact same network layer.

## Setup

```bash
pip install -r requirements.txt   # installs pygame-ce
```

## How to run

Open two (or three) terminals.

**1. Start the server** (one player hosts):
```bash
python3 server.py
```

**2. Each player joins with the graphical client:**
```bash
python3 gui.py                 # local test (defaults to 127.0.0.1)
python3 gui.py 100.x.y.z 5555  # connect to the host's IP
```

A window opens with a 5×5 grid. On your turn, **click an empty cell** to claim
it. Colors and the turn banner show whose move it is; the footer shows scores.

Prefer the terminal? `python3 play.py [host] [port]` still works.

### Playing across the internet

A home PC isn't reachable from the internet by default (NAT). Easiest fix:
install [Tailscale](https://tailscale.com/download) on both machines, log into
the same account, and the host shares their `tailscale ip -4` address — the
other player connects with `python3 gui.py <that-ip> 5555`.

## Next steps

- [ ] Lobby / rematch flow (play again without restarting)
- [ ] Reconnect handling and player-disconnect mid-game
- [ ] Sound effects and move animations
