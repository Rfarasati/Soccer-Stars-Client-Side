import pygame
import math
import time
from typing import Optional, Tuple
from client.game import GameState
from client.constants import (
    FIELD_WIDTH, FIELD_HEIGHT, GOAL_TOP, GOAL_WIDTH, GOAL_HEIGHT,
    WHITE, BLACK, BLUE, RED, GREEN, GRAY, YELLOW, SHOT_POWER
)

class GameScreen:

    def __init__(self, screen: pygame.Surface, game_state: GameState,
                 server_connection, p2p_manager):
        self.screen = screen
        self.game_state = game_state
        self.server = server_connection
        self.p2p = p2p_manager
        self.width, self.height = screen.get_size()

        # Calculate field offset to center it
        self.field_offset_x = (self.width - FIELD_WIDTH) // 2
        self.field_offset_y = 80  # Leave room for scoreboard

        # Fonts
        self.score_font = pygame.font.Font(None, 48)
        self.name_font = pygame.font.Font(None, 32)
        self.info_font = pygame.font.Font(None, 28)
        self.big_font = pygame.font.Font(None, 72)
        self.button_font = pygame.font.Font(None, 32)

        # Shot mechanics
        self.selected_piece_id: Optional[int] = None
        self.aiming = False
        self.aim_start: Optional[Tuple[int, int]] = None
        self.aim_current: Optional[Tuple[int, int]] = None

        # Game state
        self.physics_running = False
        self.waiting_for_turn_end = False
        self.my_shot_this_turn = False  # Did I shoot this turn?

        # Animations
        self.goal_animation_time: Optional[float] = None
        self.goal_scored_by: Optional[str] = None  # "blue" or "red"

        # Game over
        self.show_game_over = False
        self.show_rematch_popup = False
        self.rematch_requested = False
        self.opponent_wants_rematch = False

        # Buttons for game over screen
        self.rematch_button = pygame.Rect(self.width // 2 - 160, 400, 140, 50)
        self.lobby_button = pygame.Rect(self.width // 2 + 20, 400, 140, 50)

        # State tracking
        self.handshake_received = False
        self.handshake_sent = False
        self.game_ready = False
        self.last_received_hash: Optional[str] = None

        # Return to lobby flag
        self.return_to_lobby = False

    def start_game(self, game_data: dict) -> None:
        self.game_state.initialize(
            game_session_id=game_data["gameSessionId"],
            my_username=self.server.username,
            opponent_username=game_data["opponentUsername"],
            is_initiator=game_data["isInitiator"]
        )

        # Start P2P
        self.p2p.start(
            game_session_id=game_data["gameSessionId"],
            username=self.server.username,
            opponent_ip=game_data["opponentIp"],
            opponent_port=game_data["opponentUdpPort"]
        )

        # Register P2P handlers
        self._register_p2p_handlers()

        # Reset state
        self.selected_piece_id = None
        self.aiming = False
        self.physics_running = False
        self.waiting_for_turn_end = False
        self.my_shot_this_turn = False
        self.show_game_over = False
        self.show_rematch_popup = False
        self.rematch_requested = False
        self.opponent_wants_rematch = False
        self.return_to_lobby = False
        self.goal_animation_time = None
        self.handshake_received = False
        self.handshake_sent = False
        self.game_ready = False

        # Send handshake
        self.p2p.send_handshake()
        self.handshake_sent = True

    def _register_p2p_handlers(self) -> None:
        self.p2p.register_handler("HANDSHAKE", self._on_handshake)
        self.p2p.register_handler("HANDSHAKE_ACK", self._on_handshake_ack)
        self.p2p.register_handler("SHOT", self._on_shot)
        self.p2p.register_handler("TURN_END", self._on_turn_end)
        self.p2p.register_handler("GOAL_SCORED", self._on_goal_scored)
        self.p2p.register_handler("GAME_OVER", self._on_game_over)
        self.p2p.register_handler("STATE_SYNC", self._on_state_sync)
        self.p2p.register_handler("STATE_REQUEST", self._on_state_request)
        self.p2p.register_handler("HEARTBEAT", self._on_heartbeat)
        self.p2p.register_handler("REMATCH_REQUEST", self._on_rematch_request)
        self.p2p.register_handler("REMATCH_RESPONSE", self._on_rematch_response)
        self.p2p.register_handler("RETURN_TO_LOBBY", self._on_return_to_lobby)

    def _on_handshake(self, message: dict) -> None:
        self.handshake_received = True
        self.p2p.send_handshake_ack(ready=True)
        if self.handshake_sent:
            self.game_ready = True

    def _on_handshake_ack(self, message: dict) -> None:
        self.handshake_received = True
        self.game_ready = True

    def _on_shot(self, message: dict) -> None:
        if self.game_state.is_my_turn():
            # Ignore if it's my turn
            return

        piece_id = message.get("pieceId", 0)
        angle = message.get("angle", 0)
        power = message.get("power", SHOT_POWER)
        turn_number = message.get("turnNumber", 0)

        # Verify turn number
        if turn_number != self.game_state.current_turn:
            return

        # Apply the shot
        self.game_state.apply_shot(piece_id, angle, power)
        self.physics_running = True

        # Send ACK
        self.p2p.send_shot_ack(turn_number)

    def _on_turn_end(self, message: dict) -> None:
        turn_number = message.get("turnNumber", 0)
        state_hash = message.get("stateHash", "")

        self.last_received_hash = state_hash

        # Compare hashes
        my_hash = self.game_state.compute_state_hash()
        hash_match = (my_hash == state_hash)

        # Send ACK
        self.p2p.send_turn_end_ack(turn_number, hash_match)

        if not hash_match:
            # Request state sync
            self.p2p.send_state_request()

    def _on_goal_scored(self, message: dict) -> None:
        blue_scored = message.get("blueScored", False)

        # Set scores directly from message (authoritative)
        self.game_state.blue_score = message.get("blueScore", self.game_state.blue_score)
        self.game_state.red_score = message.get("redScore", self.game_state.red_score)

        # Check for game over (first to 2)
        from client.constants import GOALS_TO_WIN
        if self.game_state.blue_score >= GOALS_TO_WIN:
            self.game_state.game_over = True
            self.game_state.winner_username = (
                self.game_state.my_username if self.game_state.is_blue
                else self.game_state.opponent_username
            )
        elif self.game_state.red_score >= GOALS_TO_WIN:
            self.game_state.game_over = True
            self.game_state.winner_username = (
                self.game_state.opponent_username if self.game_state.is_blue
                else self.game_state.my_username
            )

        # Reset positions if game not over
        if not self.game_state.game_over:
            self.game_state._reset_positions()

        # After goal, team that was scored against kicks off
        self.game_state.is_blues_turn = not blue_scored
        self.game_state.current_turn += 1

        # Stop any ongoing physics and reset turn state
        self.physics_running = False
        self.my_shot_this_turn = False

        # Trigger goal animation
        self.goal_scored_by = "blue" if blue_scored else "red"
        self.goal_animation_time = time.time()

    def _on_game_over(self, message: dict) -> None:
        self.game_state.winner_username = message.get("winnerUsername")
        self.game_state.game_over = True
        self.show_game_over = True
        self.p2p.send_game_over_ack()

        # Report result to server
        winner_score = message.get("winnerScore", 2)
        loser_score = message.get("loserScore", 0)
        self.server.report_game_result(
            self.game_state.game_session_id,
            self.game_state.winner_username,
            winner_score,
            loser_score
        )

    def _on_state_sync(self, message: dict) -> None:
        self.game_state.apply_sync(message, smooth=True)

    def _on_state_request(self, message: dict) -> None:
        self.p2p.send_state_sync(self.game_state.to_sync_dict())

    def _on_heartbeat(self, message: dict) -> None:
        self.p2p.send_heartbeat_ack()

    def _on_rematch_request(self, message: dict) -> None:
        self.opponent_wants_rematch = True
        if self.rematch_requested:
            # Both want rematch - start new game
            self._start_rematch()

    def _on_rematch_response(self, message: dict) -> None:
        if message.get("accepted"):
            self._start_rematch()
        else:
            self.return_to_lobby = True

    def _on_return_to_lobby(self, message: dict) -> None:
        self.return_to_lobby = True

    def _start_rematch(self) -> None:
        self.game_state.reset_for_rematch()
        self.selected_piece_id = None
        self.aiming = False
        self.physics_running = False
        self.waiting_for_turn_end = False
        self.my_shot_this_turn = False
        self.show_game_over = False
        self.show_rematch_popup = False
        self.rematch_requested = False
        self.opponent_wants_rematch = False
        self.goal_animation_time = None

    def _screen_to_field(self, screen_pos: Tuple[int, int]) -> Tuple[float, float]:
        return (
            screen_pos[0] - self.field_offset_x,
            screen_pos[1] - self.field_offset_y
        )

    def _field_to_screen(self, field_pos: Tuple[float, float]) -> Tuple[int, int]:
        return (
            int(field_pos[0] + self.field_offset_x),
            int(field_pos[1] + self.field_offset_y)
        )

    def _get_piece_at(self, field_x: float, field_y: float) -> Optional[int]:
        if not self.game_state.is_my_turn():
            return None

        my_pieces = self.game_state.get_my_pieces()
        for piece in my_pieces:
            dx = field_x - piece.x
            dy = field_y - piece.y
            if math.sqrt(dx*dx + dy*dy) <= piece.radius:
                return piece.piece_id
        return None

    def _execute_shot(self) -> None:
        if self.selected_piece_id is None or not self.aim_start or not self.aim_current:
            return

        # Calculate shot direction (opposite of drag)
        dx = self.aim_start[0] - self.aim_current[0]
        dy = self.aim_start[1] - self.aim_current[1]

        # Minimum drag distance
        distance = math.sqrt(dx*dx + dy*dy)
        if distance < 10:
            self.aiming = False
            self.selected_piece_id = None
            return

        angle = math.atan2(dy, dx)

        # Apply locally
        self.game_state.apply_shot(self.selected_piece_id, angle, SHOT_POWER)
        self.physics_running = True
        self.my_shot_this_turn = True

        # Send to opponent
        self.p2p.send_shot(
            self.selected_piece_id,
            angle,
            SHOT_POWER,
            self.game_state.current_turn
        )

        # Reset shot state
        self.aiming = False
        self.selected_piece_id = None
        self.aim_start = None
        self.aim_current = None

    def update(self) -> Optional[str]:
        """Update game state. Returns 'lobby' to return to lobby."""
        if self.return_to_lobby:
            self.p2p.stop()
            return "lobby"

        # Process P2P messages
        self.p2p.process_messages()

        # Update goal animation
        if self.goal_animation_time:
            if time.time() - self.goal_animation_time > 2.0:
                self.goal_animation_time = None
                self.goal_scored_by = None
                # Check for game over after goal
                if self.game_state.game_over:
                    self.show_game_over = True

        # Update physics
        if self.physics_running and not self.goal_animation_time:
            goal_event = self.game_state.update_physics()

            # Only the shooter (my_shot_this_turn) should detect and broadcast goals
            # The receiver will get GOAL_SCORED via P2P message
            if goal_event and self.my_shot_this_turn:
                # Goal scored!
                blue_scored = (goal_event == "blue_scored")
                self.game_state.handle_goal(blue_scored)

                # After goal, team that was scored against kicks off
                # If blue scored, red kicks off (is_blues_turn = False)
                # If red scored, blue kicks off (is_blues_turn = True)
                self.game_state.is_blues_turn = not blue_scored
                self.game_state.current_turn += 1

                # Notify opponent
                self.p2p.send_goal_scored(
                    blue_scored,
                    self.game_state.blue_score,
                    self.game_state.red_score
                )

                # Show animation
                self.goal_scored_by = "blue" if blue_scored else "red"
                self.goal_animation_time = time.time()
                self.physics_running = False
                self.my_shot_this_turn = False

                # Check for game over
                if self.game_state.game_over:
                    self.p2p.send_game_over(
                        self.game_state.winner_username,
                        self.game_state.get_winner_score(),
                        self.game_state.get_loser_score()
                    )
                    self.server.report_game_result(
                        self.game_state.game_session_id,
                        self.game_state.winner_username,
                        self.game_state.get_winner_score(),
                        self.game_state.get_loser_score()
                    )

            elif not self.game_state.is_physics_running():
                # Physics stopped
                self.physics_running = False

                # If I shot this turn, send turn end
                if self.my_shot_this_turn:
                    state_hash = self.game_state.compute_state_hash()
                    self.p2p.send_turn_end(self.game_state.current_turn, state_hash)
                    self.game_state.end_turn()
                    self.my_shot_this_turn = False

                # If opponent shot, just wait for their TURN_END
                # (turn switch happens when we receive and process TURN_END)
                elif not self.game_state.is_my_turn():
                    # Opponent's physics finished locally, end their turn
                    self.game_state.end_turn()

        return None

    def handle_event(self, event: pygame.event.Event) -> Optional[str]:
        """Handle input events."""
        # Game over screen
        if self.show_game_over:
            if event.type == pygame.MOUSEBUTTONDOWN:
                if self.rematch_button.collidepoint(event.pos):
                    self.rematch_requested = True
                    self.p2p.send_rematch_request()
                    if self.opponent_wants_rematch:
                        self._start_rematch()
                elif self.lobby_button.collidepoint(event.pos):
                    self.p2p.send_return_to_lobby()
                    self.p2p.stop()
                    return "lobby"
            return None

        # Goal animation - block input
        if self.goal_animation_time:
            return None

        # Not ready yet
        if not self.game_ready:
            return None

        # Not my turn or physics running
        if not self.game_state.is_my_turn() or self.physics_running:
            return None

        # Shot mechanics
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            field_pos = self._screen_to_field(event.pos)
            piece_id = self._get_piece_at(*field_pos)
            if piece_id is not None:
                self.selected_piece_id = piece_id
                self.aiming = True
                self.aim_start = field_pos
                self.aim_current = field_pos

        elif event.type == pygame.MOUSEMOTION and self.aiming:
            self.aim_current = self._screen_to_field(event.pos)

        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and self.aiming:
            self.aim_current = self._screen_to_field(event.pos)
            self._execute_shot()

        return None

    def draw(self) -> None:
        """Draw the game screen."""
        self.screen.fill((20, 50, 20))

        # Draw scoreboard
        self._draw_scoreboard()

        # Draw field
        self._draw_field()

        # Draw pieces and ball
        self._draw_pieces()
        self._draw_ball()

        # Draw aiming line
        if self.aiming and self.selected_piece_id is not None:
            self._draw_aim_line()

        # Draw turn indicator
        self._draw_turn_indicator()

        # Draw goal animation
        if self.goal_animation_time:
            self._draw_goal_animation()

        # Draw game over screen
        if self.show_game_over:
            self._draw_game_over()

        # Draw waiting message if not ready
        if not self.game_ready:
            self._draw_waiting()

    def _draw_scoreboard(self) -> None:
        """Draw the scoreboard."""
        # Blue player (left)
        blue_name = self.game_state.my_username if self.game_state.is_blue else self.game_state.opponent_username
        blue_text = self.name_font.render(blue_name, True, BLUE)
        self.screen.blit(blue_text, (50, 20))

        blue_score = self.score_font.render(str(self.game_state.blue_score), True, BLUE)
        self.screen.blit(blue_score, (50, 45))

        # Red player (right)
        red_name = self.game_state.opponent_username if self.game_state.is_blue else self.game_state.my_username
        red_text = self.name_font.render(red_name, True, RED)
        red_rect = red_text.get_rect(right=self.width - 50, top=20)
        self.screen.blit(red_text, red_rect)

        red_score = self.score_font.render(str(self.game_state.red_score), True, RED)
        red_score_rect = red_score.get_rect(right=self.width - 50, top=45)
        self.screen.blit(red_score, red_score_rect)

        # VS
        vs_text = self.name_font.render("VS", True, WHITE)
        vs_rect = vs_text.get_rect(center=(self.width // 2, 40))
        self.screen.blit(vs_text, vs_rect)

    def _draw_field(self) -> None:
        """Draw the playing field."""
        # Field background
        field_rect = pygame.Rect(
            self.field_offset_x, self.field_offset_y,
            FIELD_WIDTH, FIELD_HEIGHT
        )
        pygame.draw.rect(self.screen, GREEN, field_rect)

        # Field border
        pygame.draw.rect(self.screen, WHITE, field_rect, 3)

        # Center line
        center_x = self.field_offset_x + FIELD_WIDTH // 2
        pygame.draw.line(self.screen, WHITE,
                        (center_x, self.field_offset_y),
                        (center_x, self.field_offset_y + FIELD_HEIGHT), 2)

        # Center circle
        pygame.draw.circle(self.screen, WHITE,
                          (center_x, self.field_offset_y + FIELD_HEIGHT // 2),
                          70, 2)

        # Goals
        # Left goal (red scores here)
        left_goal = pygame.Rect(
            self.field_offset_x - GOAL_WIDTH,
            self.field_offset_y + GOAL_TOP,
            GOAL_WIDTH, GOAL_HEIGHT
        )
        pygame.draw.rect(self.screen, (200, 200, 200), left_goal)
        pygame.draw.rect(self.screen, WHITE, left_goal, 2)

        # Right goal (blue scores here)
        right_goal = pygame.Rect(
            self.field_offset_x + FIELD_WIDTH,
            self.field_offset_y + GOAL_TOP,
            GOAL_WIDTH, GOAL_HEIGHT
        )
        pygame.draw.rect(self.screen, (200, 200, 200), right_goal)
        pygame.draw.rect(self.screen, WHITE, right_goal, 2)

    def _draw_pieces(self) -> None:
        """Draw all pieces."""
        # Draw blue pieces
        for piece in self.game_state.blue_pieces:
            screen_pos = self._field_to_screen((piece.x, piece.y))
            color = (70, 130, 230) if piece.piece_id == self.selected_piece_id and self.game_state.is_blue else BLUE
            pygame.draw.circle(self.screen, color, screen_pos, int(piece.radius))
            pygame.draw.circle(self.screen, WHITE, screen_pos, int(piece.radius), 2)

        # Draw red pieces
        for piece in self.game_state.red_pieces:
            screen_pos = self._field_to_screen((piece.x, piece.y))
            color = (230, 70, 70) if piece.piece_id == self.selected_piece_id and not self.game_state.is_blue else RED
            pygame.draw.circle(self.screen, color, screen_pos, int(piece.radius))
            pygame.draw.circle(self.screen, WHITE, screen_pos, int(piece.radius), 2)

    def _draw_ball(self) -> None:
        """Draw the ball."""
        ball = self.game_state.ball
        screen_pos = self._field_to_screen((ball.x, ball.y))
        pygame.draw.circle(self.screen, WHITE, screen_pos, int(ball.radius))
        pygame.draw.circle(self.screen, BLACK, screen_pos, int(ball.radius), 2)

    def _draw_aim_line(self) -> None:
        """Draw the aiming line and power indicator."""
        if not self.aim_start or not self.aim_current:
            return

        my_pieces = self.game_state.get_my_pieces()
        if self.selected_piece_id is None or self.selected_piece_id >= len(my_pieces):
            return

        piece = my_pieces[self.selected_piece_id]
        piece_screen = self._field_to_screen((piece.x, piece.y))

        # Direction is opposite of drag
        dx = self.aim_start[0] - self.aim_current[0]
        dy = self.aim_start[1] - self.aim_current[1]
        distance = math.sqrt(dx*dx + dy*dy)

        if distance < 5:
            return

        # Normalize and scale for display
        max_line_length = 100
        line_length = min(distance, max_line_length)
        nx = dx / distance
        ny = dy / distance

        end_x = piece_screen[0] + nx * line_length
        end_y = piece_screen[1] + ny * line_length

        # Draw direction line
        pygame.draw.line(self.screen, YELLOW, piece_screen, (int(end_x), int(end_y)), 3)

        # Draw arrowhead
        arrow_size = 10
        angle = math.atan2(ny, nx)
        arrow_x1 = end_x - arrow_size * math.cos(angle - 0.5)
        arrow_y1 = end_y - arrow_size * math.sin(angle - 0.5)
        arrow_x2 = end_x - arrow_size * math.cos(angle + 0.5)
        arrow_y2 = end_y - arrow_size * math.sin(angle + 0.5)
        pygame.draw.polygon(self.screen, YELLOW, [
            (int(end_x), int(end_y)),
            (int(arrow_x1), int(arrow_y1)),
            (int(arrow_x2), int(arrow_y2))
        ])

        # Power indicator
        power_ratio = min(distance / max_line_length, 1.0)
        power_text = self.info_font.render(f"Power: {int(power_ratio * 100)}%", True, YELLOW)
        self.screen.blit(power_text, (piece_screen[0] - 40, piece_screen[1] - 50))

    def _draw_turn_indicator(self) -> None:
        """Draw whose turn it is."""
        if self.game_state.game_over:
            return

        if self.physics_running:
            text = "Simulating..."
            color = YELLOW
        elif self.game_state.is_my_turn():
            text = "Your Turn - Click and drag a piece to shoot!"
            color = (100, 255, 100)
        else:
            text = "Opponent's Turn"
            color = (255, 200, 100)

        indicator = self.info_font.render(text, True, color)
        indicator_rect = indicator.get_rect(center=(self.width // 2, self.height - 30))
        self.screen.blit(indicator, indicator_rect)

    def _draw_goal_animation(self) -> None:
        """Draw goal celebration."""
        # Overlay
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 100))
        self.screen.blit(overlay, (0, 0))

        # Goal text
        color = BLUE if self.goal_scored_by == "blue" else RED
        scorer = "Blue" if self.goal_scored_by == "blue" else "Red"
        goal_text = self.big_font.render(f"GOAL! {scorer} Scores!", True, color)
        goal_rect = goal_text.get_rect(center=(self.width // 2, self.height // 2))
        self.screen.blit(goal_text, goal_rect)

    def _draw_game_over(self) -> None:
        """Draw game over screen."""
        # Overlay
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 200))
        self.screen.blit(overlay, (0, 0))

        # Winner text
        if self.game_state.winner_username == self.game_state.my_username:
            result_text = "You Win!"
            result_color = (100, 255, 100)
        else:
            result_text = "You Lose!"
            result_color = (255, 100, 100)

        result = self.big_font.render(result_text, True, result_color)
        result_rect = result.get_rect(center=(self.width // 2, 200))
        self.screen.blit(result, result_rect)

        # Final score
        score_text = f"{self.game_state.blue_score} - {self.game_state.red_score}"
        score = self.score_font.render(score_text, True, WHITE)
        score_rect = score.get_rect(center=(self.width // 2, 280))
        self.screen.blit(score, score_rect)

        # Status text
        if self.rematch_requested:
            status = "Waiting for opponent..."
        elif self.opponent_wants_rematch:
            status = "Opponent wants a rematch!"
        else:
            status = ""

        if status:
            status_surface = self.info_font.render(status, True, YELLOW)
            status_rect = status_surface.get_rect(center=(self.width // 2, 350))
            self.screen.blit(status_surface, status_rect)

        # Buttons
        rematch_color = GRAY if self.rematch_requested else BLUE
        pygame.draw.rect(self.screen, rematch_color, self.rematch_button, border_radius=8)
        rematch_text = self.button_font.render("Rematch", True, WHITE)
        rematch_rect = rematch_text.get_rect(center=self.rematch_button.center)
        self.screen.blit(rematch_text, rematch_rect)

        pygame.draw.rect(self.screen, (150, 50, 50), self.lobby_button, border_radius=8)
        lobby_text = self.button_font.render("Lobby", True, WHITE)
        lobby_rect = lobby_text.get_rect(center=self.lobby_button.center)
        self.screen.blit(lobby_text, lobby_rect)

    def _draw_waiting(self) -> None:
        """Draw waiting for opponent message."""
        overlay = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        waiting = self.name_font.render("Waiting for opponent to connect...", True, WHITE)
        waiting_rect = waiting.get_rect(center=(self.width // 2, self.height // 2))
        self.screen.blit(waiting, waiting_rect)
