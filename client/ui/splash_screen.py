import pygame
import time
from typing import Optional, Tuple
from client.constants import WHITE, BLACK, BLUE, GREEN, GRAY


class SplashScreen:
    """Splash screen - shows loading and connects to server."""

    def __init__(self, screen: pygame.Surface, server_connection):
        self.screen = screen
        self.server = server_connection
        self.width, self.height = screen.get_size()

        # Fonts
        self.title_font = pygame.font.Font(None, 72)
        self.message_font = pygame.font.Font(None, 36)
        self.button_font = pygame.font.Font(None, 32)

        # State
        self.status = "connecting"  # connecting, connected, failed
        self.message = "Connecting to server..."
        self.pong_received = False
        self.connect_start_time = 0

        # Retry button
        self.retry_button = pygame.Rect(
            self.width // 2 - 75,
            self.height // 2 + 80,
            150, 50
        )

    def start_connection(self) -> None:
        """Start the connection process."""
        self.status = "connecting"
        self.message = "Connecting to server..."
        self.pong_received = False
        self.connect_start_time = time.time()

        # Register PONG handler
        self.server.register_handler("PONG", self._on_pong)

        # Try to connect
        if self.server.connect():
            self.message = "Connected! Waiting for server response..."
            self.server.ping()
        else:
            self.status = "failed"
            self.message = "Failed to connect to server"

    def _on_pong(self, message: dict) -> None:
        """Handle PONG response."""
        self.pong_received = True
        welcome = message.get("welcomeMessage", "Connected!")
        self.message = welcome
        self.status = "connected"

    def update(self) -> Optional[str]:
        """Update splash screen. Returns 'login' when ready to proceed."""
        # Check for timeout
        if self.status == "connecting":
            if time.time() - self.connect_start_time > 5.0:
                self.status = "failed"
                self.message = "Connection timeout"

        # If connected, wait a moment then proceed
        if self.status == "connected":
            return "login"

        return None

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Handle input events. Returns 'login' or None."""
        if event.type == pygame.MOUSEBUTTONDOWN:
            if self.status == "failed" and self.retry_button.collidepoint(event.pos):
                self.start_connection()

        return None

    def draw(self) -> None:
        """Draw the splash screen."""
        self.screen.fill((20, 60, 20))  # Dark green background

        # Title
        title = self.title_font.render("Soccer Stars", True, WHITE)
        title_rect = title.get_rect(center=(self.width // 2, self.height // 3))
        self.screen.blit(title, title_rect)

        # Subtitle
        subtitle = self.button_font.render("Online Multiplayer", True, GRAY)
        subtitle_rect = subtitle.get_rect(center=(self.width // 2, self.height // 3 + 50))
        self.screen.blit(subtitle, subtitle_rect)

        # Status message
        msg_color = WHITE if self.status != "failed" else (255, 100, 100)
        msg = self.message_font.render(self.message, True, msg_color)
        msg_rect = msg.get_rect(center=(self.width // 2, self.height // 2 + 20))
        self.screen.blit(msg, msg_rect)

        # Loading animation or retry button
        if self.status == "connecting":
            # Simple loading dots
            dots = "." * (int(time.time() * 2) % 4)
            loading = self.message_font.render(f"Please wait{dots}", True, GRAY)
            loading_rect = loading.get_rect(center=(self.width // 2, self.height // 2 + 60))
            self.screen.blit(loading, loading_rect)

        elif self.status == "failed":
            # Retry button
            pygame.draw.rect(self.screen, BLUE, self.retry_button, border_radius=8)
            retry_text = self.button_font.render("Retry", True, WHITE)
            retry_rect = retry_text.get_rect(center=self.retry_button.center)
            self.screen.blit(retry_text, retry_rect)
