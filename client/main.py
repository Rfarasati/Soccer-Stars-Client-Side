#!/usr/bin/env python3
"""
Soccer Stars - Online Multiplayer Client
Computer Networks Final Project
"""

import pygame
import sys
import os
import random
from typing import Optional

# Add parent directory to path so 'client' package is importable
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from client.constants import FPS, FIELD_WIDTH, FIELD_HEIGHT
from client.network.server_connection import ServerConnection
from client.network.p2p_manager import P2PManager
from client.game.game_state import GameState
from client.ui.splash_screen import SplashScreen
from client.ui.login_screen import LoginScreen
from client.ui.lobby_screen import LobbyScreen
from client.ui.game_screen import GameScreen


class SoccerStarsClient:
    """Main client application."""

    def __init__(self):
        # Initialize Pygame
        pygame.init()
        pygame.display.set_caption("Soccer Stars")

        # Screen setup - slightly larger than field to fit UI
        self.screen_width = FIELD_WIDTH + 100
        self.screen_height = FIELD_HEIGHT + 180
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))

        self.clock = pygame.time.Clock()
        self.running = True

        # Network
        self.server = ServerConnection()

        # Choose a random UDP port for P2P
        self.my_udp_port = random.randint(6000, 6999)
        self.p2p: Optional[P2PManager] = None

        # Game state
        self.game_state = GameState()

        # Screens
        self.splash_screen = SplashScreen(self.screen, self.server)
        self.login_screen = LoginScreen(self.screen, self.server)
        self.lobby_screen = LobbyScreen(self.screen, self.server)
        self.game_screen: Optional[GameScreen] = None

        # Current screen
        self.current_screen = "splash"

    def run(self) -> None:
        """Main game loop."""
        # Start connection process
        self.splash_screen.start_connection()

        while self.running:
            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                    continue

                # Pass event to current screen
                next_screen = self._handle_event(event)
                if next_screen:
                    self._switch_screen(next_screen)

            # Update current screen
            next_screen = self._update()
            if next_screen:
                self._switch_screen(next_screen)

            # Process server messages
            if self.server.connected:
                self.server.process_messages()

            # Draw
            self._draw()

            # Cap framerate
            self.clock.tick(FPS)

        # Cleanup
        self._cleanup()

    def _handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Handle event for current screen."""
        if self.current_screen == "splash":
            return self.splash_screen.handle_event(event)
        elif self.current_screen == "login":
            return self.login_screen.handle_event(event)
        elif self.current_screen == "lobby":
            return self.lobby_screen.handle_event(event)
        elif self.current_screen == "game" and self.game_screen:
            return self.game_screen.handle_event(event)
        return None

    def _update(self) -> Optional[str]:
        """Update current screen."""
        if self.current_screen == "splash":
            return self.splash_screen.update()
        elif self.current_screen == "login":
            return self.login_screen.update()
        elif self.current_screen == "lobby":
            return self.lobby_screen.update()
        elif self.current_screen == "game" and self.game_screen:
            return self.game_screen.update()
        return None

    def _draw(self) -> None:
        """Draw current screen."""
        if self.current_screen == "splash":
            self.splash_screen.draw()
        elif self.current_screen == "login":
            self.login_screen.draw()
        elif self.current_screen == "lobby":
            self.lobby_screen.draw()
        elif self.current_screen == "game" and self.game_screen:
            self.game_screen.draw()

        pygame.display.flip()

    def _switch_screen(self, screen_name: str) -> None:
        """Switch to a different screen."""
        print(f"Switching to screen: {screen_name}")

        if screen_name == "login":
            self.current_screen = "login"

        elif screen_name == "lobby":
            self.current_screen = "lobby"
            self.lobby_screen.set_udp_port(self.my_udp_port)
            self.lobby_screen.enter()

        elif screen_name == "game":
            # Get game start data from lobby
            game_data = self.lobby_screen.get_game_start_data()
            if game_data:
                # Create P2P manager
                self.p2p = P2PManager(self.my_udp_port)

                # Create game screen
                self.game_screen = GameScreen(
                    self.screen,
                    self.game_state,
                    self.server,
                    self.p2p
                )

                # Start the game
                self.game_screen.start_game(game_data)
                self.current_screen = "game"

                # Change UDP port for next game
                self.my_udp_port = random.randint(6000, 6999)

    def _cleanup(self) -> None:
        """Cleanup on exit."""
        if self.p2p:
            self.p2p.stop()
        if self.server.connected:
            self.server.logout()
            self.server.disconnect()
        pygame.quit()


def main():
    """Entry point."""
    client = SoccerStarsClient()
    try:
        client.run()
    except KeyboardInterrupt:
        pass
    finally:
        pygame.quit()
        sys.exit(0)


if __name__ == "__main__":
    main()
