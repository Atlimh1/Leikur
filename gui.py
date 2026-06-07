"""Graphical client (pygame). Same game, same server -- just a real window
instead of the terminal. Reuses netclient.NetworkClient untouched, which is
the whole point of keeping networking separate from rendering.

Run:  python gui.py [host] [port]
  - no host  -> 127.0.0.1 (local test)
  - friend's Tailscale IP -> play across the internet
"""

import sys

import pygame

from netclient import NetworkClient

HOST_DEFAULT = "127.0.0.1"
PORT_DEFAULT = 5555

# --- layout ---
CELL = 96
GAP = 8                      # gap between cells
PAD = 32                     # outer padding around the board
BANNER_H = 88                # top area: whose turn
FOOTER_H = 72                # bottom area: scores / status
FPS = 60

# --- palette ---
BG = (28, 31, 38)
PANEL = (36, 40, 49)
CELL_EMPTY = (48, 53, 64)
CELL_EMPTY_HOVER = (60, 66, 80)
GRID_SHADOW = (20, 22, 28)
TEXT = (236, 238, 242)
TEXT_DIM = (150, 156, 168)
# one distinct color per player, by join order
PLAYER_COLORS = [
    (235, 87, 87),    # red    (player 0 / X)
    (52, 152, 219),   # blue   (player 1 / O)
    (46, 204, 113),   # green  (player 2)
    (241, 196, 15),   # yellow (player 3)
]


def player_color(snapshot, player_id):
    try:
        idx = snapshot["players"].index(player_id)
    except (ValueError, KeyError):
        return TEXT_DIM
    return PLAYER_COLORS[idx % len(PLAYER_COLORS)]


