import socket
import json
import threading
from typing import Optional, Callable, Dict
from queue import Queue
from client.constants import SERVER_HOST, SERVER_PORT


class ServerConnection:

    def __init__(self):
        self.socket: Optional[socket.socket] = None
        self.connected = False
        self.session_id: Optional[str] = None
        self.username: Optional[str] = None

        # Message handlers by type
        self.handlers: Dict[str, Callable] = {}

        # Incoming message queue for main thread
        self.message_queue: Queue = Queue()

        # Receiver thread
        self._receiver_thread: Optional[threading.Thread] = None
        self._running = False
        self._lock = threading.Lock()

        # Buffer for incomplete messages
        self._buffer = ""

    def connect(self, host: str = SERVER_HOST, port: int = SERVER_PORT) -> bool:
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10.0)
            self.socket.connect((host, port))
            self.socket.settimeout(None)
            self.connected = True

            # Start receiver thread
            self._running = True
            self._receiver_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self._receiver_thread.start()

            return True
        except Exception as e:
            print(f"Connection failed: {e}")
            self.connected = False
            return False

    def disconnect(self) -> None:
        self._running = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self.connected = False
        self.socket = None

    def send(self, message: dict) -> bool:
        """Send a JSON message to the server."""
        if not self.connected or not self.socket:
            return False

        try:
            data = json.dumps(message) + "\n"
            with self._lock:
                self.socket.sendall(data.encode('utf-8'))
            return True
        except Exception as e:
            print(f"Send failed: {e}")
            self.connected = False
            return False

    def register_handler(self, message_type: str, handler: Callable) -> None:
        self.handlers[message_type] = handler

    def _receive_loop(self) -> None:
        """Background thread to receive messages."""
        while self._running and self.connected:
            try:
                if not self.socket:
                    break

                self.socket.settimeout(1.0)
                try:
                    data = self.socket.recv(4096)
                except socket.timeout:
                    continue

                if not data:
                    self.connected = False
                    break

                self._buffer += data.decode('utf-8')

                # Process complete messages (newline-delimited)
                while '\n' in self._buffer:
                    line, self._buffer = self._buffer.split('\n', 1)
                    line = line.strip()
                    if line:
                        try:
                            message = json.loads(line)
                            self._handle_message(message)
                        except json.JSONDecodeError as e:
                            print(f"Invalid JSON received: {e}")

            except Exception as e:
                if self._running:
                    print(f"Receive error: {e}")
                self.connected = False
                break

    def _handle_message(self, message: dict) -> None:
        """Handle an incoming message."""
        msg_type = message.get("type", "")

        # Add to queue for main thread processing
        self.message_queue.put(message)

        # Call registered handler if exists
        if msg_type in self.handlers:
            try:
                self.handlers[msg_type](message)
            except Exception as e:
                print(f"Handler error for {msg_type}: {e}")

    def process_messages(self) -> None:
        """Process pending messages from queue (call from main thread)."""
        while not self.message_queue.empty():
            message = self.message_queue.get_nowait()
            msg_type = message.get("type", "")
            if msg_type in self.handlers:
                try:
                    self.handlers[msg_type](message)
                except Exception as e:
                    print(f"Handler error for {msg_type}: {e}")

    # Convenience methods for common operations

    def ping(self) -> bool:
        return self.send({"type": "PING"})

    def register(self, username: str, email: str, password: str) -> bool:
        return self.send({
            "type": "REGISTER_REQUEST",
            "username": username,
            "email": email,
            "password": password
        })

    def login(self, username: str, password: str) -> bool:
        return self.send({
            "type": "LOGIN_REQUEST",
            "username": username,
            "password": password
        })

    def logout(self) -> bool:
        if self.session_id:
            return self.send({
                "type": "LOGOUT_REQUEST",
                "sessionId": self.session_id
            })
        return False

    def get_online_users(self) -> bool:
        if self.session_id:
            return self.send({
                "type": "GET_ONLINE_USERS",
                "sessionId": self.session_id
            })
        return False

    def invite_player(self, target_username: str, udp_port: int) -> bool:
        if self.session_id:
            return self.send({
                "type": "GAME_INVITE",
                "sessionId": self.session_id,
                "targetUsername": target_username,
                "udpPort": udp_port
            })
        return False

    def respond_to_invite(self, invite_id: str, accepted: bool, udp_port: int) -> bool:
        return self.send({
            "type": "GAME_INVITE_RESPONSE",
            "inviteId": invite_id,
            "accepted": accepted,
            "udpPort": udp_port
        })

    def report_game_result(self, game_session_id: str, winner_username: str,
                           winner_score: int, loser_score: int) -> bool:
        if self.session_id:
            return self.send({
                "type": "GAME_RESULT",
                "sessionId": self.session_id,
                "gameSessionId": game_session_id,
                "winnerUsername": winner_username,
                "winnerScore": winner_score,
                "loserScore": loser_score
            })
        return False
