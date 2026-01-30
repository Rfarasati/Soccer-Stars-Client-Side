import pygame
from typing import Optional
from client.constants import WHITE, BLACK, BLUE, GREEN, GRAY, LIGHT_GRAY, RED


class InputBox:
    """Text input box."""

    def __init__(self, x: int, y: int, width: int, height: int,
                 placeholder: str = "", password: bool = False):
        self.rect = pygame.Rect(x, y, width, height)
        self.text = ""
        self.placeholder = placeholder
        self.password = password
        self.active = False
        self.font = pygame.font.Font(None, 32)

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.MOUSEBUTTONDOWN:
            self.active = self.rect.collidepoint(event.pos)

        if event.type == pygame.KEYDOWN and self.active:
            if event.key == pygame.K_BACKSPACE:
                self.text = self.text[:-1]
            elif event.key == pygame.K_TAB:
                pass  # Handle in screen
            elif event.key == pygame.K_RETURN:
                pass  # Handle in screen
            elif len(self.text) < 30:
                if event.unicode.isprintable():
                    self.text += event.unicode

    def draw(self, screen: pygame.Surface) -> None:
        # Background
        color = WHITE if self.active else LIGHT_GRAY
        pygame.draw.rect(screen, color, self.rect, border_radius=5)
        pygame.draw.rect(screen, BLUE if self.active else GRAY, self.rect, 2, border_radius=5)

        # Text
        display_text = self.text if not self.password else "*" * len(self.text)
        if not display_text and not self.active:
            display_text = self.placeholder
            text_surface = self.font.render(display_text, True, GRAY)
        else:
            text_surface = self.font.render(display_text, True, BLACK)

        # Clip text to fit
        text_rect = text_surface.get_rect(midleft=(self.rect.x + 10, self.rect.centery))
        screen.blit(text_surface, text_rect)

        # Cursor
        if self.active:
            cursor_x = text_rect.right + 2
            pygame.draw.line(screen, BLACK,
                           (cursor_x, self.rect.y + 8),
                           (cursor_x, self.rect.bottom - 8), 2)


