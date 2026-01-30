# Network
SERVER_HOST = "localhost"
SERVER_PORT = 5001

# Field dimensions
FIELD_WIDTH = 800
FIELD_HEIGHT = 500
GOAL_WIDTH = 20
GOAL_HEIGHT = 120
GOAL_TOP = (FIELD_HEIGHT - GOAL_HEIGHT) // 2  # 190
GOAL_BOTTOM = GOAL_TOP + GOAL_HEIGHT  # 310

# Pieces
PIECES_PER_PLAYER = 5
PIECE_RADIUS = 25
BALL_RADIUS = 15

# Physics
FRICTION = 0.98  # Velocity multiplier per frame
MIN_VELOCITY = 0.1  # Stop threshold
SHOT_POWER = 20.0  # Default shot power
RESTITUTION = 0.8  # Bounce coefficient

# Game rules
GOALS_TO_WIN = 1
FPS = 60

# Initial positions
BLUE_POSITIONS = [
    (150, 250),  # Goalkeeper
    (250, 150),  # Defender top
    (250, 350),  # Defender bottom
    (350, 200),  # Midfielder top
    (350, 300),  # Midfielder bottom
]

RED_POSITIONS = [
    (650, 250),  # Goalkeeper
    (550, 150),  # Defender top
    (550, 350),  # Defender bottom
    (450, 200),  # Midfielder top
    (450, 300),  # Midfielder bottom
]

BALL_POSITION = (400, 250)  # Center of field

# Colors
BLUE = (50, 100, 200)
RED = (200, 50, 50)
WHITE = (255, 255, 255)
GREEN = (34, 139, 34)
DARK_GREEN = (0, 100, 0)
BLACK = (0, 0, 0)
YELLOW = (255, 255, 0)
GRAY = (128, 128, 128)
LIGHT_GRAY = (200, 200, 200)

# P2P
HEARTBEAT_INTERVAL = 2.0  # seconds
HEARTBEAT_TIMEOUT = 10.0  # seconds
ACK_TIMEOUT = 0.5  # seconds
MAX_RETRIES = 3