class GameWindow:
    def __init__(self, client: NetworkClient, size: int = 5):
        self.client = client
        self.size = size

        board_px = size * CELL + (size - 1) * GAP
        self.board_px = board_px
        self.width = board_px + PAD * 2
        self.height = BANNER_H + board_px + FOOTER_H + PAD
        self.board_x = PAD
        self.board_y = BANNER_H

        pygame.init()
        pygame.display.set_caption("Tölvuleikur — claim the grid")
        self.screen = pygame.display.set_mode((self.width, self.height))
        self.clock = pygame.time.Clock()
        self.font_big = pygame.font.Font(None, 44)
        self.font = pygame.font.Font(None, 30)
        self.font_small = pygame.font.Font(None, 24)

    # --- geometry helpers ---

    def cell_rect(self, x, y):
        px = self.board_x + x * (CELL + GAP)
        py = self.board_y + y * (CELL + GAP)
        return pygame.Rect(px, py, CELL, CELL)

    def cell_at(self, mouse_x, mouse_y):
        """Which (x, y) cell is under the mouse, or None."""
        for y in range(self.size):
            for x in range(self.size):
                if self.cell_rect(x, y).collidepoint(mouse_x, mouse_y):
                    return x, y
        return None

    # --- drawing ---

    def draw(self):
        snap = self.client.get_snapshot()
        self.screen.fill(BG)

        if snap is None:
            self._center_text("Connecting…", self.font_big, TEXT)
            pygame.display.flip()
            return

        self.size = snap["size"]
        my_id = self.client.player_id
        my_turn = (snap["status"] == "playing" and snap["current_player"] == my_id)

        self._draw_banner(snap, my_turn)
        self._draw_board(snap, my_turn)
        self._draw_footer(snap)

        if snap["status"] == "finished":
            self._draw_gameover(snap)

        pygame.display.flip()

    def _draw_banner(self, snap, my_turn):
        pygame.draw.rect(self.screen, PANEL, (0, 0, self.width, BANNER_H))
        status = snap["status"]

        if status == "waiting":
            self._text("Waiting for a second player…", self.font, TEXT,
                       center=(self.width // 2, BANNER_H // 2))
            return

        cur = snap["current_player"]
        col = player_color(snap, cur)
        # turn dot
        pygame.draw.circle(self.screen, col, (PAD + 14, BANNER_H // 2), 12)
        if status == "finished":
            label = "Game over"
        elif my_turn:
            label = "Your turn"
        else:
            label = "Opponent's turn"
        self._text(label, self.font_big, TEXT,
                   midleft=(PAD + 38, BANNER_H // 2))

        # your color swatch on the right
        if self.client.player_id:
            mine = player_color(snap, self.client.player_id)
            pygame.draw.circle(self.screen, mine, (self.width - PAD - 10, BANNER_H // 2), 10)
            self._text("you", self.font_small, TEXT_DIM,
                       midright=(self.width - PAD - 26, BANNER_H // 2))

    def _draw_board(self, snap, my_turn):
        board = snap["board"]
        hover = None
        if my_turn:
            mx, my = pygame.mouse.get_pos()
            hover = self.cell_at(mx, my)

        for y in range(self.size):
            for x in range(self.size):
                rect = self.cell_rect(x, y)
                # subtle drop shadow
                pygame.draw.rect(self.screen, GRID_SHADOW, rect.move(0, 3),
                                 border_radius=12)
                owner = board[y][x]
                if owner:
                    col = player_color(snap, owner)
                    pygame.draw.rect(self.screen, col, rect, border_radius=12)
                    self._draw_token(rect, snap, owner)
                else:
                    base = CELL_EMPTY
                    if hover == (x, y) and board[y][x] is None:
                        base = CELL_EMPTY_HOVER
                    pygame.draw.rect(self.screen, base, rect, border_radius=12)
                    # ghost preview of your move
                    if hover == (x, y):
                        ghost = player_color(snap, self.client.player_id)
                        self._draw_ring(rect, ghost, alpha=90)

    def _draw_token(self, rect, snap, owner):
        """Draw a white marker on an owned cell so colors aren't the only cue."""
        idx = snap["players"].index(owner) if owner in snap["players"] else 0
        cx, cy = rect.center
        r = CELL // 4
        if idx == 0:        # X
            off = r
            pygame.draw.line(self.screen, TEXT, (cx - off, cy - off), (cx + off, cy + off), 6)
            pygame.draw.line(self.screen, TEXT, (cx + off, cy - off), (cx - off, cy + off), 6)
        elif idx == 1:      # O
            pygame.draw.circle(self.screen, TEXT, (cx, cy), r, 6)
        else:               # filled dot for any extra players
            pygame.draw.circle(self.screen, TEXT, (cx, cy), r // 2)

    def _draw_ring(self, rect, color, alpha=90):
        surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        c = (*color, alpha)
        pygame.draw.circle(surf, c, (rect.width // 2, rect.height // 2), CELL // 4, 5)
        self.screen.blit(surf, rect.topleft)

    def _draw_footer(self, snap):
        fy = self.height - FOOTER_H
        pygame.draw.rect(self.screen, PANEL, (0, fy, self.width, FOOTER_H))

        # score chips per player
        counts = {pid: 0 for pid in snap["players"]}
        for row in snap["board"]:
            for cell in row:
                if cell in counts:
                    counts[cell] += 1

        x = PAD
        cy = fy + FOOTER_H // 2
        for pid in snap["players"]:
            col = player_color(snap, pid)
            pygame.draw.circle(self.screen, col, (x + 8, cy), 9)
            label = "you" if pid == self.client.player_id else "opp"
            self._text(f"{label}: {counts[pid]}", self.font, TEXT, midleft=(x + 24, cy))
            x += 130

        if self.client.last_error:
            self._text(self.client.last_error, self.font_small, (235, 130, 130),
                       midright=(self.width - PAD, cy))

    def _draw_gameover(self, snap):
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((10, 12, 16, 180))
        self.screen.blit(overlay, (0, 0))

        winner = snap["winner"]
        if winner == "draw":
            msg, col = "It's a draw!", TEXT
        elif winner == self.client.player_id:
            msg, col = "You win! 🎉", player_color(snap, winner)
        else:
            msg, col = "You lose", player_color(snap, winner)
        self._center_text(msg, self.font_big, col, dy=-12)
        self._center_text("close the window to exit", self.font_small, TEXT_DIM, dy=28)

    # --- tiny text helpers ---

    def _text(self, s, font, color, **kw):
        surf = font.render(s, True, color)
        self.screen.blit(surf, surf.get_rect(**kw))

    def _center_text(self, s, font, color, dy=0):
        surf = font.render(s, True, color)
        self.screen.blit(surf, surf.get_rect(center=(self.width // 2, self.height // 2 + dy)))

    # --- main loop ---

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._handle_click(event.pos)

            if not self.client.connected:
                # keep drawing the last frame but note the disconnect
                self.client.last_error = "disconnected from server"

            self.draw()
            self.clock.tick(FPS)

        self.client.close()
        pygame.quit()

    def _handle_click(self, pos):
        snap = self.client.get_snapshot()
        if not snap or snap["status"] != "playing":
            return
        if snap["current_player"] != self.client.player_id:
            return
        cell = self.cell_at(*pos)
        if cell:
            x, y = cell
            if snap["board"][y][x] is None:
                self.client.last_error = None
                self.client.send_move(x, y)


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else HOST_DEFAULT
    port = int(sys.argv[2]) if len(sys.argv) > 2 else PORT_DEFAULT

    client = NetworkClient(host, port)
    try:
        client.connect()
    except OSError as e:
        print(f"Could not connect to {host}:{port} -- is the server running? ({e})")
        return

    GameWindow(client).run()


if __name__ == "__main__":
    main()
