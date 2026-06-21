"""WebSocket message protocol — type constants and small (de)serialization helpers.

All messages are JSON objects with a `type` field plus type-specific payload keys.
"""

from __future__ import annotations

# -- client -> server message types --------------------------------------
CREATE_ROOM = "create_room"
JOIN_ROOM = "join_room"
RECONNECT = "reconnect"
SET_MODE = "set_mode"
SET_CONFIG = "set_config"
START_GAME = "start_game"
SET_SECRET = "set_secret"
SUBMIT_GUESS = "submit_guess"
NEXT_ROUND = "next_round"
RESTART_ROUND = "restart_round"
REMATCH = "rematch"

# -- server -> client message types --------------------------------------
ROOM_JOINED = "room_joined"
LOBBY_UPDATE = "lobby_update"
ROUND_START = "round_start"
AWAITING_SECRET = "awaiting_secret"
GUESS_FEEDBACK = "guess_feedback"
BARRIER_UPDATE = "barrier_update"
TURN_TIMER = "turn_timer"
ROUND_OVER = "round_over"
GAME_OVER = "game_over"
ERROR = "error"


def make(type_: str, **payload) -> dict:
	"""Build an outgoing message envelope."""
	return {"type": type_, **payload}


def error(message: str, *, code: str | None = None) -> dict:
	msg = make(ERROR, message=message)
	if code is not None:
		msg["code"] = code
	return msg
