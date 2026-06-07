"""Graphical client (pygame) with a main menu / lobby.

Two screens, driven by what the server last sent:
  * menu  -> set your name, create a game, or join an open one
  * game  -> the 5x5 board (waiting -> playing -> finished)

All networking lives in netclient.NetworkClient; this file only renders state
and turns clicks into actions.

Run:  python gui.py [host] [port]
"""

import sys

import pygame

from netclient import NetworkClient

HOST_DEFAULT = "127.0.0.1"
PORT_DEFAULT = 5555

# --- layout ---
CELL = 96
GAP = 8
PAD = 32
BANNER_H = 88
FOOTER_H = 72
FPS = 60

# --- palette ---
BG = (28, 31, 38)
PANEL = (36, 40, 49)
CELL_EMPTY = (48, 53, 64)
CELL_EMPTY_HOVER = (60, 66, 80)
GRID_SHADOW = (20, 22, 28)
TEXT = (236, 238, 242)
TEXT_DIM = (150, 156, 168)
ACCENT = (52, 152, 219)
ACCENT_HOVER = (72, 172, 239)
BTN = (60, 66, 80)
BTN_HOVER = (74, 81, 98)
DANGER = (235, 130, 130)
PLAYER_COLORS = [
    (235, 87, 87),    # player 0
    (52, 152, 219),   # player 1
    (46, 204, 113),   # player 2
    (241, 196, 15),   # player 3
]


def player_color(snapshot, player_id):
    try:
        idx = snapshot["players"].index(player_id)
    except (ValueError, KeyError):
        return TEXT_DIM
    return PLAYER_COLORS[idx % len(PLAYER_COLORS)]


