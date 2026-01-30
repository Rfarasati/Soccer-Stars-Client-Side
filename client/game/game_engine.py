import math
from typing import Optional, List
from client.constants import (
    FIELD_WIDTH, FIELD_HEIGHT, GOAL_TOP, GOAL_BOTTOM,
    FRICTION, MIN_VELOCITY, RESTITUTION
)
from client.game.entities import Piece, Ball, GameObject


class PhysicsEngine:

    def __init__(self, blue_pieces: List[Piece], red_pieces: List[Piece], ball: Ball):
        self.blue_pieces = blue_pieces
        self.red_pieces = red_pieces
        self.ball = ball

    def get_all_objects(self) -> List[GameObject]:
        return self.blue_pieces + self.red_pieces + [self.ball]

    def update(self) -> Optional[str]:
        # Update positions and apply friction
        for obj in self.get_all_objects():
            # Apply velocity
            obj.x += obj.vx
            obj.y += obj.vy

            # Apply friction
            obj.vx *= FRICTION
            obj.vy *= FRICTION

            # Stop if very slow
            if abs(obj.vx) < MIN_VELOCITY:
                obj.vx = 0.0
            if abs(obj.vy) < MIN_VELOCITY:
                obj.vy = 0.0

        # Check collisions between pieces
        all_pieces = self.blue_pieces + self.red_pieces
        for i, piece1 in enumerate(all_pieces):
            for piece2 in all_pieces[i + 1:]:
                if piece1.collides_with(piece2):
                    self._resolve_collision(piece1, piece2)

        # Check collisions between pieces and ball
        for piece in all_pieces:
            if piece.collides_with(self.ball):
                self._resolve_collision(piece, self.ball)

        # Check wall collisions for all objects
        for obj in self.get_all_objects():
            self._check_wall_collision(obj)

        # Check for goals (ball only)
        return self._check_goal()

    def _resolve_collision(self, obj1: GameObject, obj2: GameObject) -> None:
        dx = obj2.x - obj1.x
        dy = obj2.y - obj1.y
        distance = math.sqrt(dx * dx + dy * dy)

        if distance == 0:
            # Objects are at exact same position, push apart
            distance = 0.01
            dx = 0.01

        # Normal vector
        nx = dx / distance
        ny = dy / distance

        # Relative velocity
        dvx = obj1.vx - obj2.vx
        dvy = obj1.vy - obj2.vy
        dvn = dvx * nx + dvy * ny

        # Don't resolve if moving apart
        if dvn < 0:
            return

        # Impulse (assuming equal mass)
        impulse = dvn * (1 + RESTITUTION) / 2

        obj1.vx -= impulse * nx
        obj1.vy -= impulse * ny
        obj2.vx += impulse * nx
        obj2.vy += impulse * ny

        # Separate overlapping objects
        overlap = (obj1.radius + obj2.radius) - distance
        if overlap > 0:
            obj1.x -= (overlap / 2 + 0.1) * nx
            obj1.y -= (overlap / 2 + 0.1) * ny
            obj2.x += (overlap / 2 + 0.1) * nx
            obj2.y += (overlap / 2 + 0.1) * ny

    def _check_wall_collision(self, obj: GameObject) -> None:
        # Left wall (but not in goal area for ball)
        if obj.x - obj.radius < 0:
            if obj is not self.ball or not (GOAL_TOP < obj.y < GOAL_BOTTOM):
                obj.x = obj.radius
                obj.vx = -obj.vx * RESTITUTION

        # Right wall (but not in goal area for ball)
        if obj.x + obj.radius > FIELD_WIDTH:
            if obj is not self.ball or not (GOAL_TOP < obj.y < GOAL_BOTTOM):
                obj.x = FIELD_WIDTH - obj.radius
                obj.vx = -obj.vx * RESTITUTION

        # Top wall
        if obj.y - obj.radius < 0:
            obj.y = obj.radius
            obj.vy = -obj.vy * RESTITUTION

        # Bottom wall
        if obj.y + obj.radius > FIELD_HEIGHT:
            obj.y = FIELD_HEIGHT - obj.radius
            obj.vy = -obj.vy * RESTITUTION

    def _check_goal(self) -> Optional[str]:
        # Blue scores (ball enters right goal)
        if self.ball.x > FIELD_WIDTH and GOAL_TOP < self.ball.y < GOAL_BOTTOM:
            return "blue_scored"

        # Red scores (ball enters left goal)
        if self.ball.x < 0 and GOAL_TOP < self.ball.y < GOAL_BOTTOM:
            return "red_scored"

        return None

    def is_all_stopped(self) -> bool:
        for obj in self.get_all_objects():
            if obj.is_moving(MIN_VELOCITY):
                return False
        return True

    def apply_shot(self, team: str, piece_id: int, angle: float, power: float) -> bool:
        pieces = self.blue_pieces if team == "blue" else self.red_pieces
        if 0 <= piece_id < len(pieces):
            pieces[piece_id].apply_shot(angle, power)
            return True
        return False