class LoginScreen:
    """Login/Register screen."""

    def __init__(self, screen: pygame.Surface, server_connection):
        self.screen = screen
        self.server = server_connection
        self.width, self.height = screen.get_size()

        # Fonts
        self.title_font = pygame.font.Font(None, 48)
        self.label_font = pygame.font.Font(None, 28)
        self.button_font = pygame.font.Font(None, 32)
        self.error_font = pygame.font.Font(None, 24)

        # Mode: "login" or "register"
        self.mode = "login"

        # Input boxes
        center_x = self.width // 2
        self.username_box = InputBox(center_x - 150, 180, 300, 40, "Username")
        self.password_box = InputBox(center_x - 150, 260, 300, 40, "Password", password=True)
        self.email_box = InputBox(center_x - 150, 340, 300, 40, "Email")

        self.input_boxes = [self.username_box, self.password_box, self.email_box]
        self.active_box_index = 0
        self.username_box.active = True

        # Buttons
        self.submit_button = pygame.Rect(center_x - 75, 420, 150, 45)
        self.toggle_button = pygame.Rect(center_x - 100, 480, 200, 35)

        # State
        self.error_message = ""
        self.waiting = False

        # Register handlers
        self.server.register_handler("LOGIN_RESPONSE", self._on_login_response)
        self.server.register_handler("REGISTER_RESPONSE", self._on_register_response)
        self.server.register_handler("ERROR", self._on_error)

    def _on_login_response(self, message: dict) -> None:
        self.waiting = False
        if message.get("success"):
            self.server.session_id = message.get("sessionId")
            self.server.username = message.get("username")
            self.error_message = ""
        else:
            self.error_message = message.get("message", "Login failed")

    def _on_register_response(self, message: dict) -> None:
        self.waiting = False
        if message.get("success"):
            self.error_message = "Registration successful! Please login."
            self.mode = "login"
            self.password_box.text = ""
            self.email_box.text = ""
        else:
            self.error_message = message.get("message", "Registration failed")

    def _on_error(self, message: dict) -> None:
        self.waiting = False
        self.error_message = message.get("errorMessage", "An error occurred")

    def _switch_active_box(self, direction: int) -> None:
        """Switch to next/previous input box."""
        self.input_boxes[self.active_box_index].active = False

        max_index = 2 if self.mode == "register" else 1
        self.active_box_index = (self.active_box_index + direction) % (max_index + 1)

        self.input_boxes[self.active_box_index].active = True

    def _submit(self) -> None:
        """Submit the form."""
        username = self.username_box.text.strip()
        password = self.password_box.text.strip()
        email = self.email_box.text.strip()

        if not username:
            self.error_message = "Please enter a username"
            return
        if not password:
            self.error_message = "Please enter a password"
            return
        if self.mode == "register" and not email:
            self.error_message = "Please enter an email"
            return

        self.waiting = True
        self.error_message = ""

        if self.mode == "login":
            self.server.login(username, password)
        else:
            self.server.register(username, email, password)

    def update(self) -> Optional[str]:
        """Update login screen. Returns 'lobby' when logged in."""
        if self.server.session_id:
            return "lobby"
        return None

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Handle input events."""
        if self.waiting:
            return None

        # Input boxes
        for box in self.input_boxes:
            box.handle_event(event)

        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_TAB:
                self._switch_active_box(1)
            elif event.key == pygame.K_RETURN:
                self._submit()

        if event.type == pygame.MOUSEBUTTONDOWN:
            # Update active box index based on which is active
            for i, box in enumerate(self.input_boxes):
                if box.active:
                    self.active_box_index = i

            if self.submit_button.collidepoint(event.pos):
                self._submit()
            elif self.toggle_button.collidepoint(event.pos):
                self.mode = "register" if self.mode == "login" else "login"
                self.error_message = ""
                # Reset email box visibility
                if self.mode == "login" and self.active_box_index == 2:
                    self.email_box.active = False
                    self.username_box.active = True
                    self.active_box_index = 0

        return None

    def draw(self) -> None:
        """Draw the login screen."""
        self.screen.fill((30, 70, 30))

        # Title
        title_text = "Login" if self.mode == "login" else "Register"
        title = self.title_font.render(title_text, True, WHITE)
        title_rect = title.get_rect(center=(self.width // 2, 100))
        self.screen.blit(title, title_rect)

        # Labels and input boxes
        username_label = self.label_font.render("Username:", True, WHITE)
        self.screen.blit(username_label, (self.width // 2 - 150, 155))
        self.username_box.draw(self.screen)

        password_label = self.label_font.render("Password:", True, WHITE)
        self.screen.blit(password_label, (self.width // 2 - 150, 235))
        self.password_box.draw(self.screen)

        if self.mode == "register":
            email_label = self.label_font.render("Email:", True, WHITE)
            self.screen.blit(email_label, (self.width // 2 - 150, 315))
            self.email_box.draw(self.screen)

        # Submit button
        btn_color = GRAY if self.waiting else BLUE
        pygame.draw.rect(self.screen, btn_color, self.submit_button, border_radius=8)
        submit_text = "Please wait..." if self.waiting else ("Login" if self.mode == "login" else "Register")
        submit_surface = self.button_font.render(submit_text, True, WHITE)
        submit_rect = submit_surface.get_rect(center=self.submit_button.center)
        self.screen.blit(submit_surface, submit_rect)

        # Toggle button
        toggle_text = "Create Account" if self.mode == "login" else "Back to Login"
        toggle_surface = self.label_font.render(toggle_text, True, (150, 200, 255))
        toggle_rect = toggle_surface.get_rect(center=self.toggle_button.center)
        self.screen.blit(toggle_surface, toggle_rect)

        # Error message
        if self.error_message:
            error_color = (100, 255, 100) if "successful" in self.error_message.lower() else (255, 100, 100)
            error_surface = self.error_font.render(self.error_message, True, error_color)
            error_rect = error_surface.get_rect(center=(self.width // 2, 530))
            self.screen.blit(error_surface, error_rect)