class App:
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
        pygame.display.set_caption("Tölvuleikur")
        self.screen = pygame.display.set_mode((self.width, self.height))
        self.clock = pygame.time.Clock()
        self.font_big = pygame.font.Font(None, 46)
        self.font = pygame.font.Font(None, 30)
        self.font_small = pygame.font.Font(None, 24)

        self.name = ""           # local copy of the editable name
        self.editing_name = False
        self._name_initialized = False
        self._buttons = []       # (rect, callback) rebuilt each frame

    # ================= main loop =================

    def run(self):
        running = True
        while running:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and self.editing_name:
                    self._type_name(event)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self._on_click(event.pos)

            if not self.client.connected and not self.client.connect_error:
                self.client.last_error = "disconnected from server"

            # adopt the server-assigned name once
            if not self._name_initialized and self.client.name:
                self.name = self.client.name
                self._name_initialized = True

            self._draw()
            self.clock.tick(FPS)

        self.client.close()
        pygame.quit()

    def _type_name(self, event):
        if event.key == pygame.K_RETURN:
            self.editing_name = False
        elif event.key == pygame.K_BACKSPACE:
            self.name = self.name[:-1]
        elif event.unicode and event.unicode.isprintable() and len(self.name) < 16:
            self.name += event.unicode
        if self.client.connected:
            self.client.set_name(self.name or "Player")

    def _on_click(self, pos):
        # buttons first (they sit on top of everything)
        for rect, cb in self._buttons:
            if rect.collidepoint(pos):
                cb()
                return
        # menu: clicking the name box starts editing
        if self.client.mode == "menu" and getattr(self, "_name_box", None):
            self.editing_name = self._name_box.collidepoint(pos)
            return
        # game: clicking a board cell
        if self.client.mode == "game":
            self._board_click(pos)

    # ================= dispatch / draw =================

    def _draw(self):
        self.screen.fill(BG)
        self._buttons = []

        if self.client.connect_error:
            self._screen_message("Can't reach the server", DANGER,
                                  f"{self.client.host}:{self.client.port}",
                                  "Is someone running  python server.py  there?")
        elif not self.client.connected:
            self._screen_message("Lost connection to server", DANGER,
                                  "close the window and reopen to retry")
        elif self.client.mode == "menu":
            self._draw_menu()
        elif self.client.mode == "game":
            self._draw_game()
        else:
            self._screen_message("Connecting…", TEXT)

        pygame.display.flip()

    # ================= MENU =================

    def _draw_menu(self):
        self._text("Tölvuleikur", self.font_big, TEXT, center=(self.width // 2, 56))
        self._text("claim the grid — turn-based multiplayer", self.font_small,
                   TEXT_DIM, center=(self.width // 2, 88))

        # name field
        self._text("Your name", self.font_small, TEXT_DIM, topleft=(PAD, 128))
        box = pygame.Rect(PAD, 150, self.width - PAD * 2, 44)
        self._name_box = box
        border = ACCENT if self.editing_name else (70, 76, 90)
        pygame.draw.rect(self.screen, (24, 27, 33), box, border_radius=8)
        pygame.draw.rect(self.screen, border, box, width=2, border_radius=8)
        shown = self.name + ("|" if self.editing_name else "")
        self._text(shown or "click to type…", self.font, TEXT if self.name else TEXT_DIM,
                   midleft=(box.x + 12, box.centery))

        # create button
        create = pygame.Rect(PAD, 212, self.width - PAD * 2, 52)
        self._button(create, "＋  Create New Game", self._create, primary=True)

        # open games list
        self._text("Open games", self.font_small, TEXT_DIM, topleft=(PAD, 290))
        games = self.client.get_lobby() or []
        y = 318
        if not games:
            self._text("No open games yet — create one and wait for a friend.",
                       self.font_small, TEXT_DIM, topleft=(PAD, y + 6))
        for g in games:
            row = pygame.Rect(PAD, y, self.width - PAD * 2, 50)
            pygame.draw.rect(self.screen, PANEL, row, border_radius=10)
            self._text(g["host_name"], self.font, TEXT,
                       midleft=(row.x + 14, row.centery))
            self._text(f"{g['players']}/2", self.font_small, TEXT_DIM,
                       midright=(row.right - 92, row.centery))
            join = pygame.Rect(row.right - 80, row.y + 9, 70, 32)
            gid = g["id"]
            self._button(join, "Join", (lambda i=gid: self._join(i)))
            y += 58
            if y > self.height - 40:
                break

        if self.client.last_error:
            self._text(self.client.last_error, self.font_small, DANGER,
                       center=(self.width // 2, self.height - 18))

    def _create(self):
        if self.client.connected:
            self.client.set_name(self.name or "Player")
            self.client.create_game()

    def _join(self, game_id):
        if self.client.connected:
            self.client.set_name(self.name or "Player")
            self.client.join_game(game_id)

    # ================= GAME =================

    def _draw_game(self):
        snap = self.client.get_snapshot()
        if snap is None:
            self._screen_message("Loading game…", TEXT)
            return
        self.size = snap["size"]
        my_id = self.client.player_id
        my_turn = (snap["status"] == "playing" and snap["current_player"] == my_id)

        self._draw_banner(snap, my_turn)
        self._draw_board(snap, my_turn)
        self._draw_footer(snap)

        if snap["status"] == "finished":
            self._draw_gameover(snap)

    def _draw_banner(self, snap, my_turn):
        pygame.draw.rect(self.screen, PANEL, (0, 0, self.width, BANNER_H))
        status = snap["status"]

        # small "Leave" button (top-right)
        leave = pygame.Rect(self.width - 92, 14, 78, 30)
        self._button(leave, "Leave", self.client.leave_game)

        if status == "waiting":
            self._text("Waiting for opponent to join…", self.font, TEXT,
                       center=(self.width // 2 - 30, BANNER_H // 2 - 10))
            self._text("(share the server IP with a friend)", self.font_small,
                       TEXT_DIM, center=(self.width // 2 - 30, BANNER_H // 2 + 16))
            return

        cur = snap["current_player"]
        pygame.draw.circle(self.screen, player_color(snap, cur), (PAD + 2, BANNER_H // 2), 12)
        if status == "finished":
            label = "Game over"
        elif my_turn:
            label = "Your turn"
        else:
            opp = snap["names"].get(cur, "Opponent")
            label = f"{opp}'s turn"
        self._text(label, self.font_big, TEXT, midleft=(PAD + 22, BANNER_H // 2))

    def cell_rect(self, x, y):
        px = self.board_x + x * (CELL + GAP)
        py = self.board_y + y * (CELL + GAP)
        return pygame.Rect(px, py, CELL, CELL)

    def cell_at(self, mx, my):
        for y in range(self.size):
            for x in range(self.size):
                if self.cell_rect(x, y).collidepoint(mx, my):
                    return x, y
        return None

    def _draw_board(self, snap, my_turn):
        board = snap["board"]
        hover = self.cell_at(*pygame.mouse.get_pos()) if my_turn else None
        for y in range(self.size):
            for x in range(self.size):
                rect = self.cell_rect(x, y)
                pygame.draw.rect(self.screen, GRID_SHADOW, rect.move(0, 3), border_radius=12)
                owner = board[y][x]
                if owner:
                    pygame.draw.rect(self.screen, player_color(snap, owner), rect, border_radius=12)
                    self._draw_token(rect, snap, owner)
                else:
                    base = CELL_EMPTY_HOVER if hover == (x, y) else CELL_EMPTY
                    pygame.draw.rect(self.screen, base, rect, border_radius=12)
                    if hover == (x, y):
                        self._draw_ring(rect, player_color(snap, self.client.player_id))

    def _draw_token(self, rect, snap, owner):
        idx = snap["players"].index(owner) if owner in snap["players"] else 0
        cx, cy = rect.center
        r = CELL // 4
        if idx == 0:
            pygame.draw.line(self.screen, TEXT, (cx - r, cy - r), (cx + r, cy + r), 6)
            pygame.draw.line(self.screen, TEXT, (cx + r, cy - r), (cx - r, cy + r), 6)
        elif idx == 1:
            pygame.draw.circle(self.screen, TEXT, (cx, cy), r, 6)
        else:
            pygame.draw.circle(self.screen, TEXT, (cx, cy), r // 2)

    def _draw_ring(self, rect, color, alpha=90):
        surf = pygame.Surface((rect.width, rect.height), pygame.SRCALPHA)
        pygame.draw.circle(surf, (*color, alpha), (rect.width // 2, rect.height // 2), CELL // 4, 5)
        self.screen.blit(surf, rect.topleft)

    def _draw_footer(self, snap):
        fy = self.height - FOOTER_H
        pygame.draw.rect(self.screen, PANEL, (0, fy, self.width, FOOTER_H))
        counts = {pid: 0 for pid in snap["players"]}
        for row in snap["board"]:
            for cell in row:
                if cell in counts:
                    counts[cell] += 1
        x, cy = PAD, fy + FOOTER_H // 2
        for pid in snap["players"]:
            pygame.draw.circle(self.screen, player_color(snap, pid), (x + 8, cy), 9)
            name = snap["names"].get(pid, "?")
            if pid == self.client.player_id:
                name += " (you)"
            self._text(f"{name}: {counts[pid]}", self.font_small, TEXT, midleft=(x + 24, cy))
            x += self.width // 2 - 10

    def _draw_gameover(self, snap):
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((10, 12, 16, 190))
        self.screen.blit(overlay, (0, 0))
        winner = snap["winner"]
        if winner == "draw":
            msg, col = "It's a draw!", TEXT
        elif winner == self.client.player_id:
            msg, col = "You win! 🎉", player_color(snap, winner)
        else:
            msg, col = f"{snap['names'].get(winner, 'Opponent')} wins", player_color(snap, winner)
        self._text(msg, self.font_big, col, center=(self.width // 2, self.height // 2 - 40))
        back = pygame.Rect(self.width // 2 - 110, self.height // 2 + 4, 220, 52)
        self._button(back, "Back to menu", self.client.leave_game, primary=True)

    def _board_click(self, pos):
        snap = self.client.get_snapshot()
        if not snap or snap["status"] != "playing":
            return
        if snap["current_player"] != self.client.player_id:
            return
        cell = self.cell_at(*pos)
        if cell and snap["board"][cell[1]][cell[0]] is None:
            self.client.last_error = None
            self.client.send_move(*cell)

    # ================= widgets / text =================

    def _button(self, rect, label, callback, primary=False):
        hover = rect.collidepoint(pygame.mouse.get_pos())
        if primary:
            color = ACCENT_HOVER if hover else ACCENT
        else:
            color = BTN_HOVER if hover else BTN
        pygame.draw.rect(self.screen, color, rect, border_radius=10)
        self._text(label, self.font if rect.height >= 44 else self.font_small, TEXT,
                   center=rect.center)
        self._buttons.append((rect, callback))

    def _screen_message(self, title, color, *lines):
        self._text(title, self.font_big, color, center=(self.width // 2, self.height // 2 - 20))
        dy = 24
        for line in lines:
            self._text(line, self.font_small, TEXT_DIM,
                       center=(self.width // 2, self.height // 2 + dy))
            dy += 28

    def _text(self, s, font, color, **kw):
        surf = font.render(s, True, color)
        self.screen.blit(surf, surf.get_rect(**kw))


def main():
    host = sys.argv[1] if len(sys.argv) > 1 else HOST_DEFAULT
    port = int(sys.argv[2]) if len(sys.argv) > 2 else PORT_DEFAULT

    client = NetworkClient(host, port)
    try:
        client.connect()
    except OSError as e:
        print(f"Could not connect to {host}:{port} -- is the server running? ({e})")

    App(client).run()


if __name__ == "__main__":
    main()
