"""Room and player lifecycle — lobby state, membership, scoring.

Per-round game state lives in `modes.py`; a room only holds a reference to the
current round via `Room.round`.
"""

from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass, field

MIN_PLAYERS = 2
MAX_PLAYERS = 4
ROOM_CODE_LENGTH = 4
# Unambiguous alphabet (no 0/O, 1/I) for human-typed room codes.
ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"

MODE_CLASSIC = "classic"
MODE_COMPETITION = "competition"
MODE_SOLO = "solo"
MODE_DAILY = "daily"
VALID_MODES = (MODE_CLASSIC, MODE_COMPETITION, MODE_SOLO, MODE_DAILY)

STATE_LOBBY = "lobby"
STATE_IN_ROUND = "in_round"
STATE_ROUND_OVER = "round_over"
STATE_GAME_OVER = "game_over"


class RoomError(Exception):
	"""Base class for room operations the caller should surface to a client."""


class RoomNotFound(RoomError):
	pass


class RoomFull(RoomError):
	pass


class GameAlreadyStarted(RoomError):
	pass


class InvalidNickname(RoomError):
	pass


@dataclass
class GameConfig:
	code_length: int = 4
	n_colors: int = 6
	max_guesses: int = 10
	target_score: int = 3
	# 0 = no per-turn timer; otherwise seconds allowed per competition barrier.
	turn_seconds: int = 0
	# Blanks add one extra symbol (the empty peg) as a usable color.
	allow_blanks: bool = False
	# Hard mode: each guess must stay consistent with all prior feedback.
	hard_mode: bool = False

	def effective_colors(self) -> int:
		"""Total distinct symbols a guess may use, counting the blank when enabled."""
		return self.n_colors + (1 if self.allow_blanks else 0)

	def to_dict(self) -> dict:
		return {
			"code_length": self.code_length,
			"n_colors": self.n_colors,
			"max_guesses": self.max_guesses,
			"target_score": self.target_score,
			"turn_seconds": self.turn_seconds,
			"allow_blanks": self.allow_blanks,
			"hard_mode": self.hard_mode,
		}


@dataclass
class Player:
	id: str
	token: str
	nickname: str
	connected: bool = True
	score: int = 0

	def public_dict(self) -> dict:
		"""Player info safe to broadcast to everyone (no token)."""
		return {
			"id": self.id,
			"nickname": self.nickname,
			"connected": self.connected,
			"score": self.score,
		}


@dataclass
class Room:
	code: str
	host_id: str
	config: GameConfig = field(default_factory=GameConfig)
	mode: str = MODE_CLASSIC
	state: str = STATE_LOBBY
	players: dict[str, Player] = field(default_factory=dict)
	round_no: int = 0
	# Index into the player order used to rotate the classic codemaker.
	codemaker_turn: int = 0
	# Current round state object (defined in modes.py) or None in the lobby.
	round: object | None = None
	# Day number for a daily-challenge room (set at creation), else None.
	daily_day: int | None = None

	# -- membership --------------------------------------------------------

	def add_player(self, nickname: str) -> Player:
		nickname = (nickname or "").strip()
		if not nickname:
			raise InvalidNickname("Nickname cannot be empty")
		if len(nickname) > 20:
			raise InvalidNickname("Nickname too long (max 20 characters)")
		if self.state != STATE_LOBBY:
			raise GameAlreadyStarted("Game already in progress")
		if len(self.players) >= MAX_PLAYERS:
			raise RoomFull("Room is full")
		player = Player(id=uuid.uuid4().hex, token=secrets.token_urlsafe(16), nickname=nickname)
		self.players[player.id] = player
		return player

	def get_player(self, player_id: str) -> Player | None:
		return self.players.get(player_id)

	def get_player_by_token(self, token: str) -> Player | None:
		return next((p for p in self.players.values() if p.token == token), None)

	def remove_player(self, player_id: str) -> None:
		self.players.pop(player_id, None)

	def player_order(self) -> list[Player]:
		"""Players in stable join order."""
		return list(self.players.values())

	def connected_players(self) -> list[Player]:
		return [p for p in self.players.values() if p.connected]

	def is_empty(self) -> bool:
		return len(self.players) == 0

	def all_disconnected(self) -> bool:
		return len(self.connected_players()) == 0

	# -- scoring -----------------------------------------------------------

	def reset_scores(self) -> None:
		for p in self.players.values():
			p.score = 0

	def winner_by_score(self) -> Player | None:
		"""The player who has reached the target score, if any."""
		return next((p for p in self.players.values() if p.score >= self.config.target_score), None)

	# -- serialization -----------------------------------------------------

	def lobby_dict(self) -> dict:
		return {
			"code": self.code,
			"host_id": self.host_id,
			"mode": self.mode,
			"state": self.state,
			"config": self.config.to_dict(),
			"players": [p.public_dict() for p in self.player_order()],
		}


class RoomRegistry:
	"""In-memory store of active rooms keyed by room code."""

	def __init__(self) -> None:
		self._rooms: dict[str, Room] = {}

	def _new_code(self) -> str:
		while True:
			code = "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LENGTH))
			if code not in self._rooms:
				return code

	def create_room(self, host_nickname: str, mode: str = MODE_CLASSIC) -> tuple[Room, Player]:
		if mode not in VALID_MODES:
			raise RoomError(f"Unknown mode: {mode}")
		code = self._new_code()
		room = Room(code=code, host_id="", mode=mode)
		host = room.add_player(host_nickname)
		room.host_id = host.id
		self._rooms[code] = room
		return room, host

	def join_room(self, code: str, nickname: str) -> tuple[Room, Player]:
		room = self.get(code)
		if room is None:
			raise RoomNotFound("No room with that code")
		player = room.add_player(nickname)
		return room, player

	def get(self, code: str) -> Room | None:
		return self._rooms.get((code or "").upper())

	def remove(self, code: str) -> None:
		self._rooms.pop(code, None)

	def prune_empty(self) -> None:
		for code in [c for c, r in self._rooms.items() if r.is_empty()]:
			del self._rooms[code]
