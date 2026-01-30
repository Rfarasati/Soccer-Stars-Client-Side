import socket
import json
import threading
import time
from typing import Optional, Callable, Dict, Set
from queue import Queue
from client.constants import HEARTBEAT_INTERVAL, HEARTBEAT_TIMEOUT, ACK_TIMEOUT, MAX_RETRIES


class P2PManager:
    """UDP P2P manager for real-time game communication."""

    def __init__(self, local_port: int):
        self.local_port = local_port
        self.socket: Optional[socket.socket] = None

        # Opponent info
        self.opponent_ip: Optional[str] = None
        self.opponent_port: Optional[int] = None

        # Game session
        self.game_session_id: Optional[str] = None
        self.username: Optional[str] = None

        # Message handling
        self.handlers: Dict[str, Callable] = {}
        self.message_queue: Queue = Queue()

        # Sequence numbers
        self.send_sequence = 0
        self.received_sequences: Set[int] = set()
        self._sequence_lock = threading.Lock()

        # Reliability
        self._pending_acks: Dict[int, dict] = {}  # seq -> message data
        self._pending_ack_lock = threading.Lock()

        # Heartbeat
        self.last_received_time = 0
        self.connected = False

        # Threads
        self._running = False
        self._receiver_thread: Optional[threading.Thread] = None
        self._heartbeat_thread: Optional[threading.Thread] = None
        self._retry_thread: Optional[threading.Thread] = None

    def start(self, game_session_id: str, username: str,
              opponent_ip: str, opponent_port: int) -> bool:
        """Start the P2P connection."""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            self.socket.bind(('', self.local_port))
            self.socket.settimeout(1.0)

            self.game_session_id = game_session_id
            self.username = username
            self.opponent_ip = opponent_ip
            self.opponent_port = opponent_port

            self.last_received_time = time.time()
            self.connected = True
            self._running = True

            # Reset sequence tracking
            self.send_sequence = 0
            self.received_sequences.clear()
            self._pending_acks.clear()

            # Start threads
            self._receiver_thread = threading.Thread(target=self._receive_loop, daemon=True)
            self._receiver_thread.start()

            self._heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
            self._heartbeat_thread.start()

            self._retry_thread = threading.Thread(target=self._retry_loop, daemon=True)
            self._retry_thread.start()

            return True
        except Exception as e:
            print(f"P2P start failed: {e}")
            return False

    def stop(self) -> None:
        """Stop the P2P connection."""
        self._running = False
        self.connected = False
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
            self.socket = None

    def _get_next_sequence(self) -> int:
        """Get next sequence number."""
        with self._sequence_lock:
            self.send_sequence += 1
            return self.send_sequence

    def send(self, message: dict, require_ack: bool = False) -> bool:
        """Send a message to the opponent."""
        if not self.connected or not self.socket:
            return False

        try:
            # Add metadata
            seq = self._get_next_sequence()
            message["timestamp"] = int(time.time() * 1000)
            message["sequenceNumber"] = seq

            data = json.dumps(message).encode('utf-8')
            self.socket.sendto(data, (self.opponent_ip, self.opponent_port))

            # Track if ACK required
            if require_ack:
                with self._pending_ack_lock:
                    self._pending_acks[seq] = {
                        "message": message,
                        "sent_time": time.time(),
                        "retries": 0
                    }

            return True
        except Exception as e:
            print(f"P2P send failed: {e}")
            return False

    def register_handler(self, message_type: str, handler: Callable) -> None:
        """Register a handler for a specific message type."""
        self.handlers[message_type] = handler

    def _receive_loop(self) -> None:
        """Background thread to receive messages."""
        while self._running:
            try:
                if not self.socket:
                    break

                try:
                    data, addr = self.socket.recvfrom(4096)
                except socket.timeout:
                    continue

                self.last_received_time = time.time()

                try:
                    message = json.loads(data.decode('utf-8'))
                    self._handle_message(message)
                except json.JSONDecodeError as e:
                    print(f"Invalid P2P JSON: {e}")

            except Exception as e:
                if self._running:
                    print(f"P2P receive error: {e}")

    def _handle_message(self, message: dict) -> None:
        """Handle an incoming message."""
        msg_type = message.get("type", "")
        seq = message.get("sequenceNumber", 0)

        # Ignore duplicates
        if seq in self.received_sequences:
            return
        self.received_sequences.add(seq)

        # Limit stored sequence numbers to prevent memory issues
        if len(self.received_sequences) > 1000:
            min_seq = min(self.received_sequences)
            self.received_sequences = {s for s in self.received_sequences if s > min_seq - 100}

        # Handle ACKs - clear pending messages
        if msg_type.endswith("_ACK"):
            self._handle_ack(message)
            # Also add ACK to queue so registered handlers get called
            # (e.g., HANDSHAKE_ACK needs to trigger game_ready)

        # Add to queue for main thread
        self.message_queue.put(message)

    def _handle_ack(self, message: dict) -> None:
        """Handle an ACK message."""
        # ACK messages clear the pending message
        # Find by examining the message type pattern
        msg_type = message.get("type", "")
        turn_number = message.get("turnNumber")

        with self._pending_ack_lock:
            # Remove from pending based on type
            to_remove = []
            for seq, data in self._pending_acks.items():
                pending_type = data["message"].get("type", "")
                if msg_type == f"{pending_type}_ACK":
                    # Additional check for turn number if present
                    if turn_number is None or data["message"].get("turnNumber") == turn_number:
                        to_remove.append(seq)
            for seq in to_remove:
                del self._pending_acks[seq]

    def _heartbeat_loop(self) -> None:
        """Background thread to send heartbeats."""
        while self._running and self.connected:
            time.sleep(HEARTBEAT_INTERVAL)

            if not self._running:
                break

            # Send heartbeat
            self.send_heartbeat()

            # Check for timeout
            if time.time() - self.last_received_time > HEARTBEAT_TIMEOUT:
                print("P2P connection timeout")
                self.connected = False
                if "DISCONNECTED" in self.handlers:
                    self.handlers["DISCONNECTED"]({})

    def _retry_loop(self) -> None:
        """Background thread to retry unacknowledged messages."""
        while self._running:
            time.sleep(ACK_TIMEOUT / 2)

            if not self._running:
                break

            current_time = time.time()
            to_retry = []
            to_remove = []

            with self._pending_ack_lock:
                for seq, data in self._pending_acks.items():
                    elapsed = current_time - data["sent_time"]
                    if elapsed >= ACK_TIMEOUT:
                        if data["retries"] < MAX_RETRIES:
                            to_retry.append((seq, data))
                        else:
                            to_remove.append(seq)
                            print(f"Message {seq} failed after {MAX_RETRIES} retries")

                for seq in to_remove:
                    del self._pending_acks[seq]

            # Retry messages outside of lock
            for seq, data in to_retry:
                message = data["message"]
                try:
                    msg_data = json.dumps(message).encode('utf-8')
                    self.socket.sendto(msg_data, (self.opponent_ip, self.opponent_port))
                    with self._pending_ack_lock:
                        if seq in self._pending_acks:
                            self._pending_acks[seq]["retries"] += 1
                            self._pending_acks[seq]["sent_time"] = current_time
                except Exception as e:
                    print(f"Retry failed: {e}")

    def process_messages(self) -> None:
        """Process pending messages from queue (call from main thread)."""
        while not self.message_queue.empty():
            message = self.message_queue.get_nowait()
            msg_type = message.get("type", "")
            if msg_type in self.handlers:
                try:
                    self.handlers[msg_type](message)
                except Exception as e:
                    print(f"P2P handler error for {msg_type}: {e}")

    # Convenience methods

    def send_handshake(self) -> bool:
        """Send initial handshake."""
        return self.send({
            "type": "HANDSHAKE",
            "gameSessionId": self.game_session_id,
            "username": self.username
        }, require_ack=False)

    def send_handshake_ack(self, ready: bool = True) -> bool:
        """Send handshake acknowledgment."""
        return self.send({
            "type": "HANDSHAKE_ACK",
            "gameSessionId": self.game_session_id,
            "username": self.username,
            "ready": ready
        })

    def send_shot(self, piece_id: int, angle: float, power: float, turn_number: int) -> bool:
        """Send a shot message."""
        return self.send({
            "type": "SHOT",
            "pieceId": piece_id,
            "angle": angle,
            "power": power,
            "turnNumber": turn_number
        }, require_ack=True)

    def send_shot_ack(self, turn_number: int) -> bool:
        """Send shot acknowledgment."""
        return self.send({
            "type": "SHOT_ACK",
            "turnNumber": turn_number,
            "received": True
        })

    def send_turn_end(self, turn_number: int, state_hash: str) -> bool:
        """Send turn end message."""
        return self.send({
            "type": "TURN_END",
            "turnNumber": turn_number,
            "stateHash": state_hash
        }, require_ack=True)

    def send_turn_end_ack(self, turn_number: int, hash_match: bool) -> bool:
        """Send turn end acknowledgment."""
        return self.send({
            "type": "TURN_END_ACK",
            "turnNumber": turn_number,
            "hashMatch": hash_match
        })

    def send_goal_scored(self, blue_scored: bool, blue_score: int, red_score: int) -> bool:
        """Send goal scored notification."""
        return self.send({
            "type": "GOAL_SCORED",
            "blueScored": blue_scored,
            "blueScore": blue_score,
            "redScore": red_score
        })

    def send_game_over(self, winner_username: str, winner_score: int, loser_score: int) -> bool:
        """Send game over message."""
        return self.send({
            "type": "GAME_OVER",
            "winnerUsername": winner_username,
            "winnerScore": winner_score,
            "loserScore": loser_score
        }, require_ack=True)

    def send_game_over_ack(self) -> bool:
        """Send game over acknowledgment."""
        return self.send({"type": "GAME_OVER_ACK"})

    def send_state_request(self) -> bool:
        """Request full state sync."""
        return self.send({"type": "STATE_REQUEST"})

    def send_state_sync(self, state_data: dict) -> bool:
        """Send full state sync."""
        message = {"type": "STATE_SYNC"}
        message.update(state_data)
        return self.send(message)

    def send_heartbeat(self) -> bool:
        """Send heartbeat."""
        return self.send({"type": "HEARTBEAT"})

    def send_heartbeat_ack(self) -> bool:
        """Send heartbeat acknowledgment."""
        return self.send({"type": "HEARTBEAT_ACK"})

    def send_rematch_request(self) -> bool:
        """Send rematch request."""
        return self.send({"type": "REMATCH_REQUEST"})

    def send_rematch_response(self, accepted: bool) -> bool:
        """Send rematch response."""
        return self.send({
            "type": "REMATCH_RESPONSE",
            "accepted": accepted
        })

    def send_return_to_lobby(self) -> bool:
        """Send return to lobby notification."""
        return self.send({"type": "RETURN_TO_LOBBY"})
