import pygame
import time
from typing import Optional, List, Dict
from client.constants import WHITE, BLACK, BLUE, GREEN, GRAY, LIGHT_GRAY, RED, YELLOW


class LobbyScreen:

    def __init__(self, screen: pygame.Surface, server_connection):
        self.screen = screen
        self.server = server_connection
        self.width, self.height = screen.get_size()

        # Fonts
        self.title_font = pygame.font.Font(None, 48)
        self.user_font = pygame.font.Font(None, 32)
        self.status_font = pygame.font.Font(None, 24)
        self.button_font = pygame.font.Font(None, 28)

        # Users list
        self.users: List[Dict] = []
        self.selected_user_index: Optional[int] = None
        self.scroll_offset = 0

        # User list area
        self.list_area = pygame.Rect(50, 120, self.width - 100, 350)
        self.user_item_height = 50

        # Buttons
        self.refresh_button = pygame.Rect(self.width - 150, 60, 100, 35)
        self.invite_button = pygame.Rect(self.width // 2 - 75, 490, 150, 45)
        self.logout_button = pygame.Rect(50, 60, 100, 35)

        # Invite popup
        self.show_invite_popup = False
        self.invite_data: Optional[Dict] = None
        self.popup_accept_btn = pygame.Rect(self.width // 2 - 130, 320, 100, 40)
        self.popup_reject_btn = pygame.Rect(self.width // 2 + 30, 320, 100, 40)

        # State
        self.last_refresh = 0
        self.refresh_interval = 5.0  # Auto-refresh every 5 seconds
        self.status_message = ""
        self.waiting_for_response = False

        # Game start data
        self.game_start_data: Optional[Dict] = None

        # UDP port for P2P
        self.my_udp_port = 6000  # Will be set properly

        # Register handlers
        self.server.register_handler("ONLINE_USERS_LIST", self._on_users_list)
        self.server.register_handler("USER_STATUS_UPDATE", self._on_user_status)
        self.server.register_handler("GAME_INVITE_NOTIFICATION", self._on_invite_received)
        self.server.register_handler("GAME_START", self._on_game_start)
        self.server.register_handler("GAME_INVITE_CANCELLED", self._on_invite_cancelled)
        self.server.register_handler("ERROR", self._on_error)

    def set_udp_port(self, port: int) -> None:
        """Set the UDP port to use for P2P."""
        self.my_udp_port = port

    def enter(self) -> None:
        """Called when entering the lobby."""
        self.game_start_data = None
        self.waiting_for_response = False
        self.show_invite_popup = False
        self.invite_data = None
        self._refresh_users()

    def _refresh_users(self) -> None:
        """Request updated user list."""
        self.server.get_online_users()
        self.last_refresh = time.time()

    def _on_users_list(self, message: dict) -> None:
        """Handle user list response."""
        self.users = message.get("users", [])
        # Remove self from list
        self.users = [u for u in self.users if u.get("username") != self.server.username]
        self.selected_user_index = None

    def _on_user_status(self, message: dict) -> None:
        """Handle user status update."""
        username = message.get("username")
        status = message.get("status")

        if status == "offline":
            self.users = [u for u in self.users if u.get("username") != username]
        else:
            # Update or add user
            found = False
            for user in self.users:
                if user.get("username") == username:
                    user["status"] = status
                    found = True
                    break
            if not found and username != self.server.username:
                self.users.append({"username": username, "status": status})

    def _on_invite_received(self, message: dict) -> None:
        """Handle incoming game invite."""
        self.invite_data = message
        self.show_invite_popup = True

    def _on_game_start(self, message: dict) -> None:
        """Handle game start notification."""
        self.game_start_data = message
        self.waiting_for_response = False
        self.status_message = "Game starting!"

    def _on_invite_cancelled(self, message: dict) -> None:
        """Handle invite cancelled."""
        self.waiting_for_response = False
        self.status_message = message.get("reason", "Invitation cancelled")

    def _on_error(self, message: dict) -> None:
        """Handle error."""
        self.waiting_for_response = False
        self.status_message = message.get("errorMessage", "Error occurred")

    def _get_visible_users(self) -> List[tuple]:
        """Get users visible in the scroll area."""
        visible = []
        max_visible = self.list_area.height // self.user_item_height

        start_index = self.scroll_offset
        end_index = min(start_index + max_visible, len(self.users))

        for i in range(start_index, end_index):
            y = self.list_area.y + (i - start_index) * self.user_item_height
            visible.append((i, self.users[i], y))

        return visible

    def _invite_selected_user(self) -> None:
        """Send invite to selected user."""
        if self.selected_user_index is None or self.waiting_for_response:
            return

        user = self.users[self.selected_user_index]
        if user.get("status") != "free":
            self.status_message = "User is not available"
            return

        self.server.invite_player(user["username"], self.my_udp_port)
        self.waiting_for_response = True
        self.status_message = f"Inviting {user['username']}..."

    def _respond_to_invite(self, accept: bool) -> None:
        """Respond to an invite."""
        if self.invite_data:
            invite_id = self.invite_data.get("inviteId")
            self.server.respond_to_invite(invite_id, accept, self.my_udp_port)
            self.show_invite_popup = False
            self.invite_data = None
            if accept:
                self.waiting_for_response = True
                self.status_message = "Joining game..."

    def update(self) -> Optional[str]:
        """Update lobby. Returns 'game' when game starts, 'login' on logout."""
        # Auto-refresh
        if time.time() - self.last_refresh > self.refresh_interval:
            self._refresh_users()

        # Check for game start
        if self.game_start_data:
            return "game"

        return None

    def get_game_start_data(self) -> Optional[Dict]:
        """Get game start data and clear it."""
        data = self.game_start_data
        self.game_start_data = None
        return data

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Handle input events. Returns 'login' on logout."""
        # Handle invite popup first
        if self.show_invite_popup:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.popup_accept_btn.collidepoint(event.pos):
                    self._respond_to_invite(True)
                elif self.popup_reject_btn.collidepoint(event.pos):
                    self._respond_to_invite(False)
            return None

        if event.type == pygame.MOUSEBUTTONDOWN:
            # Logout button
            if self.logout_button.collidepoint(event.pos):
                self.server.logout()
                self.server.session_id = None
                return "login"

            # Refresh button
            if self.refresh_button.collidepoint(event.pos):
                self._refresh_users()
                self.status_message = "Refreshing..."

            # Invite button
            if self.invite_button.collidepoint(event.pos):
                self._invite_selected_user()

            # User selection
            if self.list_area.collidepoint(event.pos):
                for idx, user, y in self._get_visible_users():
                    item_rect = pygame.Rect(self.list_area.x, y,
                                          self.list_area.width, self.user_item_height)
                    if item_rect.collidepoint(event.pos):
                        self.selected_user_index = idx
                        break

        # Scroll
        if event.type == pygame.MOUSEWHEEL:
            if self.list_area.collidepoint(pygame.mouse.get_pos()):
                self.scroll_offset -= event.y
                max_scroll = max(0, len(self.users) - self.list_area.height // self.user_item_height)
                self.scroll_offset = max(0, min(self.scroll_offset, max_scroll))

        return None

    def draw(self) -> None:
        """Draw the lobby screen."""
        self.screen.fill((30, 70, 30))

        # Title
        title = self.title_font.render("Lobby", True, WHITE)
        title_rect = title.get_rect(center=(self.width // 2, 40))
        self.screen.blit(title, title_rect)

        # Welcome message
        welcome = self.status_font.render(f"Welcome, {self.server.username}!", True, LIGHT_GRAY)
        self.screen.blit(welcome, (self.width // 2 - welcome.get_width() // 2, 70))

        # Logout button
        pygame.draw.rect(self.screen, (150, 50, 50), self.logout_button, border_radius=5)
        logout_text = self.button_font.render("Logout", True, WHITE)
        logout_rect = logout_text.get_rect(center=self.logout_button.center)
        self.screen.blit(logout_text, logout_rect)

        # Refresh button
        pygame.draw.rect(self.screen, BLUE, self.refresh_button, border_radius=5)
        refresh_text = self.button_font.render("Refresh", True, WHITE)
        refresh_rect = refresh_text.get_rect(center=self.refresh_button.center)
        self.screen.blit(refresh_text, refresh_rect)

        # Online users header
        header = self.user_font.render("Online Players:", True, WHITE)
        self.screen.blit(header, (self.list_area.x, self.list_area.y - 30))

        # Users list background
        pygame.draw.rect(self.screen, (40, 80, 40), self.list_area, border_radius=8)
        pygame.draw.rect(self.screen, (60, 120, 60), self.list_area, 2, border_radius=8)

        # Draw users
        if not self.users:
            no_users = self.status_font.render("No other players online", True, GRAY)
            no_users_rect = no_users.get_rect(center=self.list_area.center)
            self.screen.blit(no_users, no_users_rect)
        else:
            for idx, user, y in self._get_visible_users():
                item_rect = pygame.Rect(self.list_area.x + 5, y + 2,
                                       self.list_area.width - 10, self.user_item_height - 4)

                # Highlight selected
                if idx == self.selected_user_index:
                    pygame.draw.rect(self.screen, (60, 100, 60), item_rect, border_radius=5)

                # Username
                username = user.get("username", "Unknown")
                name_surface = self.user_font.render(username, True, WHITE)
                self.screen.blit(name_surface, (item_rect.x + 15, item_rect.y + 10))

                # Status
                status = user.get("status", "unknown")
                status_colors = {
                    "free": (100, 255, 100),
                    "in_game": (255, 200, 100),
                    "busy": (255, 100, 100)
                }
                status_color = status_colors.get(status, GRAY)
                status_surface = self.status_font.render(status.upper(), True, status_color)
                self.screen.blit(status_surface, (item_rect.right - 100, item_rect.y + 15))

        # Invite button
        invite_enabled = (self.selected_user_index is not None and
                         not self.waiting_for_response and
                         self.users and
                         self.users[self.selected_user_index].get("status") == "free")
        btn_color = BLUE if invite_enabled else GRAY
        pygame.draw.rect(self.screen, btn_color, self.invite_button, border_radius=8)
        invite_text = "Waiting..." if self.waiting_for_response else "Invite to Play"
        invite_surface = self.button_font.render(invite_text, True, WHITE)
        invite_rect = invite_surface.get_rect(center=self.invite_button.center)
        self.screen.blit(invite_surface, invite_rect)

        # Status message
        if self.status_message:
            status_surface = self.status_font.render(self.status_message, True, YELLOW)
            status_rect = status_surface.get_rect(center=(self.width // 2, 550))
            self.screen.blit(status_surface, status_rect)

        # Invite popup
        if self.show_invite_popup and self.invite_data:
            self._draw_invite_popup()

    def _draw_invite_popup(self) -> None:
        """Draw the invite popup."""
        # Overlay
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 180))
        self.screen.blit(overlay, (0, 0))

        # Popup box
        popup_rect = pygame.Rect(self.width // 2 - 175, 200, 350, 200)
        pygame.draw.rect(self.screen, (40, 80, 40), popup_rect, border_radius=10)
        pygame.draw.rect(self.screen, WHITE, popup_rect, 3, border_radius=10)

        # Title
        title = self.user_font.render("Game Invitation", True, WHITE)
        title_rect = title.get_rect(center=(popup_rect.centerx, popup_rect.y + 30))
        self.screen.blit(title, title_rect)

        # Message
        from_user = self.invite_data.get("fromUsername", "Someone")
        msg = self.status_font.render(f"{from_user} wants to play with you!", True, WHITE)
        msg_rect = msg.get_rect(center=(popup_rect.centerx, popup_rect.centery - 10))
        self.screen.blit(msg, msg_rect)

        # Accept button
        pygame.draw.rect(self.screen, GREEN, self.popup_accept_btn, border_radius=8)
        accept_text = self.button_font.render("Accept", True, WHITE)
        accept_rect = accept_text.get_rect(center=self.popup_accept_btn.center)
        self.screen.blit(accept_text, accept_rect)

        # Reject button
        pygame.draw.rect(self.screen, RED, self.popup_reject_btn, border_radius=8)
        reject_text = self.button_font.render("Reject", True, WHITE)
        reject_rect = reject_text.get_rect(center=self.popup_reject_btn.center)
        self.screen.blit(reject_text, reject_rect)
