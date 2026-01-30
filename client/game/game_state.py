import hashlib
from typing import Optional, Callable
from client.constants import (
    BLUE_POSITIONS, RED_POSITIONS, BALL_POSITION,
    PIECE_RADIUS, BALL_RADIUS, GOALS_TO_WIN
)
from client.game.entities import create_pieces, create_ball
from client.game.game_engine import PhysicsEngine


class GameState:

    def __init__(self):
        self.blue_pieces = []
        self.red_pieces = []
        self.ball = None
        self.physics = None

        self.blue_score = 0
        self.red_score = 0
        self.current_turn = 1
        self.is_blues_turn = True

        self.game_session_id = None
        self.my_username = None
        self.opponent_username = None
        self.is_blue = True  # Am I playing as blue?

        self.game_over = False
        self.winner_username = None

        # Callbacks
        self.on_goal_scored: Optional[Callable] = None
        self.on_game_over: Optional[Callable] = None
        self.on_turn_end: Optional[Callable] = None

    def initialize(self, game_session_id: str, my_username: str,
                   opponent_username: str, is_initiator: bool) -> None:
        self.game_session_id = game_session_id
        self.my_username = my_username
        self.opponent_username = opponent_username
        self.is_blue = is_initiator  # Initiator is blue

        self.blue_score = 0
        self.red_score = 0
        self.current_turn = 1
        self.is_blues_turn = True  # Blue always goes first
        self.game_over = False
        self.winner_username = None

        self._reset_positions()

    def _reset_positions(self) -> None:
        self.blue_pieces = create_pieces("blue", BLUE_POSITIONS, PIECE_RADIUS)
        self.red_pieces = create_pieces("red", RED_POSITIONS, PIECE_RADIUS)
        self.ball = create_ball(BALL_POSITION, BALL_RADIUS)
        self.physics = PhysicsEngine(self.blue_pieces, self.red_pieces, self.ball)

    def is_my_turn(self) -> bool:
        if self.game_over:
            return False
        if self.is_blue:
            return self.is_blues_turn
        else:
            return not self.is_blues_turn

    def get_my_pieces(self) -> list:
        return self.blue_pieces if self.is_blue else self.red_pieces

    def get_opponent_pieces(self) -> list:
        return self.red_pieces if self.is_blue else self.blue_pieces

    def get_my_team(self) -> str:
        return "blue" if self.is_blue else "red"

    def apply_shot(self, piece_id: int, angle: float, power: float) -> bool:
        team = "blue" if self.is_blues_turn else "red"
        return self.physics.apply_shot(team, piece_id, angle, power)

    def update_physics(self) -> Optional[str]:
        if self.game_over:
            return None
        return self.physics.update()

    def is_physics_running(self) -> bool:
        return not self.physics.is_all_stopped()

    def handle_goal(self, blue_scored: bool) -> None:
        if blue_scored:
            self.blue_score += 1
        else:
            self.red_score += 1

        # Check for game over
        if self.blue_score >= GOALS_TO_WIN:
            self.game_over = True
            self.winner_username = self.my_username if self.is_blue else self.opponent_username
        elif self.red_score >= GOALS_TO_WIN:
            self.game_over = True
            self.winner_username = self.opponent_username if self.is_blue else self.my_username

        # Reset positions after goal
        if not self.game_over:
            self._reset_positions()

    def end_turn(self) -> None:
        self.is_blues_turn = not self.is_blues_turn
        self.current_turn += 1

    def compute_state_hash(self) -> str:
        state = ""
        for piece in self.blue_pieces + self.red_pieces + [self.ball]:
            state += f"{round(piece.x, 1)},{round(piece.y, 1)};"
        return hashlib.md5(state.encode()).hexdigest()[:8]

    def to_sync_dict(self) -> dict:
        return {
            "bluePieces": [p.to_dict() for p in self.blue_pieces],
            "redPieces": [p.to_dict() for p in self.red_pieces],
            "ball": self.ball.to_dict(),
            "blueScore": self.blue_score,
            "redScore": self.red_score,
            "currentTurn": self.current_turn,
            "isBluesTurn": self.is_blues_turn
        }

    def apply_sync(self, data: dict, smooth: bool = True) -> None:
        """Apply a STATE_SYNC from the network."""
        target_blue = data.get("bluePieces", [])
        target_red = data.get("redPieces", [])
        target_ball = data.get("ball", {})

        if smooth:
            # Smooth interpolation (gradual correction)
            lerp_factor = 0.3  # 30% towards target each frame
            for i, piece_data in enumerate(target_blue):
                if i < len(self.blue_pieces):
                    self._lerp_object(self.blue_pieces[i], piece_data, lerp_factor)
            for i, piece_data in enumerate(target_red):
                if i < len(self.red_pieces):
                    self._lerp_object(self.red_pieces[i], piece_data, lerp_factor)
            if target_ball:
                self._lerp_object(self.ball, target_ball, lerp_factor)
        else:
            # Direct application
            for i, piece_data in enumerate(target_blue):
                if i < len(self.blue_pieces):
                    self.blue_pieces[i].from_dict(piece_data)
            for i, piece_data in enumerate(target_red):
                if i < len(self.red_pieces):
                    self.red_pieces[i].from_dict(piece_data)
            if target_ball:
                self.ball.from_dict(target_ball)

        self.blue_score = data.get("blueScore", self.blue_score)
        self.red_score = data.get("redScore", self.red_score)
        self.current_turn = data.get("currentTurn", self.current_turn)
        self.is_blues_turn = data.get("isBluesTurn", self.is_blues_turn)

    def _lerp_object(self, obj, target: dict, factor: float) -> None:
        obj.x += (target["x"] - obj.x) * factor
        obj.y += (target["y"] - obj.y) * factor
        obj.vx = target.get("vx", 0.0)
        obj.vy = target.get("vy", 0.0)

    def get_winner_score(self) -> int:
        if self.winner_username == self.my_username:
            return self.blue_score if self.is_blue else self.red_score
        else:
            return self.red_score if self.is_blue else self.blue_score

    def get_loser_score(self) -> int:
        if self.winner_username == self.my_username:
            return self.red_score if self.is_blue else self.blue_score
        else:
            return self.blue_score if self.is_blue else self.red_score

    def reset_for_rematch(self) -> None:
        self.is_blue = not self.is_blue  # Swap sides
        self.blue_score = 0
        self.red_score = 0
        self.current_turn = 1
        self.is_blues_turn = True
        self.game_over = False
        self.winner_username = None
        self._reset_positions()
