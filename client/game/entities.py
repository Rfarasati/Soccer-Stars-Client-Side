import math
from dataclasses import dataclass

@dataclass
class GameObject:
    """Base class for all game objects (pieces and ball)."""
    x: float
    y: float
    radius: float
    vx: float = 0.0
    vy: float = 0.0

    def is_moving(self, min_velocity: float = 0.1) -> bool:
        """Check if object is still moving."""
        return abs(self.vx) >= min_velocity or abs(self.vy) >= min_velocity

    def distance_to(self, other: 'GameObject') -> float:
        """Calculate distance to another object."""
        dx = other.x - self.x
        dy = other.y - self.y
        return math.sqrt(dx * dx + dy * dy)

    def collides_with(self, other: 'GameObject') -> bool:
        """Check if this object collides with another."""
        return self.distance_to(other) < (self.radius + other.radius)

    def to_dict(self) -> dict:
        """Convert to dictionary for network serialization."""
        return {
            "x": round(self.x, 2),
            "y": round(self.y, 2),
            "vx": round(self.vx, 2),
            "vy": round(self.vy, 2)
        }

    def from_dict(self, data: dict) -> None:
        """Update from dictionary."""
        self.x = data["x"]
        self.y = data["y"]
        self.vx = data.get("vx", 0.0)
        self.vy = data.get("vy", 0.0)


@dataclass
class Piece(GameObject):
    """A player's piece."""
    piece_id: int = 0
    team: str = "blue"  # "blue" or "red"

    def apply_shot(self, angle: float, power: float) -> None:
        """Apply a shot to this piece."""
        self.vx = math.cos(angle) * power
        self.vy = math.sin(angle) * power


@dataclass
class Ball(GameObject):
    """The game ball."""
    pass


def create_pieces(team: str, positions: list, radius: float) -> list:
    """Create a list of pieces for a team."""
    pieces = []
    for i, (x, y) in enumerate(positions):
        piece = Piece(
            x=float(x),
            y=float(y),
            radius=radius,
            piece_id=i,
            team=team
        )
        pieces.append(piece)
    return pieces


def create_ball(position: tuple, radius: float) -> Ball:
    """Create the game ball."""
    return Ball(
        x=float(position[0]),
        y=float(position[1]),
        radius=radius
    )
