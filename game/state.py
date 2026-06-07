"""Pure turn-based game logic. Knows nothing about sockets or rendering.

The demo game: a 5x5 grid. Players take turns claiming one empty cell each.
When the board is full, whoever claimed the most cells wins (ties possible).
Simple, but it exercises everything multiplayer needs -- turn order, move
validation, shared state, and an end condition.

Keeping this as a plain class with no I/O makes it trivial to unit-test and
lets us swap in a richer game later without touching the network code.
"""

BOARD_SIZE = 5
EMPTY = None


class GameState:
    def __init__(self, size: int = BOARD_SIZE):
        self.size = size
        # board[y][x] holds a player_id or EMPTY
        self.board = [[EMPTY for _ in range(size)] for _ in range(size)]
        self.players = []          # list of player_ids in join order
        self.symbols = {}          # player_id -> display symbol ("X", "O", ...)
        self.current_index = 0     # whose turn: index into self.players
        self.status = "waiting"    # "waiting" -> "playing" -> "finished"
        self.winner = None         # player_id, or "draw", once finished

    # --- lobby ---

    def add_player(self, player_id: str) -> str:
        """Register a player; return the symbol assigned to them."""
        symbol = "XO△□"[len(self.players)] if len(self.players) < 4 else "?"
        self.players.append(player_id)
        self.symbols[player_id] = symbol
        # Start once we have two players.
        if len(self.players) >= 2 and self.status == "waiting":
            self.status = "playing"
        return symbol

    @property
    def current_player(self):
        if not self.players:
            return None
        return self.players[self.current_index]

    # --- moves ---

    def apply_move(self, player_id: str, x: int, y: int):
        """Validate and apply a move. Raises ValueError if illegal."""
        if self.status != "playing":
            raise ValueError("game is not in progress")
        if player_id != self.current_player:
            raise ValueError("not your turn")
        if not (0 <= x < self.size and 0 <= y < self.size):
            raise ValueError("move out of bounds")
        if self.board[y][x] is not EMPTY:
            raise ValueError("cell already taken")

        self.board[y][x] = player_id

        if self._board_full():
            self._finish()
        else:
            self._advance_turn()

    def _advance_turn(self):
        self.current_index = (self.current_index + 1) % len(self.players)

    def _board_full(self) -> bool:
        return all(cell is not EMPTY for row in self.board for cell in row)

    def _finish(self):
        self.status = "finished"
        counts = {pid: 0 for pid in self.players}
        for row in self.board:
            for cell in row:
                if cell in counts:
                    counts[cell] += 1
        top = max(counts.values())
        leaders = [pid for pid, c in counts.items() if c == top]
        self.winner = leaders[0] if len(leaders) == 1 else "draw"

    # --- serialization for the network ---

    def snapshot(self) -> dict:
        """A JSON-safe full view of the game, sent to every client."""
        return {
            "board": self.board,
            "size": self.size,
            "players": self.players,
            "symbols": self.symbols,
            "current_player": self.current_player,
            "status": self.status,
            "winner": self.winner,
        }
