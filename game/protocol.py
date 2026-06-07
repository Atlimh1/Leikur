"""Wire protocol shared by server and client.

Messages are JSON objects, one per line ("\n"-delimited framing) over TCP.
Every message has a "type" field; the rest of the fields depend on the type.

Keeping this in one module means the server and client can never disagree
about the format -- both import the same constants and helpers.
"""

import json


# --- Message types: client -> server ---
SET_NAME = "set_name"        # {type, name}        -- set your display name
CREATE_GAME = "create_game"  # {type}              -- open a new game, you host it
JOIN_GAME = "join_game"      # {type, game_id}     -- join someone's open game
LEAVE_GAME = "leave_game"    # {type}              -- go back to the menu/lobby
MOVE = "move"                # {type, x, y}        -- claim a cell on your turn

# --- Message types: server -> client ---
WELCOME = "welcome"  # {type, player_id, name}           -- sent once on connect
LOBBY = "lobby"      # {type, games:[...], your_name}    -- you're in the menu
STATE = "state"      # {type, ...game snapshot..., names} -- you're in a game
ERROR = "error"      # {type, message}                   -- something went wrong


def encode(message: dict) -> bytes:
    """Serialize a message dict to a single framed line of bytes."""
    return (json.dumps(message) + "\n").encode("utf-8")


class MessageStream:
    """Reads newline-delimited JSON messages off a socket.

    TCP is a byte stream with no message boundaries, so we buffer incoming
    bytes and split on newlines. Call `feed()` with whatever recv() returned
    and it yields complete messages.
    """

    def __init__(self):
        self._buffer = b""

    def feed(self, data: bytes):
        """Add received bytes; yield each complete message decoded as a dict."""
        self._buffer += data
        while b"\n" in self._buffer:
            line, self._buffer = self._buffer.split(b"\n", 1)
            line = line.strip()
            if line:
                yield json.loads(line.decode("utf-8"))
