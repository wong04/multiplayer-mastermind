"""FastAPI WebSocket server wiring the game logic to clients.

One persistent `/ws` connection per player. Messages are JSON envelopes defined
in `protocol.py`. All room/game state lives in memory in a single `RoomRegistry`.
"""

from __future__ import annotations

import asyncio
import os
from dataclasses import dataclass
from datetime import datetime, timezone

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

from . import modes, protocol as p
from .modes import ClassicRound, CompetitionRound, GameError
from .rooms import (
	MIN_PLAYERS,
	MODE_COMPETITION,
	MODE_DAILY,
	MODE_SOLO,
	STATE_GAME_OVER,
	STATE_IN_ROUND,
	STATE_LOBBY,
	STATE_ROUND_OVER,
	VALID_MODES,
	Player,
	Room,
	RoomError,
	RoomRegistry,
)

# Daily puzzle #1 falls on this UTC date; the number increments each day after.
DAILY_EPOCH = datetime(2024, 1, 1, tzinfo=timezone.utc)


def today_daily_number() -> int:
	"""1-based puzzle number for the current UTC day."""
	return (datetime.now(timezone.utc) - DAILY_EPOCH).days + 1


# Modes that skip the lobby and start a single-player round immediately.
SKIP_LOBBY_MODES = (MODE_SOLO, MODE_DAILY)

app = FastAPI(title="Multiplayer Mastermind")

# Frontend is served from a different origin (Vercel) than this server (Railway).
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_methods=["*"],
	allow_headers=["*"],
)

registry = RoomRegistry()


@app.get("/healthz")
async def healthz() -> dict:
	return {"status": "ok"}


# Railway injects the deployed commit SHA; falls back to "unknown" locally.
COMMIT_SHA = os.environ.get("RAILWAY_GIT_COMMIT_SHA", "unknown")


@app.get("/version")
async def version() -> dict:
	return {"commit": COMMIT_SHA, "modes": list(VALID_MODES)}


class ConnectionManager:
	"""Maps player ids to their live WebSocket and broadcasts to rooms."""

	def __init__(self) -> None:
		self._sockets: dict[str, WebSocket] = {}

	def register(self, player_id: str, ws: WebSocket) -> None:
		self._sockets[player_id] = ws

	def unregister(self, player_id: str) -> None:
		self._sockets.pop(player_id, None)

	async def send(self, player_id: str, message: dict) -> None:
		ws = self._sockets.get(player_id)
		if ws is None:
			return
		try:
			await ws.send_json(message)
		except RuntimeError:
			# Socket closed between the connection check and the send.
			self.unregister(player_id)

	async def broadcast(self, room: Room, message: dict) -> None:
		for player in room.player_order():
			await self.send(player.id, message)


manager = ConnectionManager()


@dataclass
class Session:
	"""Per-connection binding to a room and player, set after create/join/reconnect."""

	room: Room | None = None
	player: Player | None = None


# ---------------------------------------------------------------------------
# Message-building helpers
# ---------------------------------------------------------------------------


def scoreboard(room: Room) -> list[dict]:
	return [pl.public_dict() for pl in room.player_order()]


def your_board(room: Room, player_id: str) -> list[dict]:
	rnd = room.round
	if isinstance(rnd, (ClassicRound, CompetitionRound)):
		return modes.board_to_dicts(rnd.boards.get(player_id, []))
	return []


def round_start_msg(room: Room, player_id: str) -> dict:
	rnd = room.round
	payload = {
		"mode": room.mode,
		"round_no": room.round_no,
		"config": room.config.to_dict(),
		"scoreboard": scoreboard(room),
		"your_board": your_board(room, player_id),
	}
	if isinstance(rnd, ClassicRound):
		payload.update(
			codemaker_id=rnd.codemaker_id,
			secret_set=rnd.secret is not None,
			role="codemaker" if player_id == rnd.codemaker_id else "breaker",
		)
	elif isinstance(rnd, CompetitionRound):
		payload.update(
			guess_no=rnd.guess_no,
			submitted=len(rnd.pending),
			total=len(room.connected_players()),
			already_submitted=player_id in rnd.pending,
		)
	if room.mode == MODE_DAILY:
		payload["daily_no"] = room.daily_day
	return p.make(p.ROUND_START, **payload)


def barrier_msg(room: Room) -> dict:
	rnd = room.round
	assert isinstance(rnd, CompetitionRound)
	return p.make(
		p.BARRIER_UPDATE,
		guess_no=rnd.guess_no,
		submitted=len(rnd.pending),
		total=len(room.connected_players()),
	)


# ---------------------------------------------------------------------------
# Shared emitters
# ---------------------------------------------------------------------------


async def broadcast_lobby(room: Room) -> None:
	await manager.broadcast(room, p.make(p.LOBBY_UPDATE, **room.lobby_dict()))


async def broadcast_round_start(room: Room) -> None:
	for player in room.player_order():
		await manager.send(player.id, round_start_msg(room, player.id))
	await arm_turn_timer(room)


async def emit_round_over(room: Room, winner_id: str | None, reason: str) -> None:
	cancel_turn_timer(room)
	rnd = room.round
	secret = list(rnd.secret) if getattr(rnd, "secret", None) is not None else None
	match_winner = modes.finish_round(room)
	await manager.broadcast(
		room,
		p.make(
			p.ROUND_OVER,
			winner_id=winner_id,
			reason=reason,
			secret=secret,
			scoreboard=scoreboard(room),
		),
	)
	if match_winner is not None:
		await manager.broadcast(
			room,
			p.make(p.GAME_OVER, winner_id=match_winner.id, scoreboard=scoreboard(room)),
		)


# ---------------------------------------------------------------------------
# Handlers
# ---------------------------------------------------------------------------


async def handle_create_room(msg: dict, ws: WebSocket, session: Session) -> None:
	mode = msg.get("mode", "classic")
	if mode not in VALID_MODES:
		raise RoomError(f"Unknown mode: {mode}")
	nickname = msg.get("nickname", "")
	if mode in SKIP_LOBBY_MODES and not nickname.strip():
		nickname = "Player"
	room, player = registry.create_room(nickname, mode=mode)
	_bind(session, room, player, ws)
	await _send_joined(room, player)
	if mode in SKIP_LOBBY_MODES:
		# Solo/daily skip the lobby and start immediately.
		if mode == MODE_DAILY:
			# Everyone shares the same code and rules for the day.
			room.daily_day = today_daily_number()
			room.config.code_length = 4
			room.config.n_colors = 6
			room.config.max_guesses = 10
		else:
			_apply_config(room, msg.get("config") or {})
		modes.start_round(room)
		await broadcast_round_start(room)
		return
	await broadcast_lobby(room)


async def handle_join_room(msg: dict, ws: WebSocket, session: Session) -> None:
	room, player = registry.join_room(msg.get("room_code", ""), msg.get("nickname", ""))
	_bind(session, room, player, ws)
	await _send_joined(room, player)
	await broadcast_lobby(room)


async def handle_reconnect(msg: dict, ws: WebSocket, session: Session) -> None:
	room = registry.get(msg.get("room_code", ""))
	if room is None:
		raise RoomError("Room no longer exists")
	player = room.get_player_by_token(msg.get("token", ""))
	if player is None:
		raise RoomError("Unknown session for this room")
	player.connected = True
	_bind(session, room, player, ws)
	await _send_joined(room, player)
	await broadcast_lobby(room)
	if room.state in (STATE_IN_ROUND, STATE_ROUND_OVER):
		await manager.send(player.id, round_start_msg(room, player.id))


async def handle_set_mode(msg: dict, ws: WebSocket, session: Session) -> None:
	room, player = _require_host_in_lobby(session)
	mode = msg.get("mode")
	if mode not in VALID_MODES:
		raise GameError(f"Unknown mode: {mode}")
	room.mode = mode
	await broadcast_lobby(room)


async def handle_set_config(msg: dict, ws: WebSocket, session: Session) -> None:
	room, player = _require_host_in_lobby(session)
	_apply_config(room, msg)
	await broadcast_lobby(room)


def _apply_config(room: Room, cfg_msg: dict) -> None:
	cfg = room.config
	cfg.code_length = _clamp(cfg_msg.get("code_length", cfg.code_length), 2, 8)
	cfg.n_colors = _clamp(cfg_msg.get("n_colors", cfg.n_colors), 2, 10)
	cfg.max_guesses = _clamp(cfg_msg.get("max_guesses", cfg.max_guesses), 1, 20)
	cfg.target_score = _clamp(cfg_msg.get("target_score", cfg.target_score), 1, 20)
	cfg.turn_seconds = _clamp_turn_seconds(cfg_msg.get("turn_seconds", cfg.turn_seconds))
	cfg.allow_blanks = bool(cfg_msg.get("allow_blanks", cfg.allow_blanks))
	cfg.hard_mode = bool(cfg_msg.get("hard_mode", cfg.hard_mode))


def _clamp_turn_seconds(value) -> int:
	"""0 disables the timer; any positive value is clamped to a sane 10–300s range."""
	try:
		value = int(value)
	except (TypeError, ValueError):
		raise GameError("Turn timer must be an integer")
	if value <= 0:
		return 0
	return max(10, min(300, value))


async def handle_start_game(msg: dict, ws: WebSocket, session: Session) -> None:
	room, player = _require_host_in_lobby(session)
	if len(room.connected_players()) < MIN_PLAYERS:
		raise GameError(f"Need at least {MIN_PLAYERS} players to start")
	room.reset_scores()
	modes.start_round(room)
	await broadcast_round_start(room)


async def handle_set_secret(msg: dict, ws: WebSocket, session: Session) -> None:
	room, player = _require_active(session)
	modes.set_classic_secret(room, player.id, msg.get("secret"))
	# Re-send round_start so breakers learn the secret is set and can begin.
	await broadcast_round_start(room)


async def handle_submit_guess(msg: dict, ws: WebSocket, session: Session) -> None:
	room, player = _require_active(session)
	if room.state != STATE_IN_ROUND:
		raise GameError("No round in progress")
	if isinstance(room.round, ClassicRound):
		await _classic_guess(room, player, msg.get("guess"))
	elif isinstance(room.round, CompetitionRound):
		await _competition_guess(room, player, msg.get("guess"))
	else:
		raise GameError("No round in progress")


async def _classic_guess(room: Room, player: Player, guess) -> None:
	outcome = modes.submit_classic_guess(room, player.id, guess)
	await manager.send(
		player.id,
		p.make(
			p.GUESS_FEEDBACK,
			result=outcome["result"].to_dict(),
			board=your_board(room, player.id),
		),
	)
	if outcome["round_over"]:
		await emit_round_over(room, outcome["winner_id"], outcome["reason"])


async def _competition_guess(room: Room, player: Player, guess) -> None:
	modes.submit_competition_guess(room, player.id, guess)
	await manager.broadcast(room, barrier_msg(room))
	if modes.competition_barrier_ready(room):
		await _resolve_barrier(room)


async def _resolve_barrier(room: Room) -> None:
	outcome = modes.resolve_competition_barrier(room)
	for pid, result in outcome["results"].items():
		await manager.send(
			pid,
			p.make(p.GUESS_FEEDBACK, result=result.to_dict(), board=your_board(room, pid)),
		)
	if outcome["round_over"]:
		await emit_round_over(room, outcome["winner_id"], "cracked" if outcome["winner_id"] else "unbroken")
	else:
		await manager.broadcast(room, barrier_msg(room))
		await arm_turn_timer(room)


# ---------------------------------------------------------------------------
# Per-turn timer (competition mode)
# ---------------------------------------------------------------------------

# One countdown task per room while a timed competition barrier is open.
_turn_timers: dict[str, asyncio.Task] = {}


def cancel_turn_timer(room: Room) -> None:
	task = _turn_timers.pop(room.code, None)
	if task is not None:
		task.cancel()


async def arm_turn_timer(room: Room) -> None:
	"""Start (or restart) the countdown for the current competition barrier."""
	cancel_turn_timer(room)
	cfg = room.config
	if room.mode != MODE_COMPETITION or cfg.turn_seconds <= 0:
		return
	rnd = room.round
	if not isinstance(rnd, CompetitionRound) or rnd.finished:
		return
	await manager.broadcast(room, p.make(p.TURN_TIMER, seconds=cfg.turn_seconds, guess_no=rnd.guess_no))
	_turn_timers[room.code] = asyncio.create_task(_turn_timeout(room, cfg.turn_seconds, rnd.guess_no))


async def _turn_timeout(room: Room, seconds: int, guess_no: int) -> None:
	try:
		await asyncio.sleep(seconds)
	except asyncio.CancelledError:
		return
	# Drop our own registry entry first so resolution's cancel calls are no-ops.
	_turn_timers.pop(room.code, None)
	rnd = room.round
	if room.state != STATE_IN_ROUND or not isinstance(rnd, CompetitionRound):
		return
	if rnd.finished or rnd.guess_no != guess_no:
		return
	# Time's up: resolve with whoever submitted (non-submitters skip this guess).
	await _resolve_barrier(room)


async def handle_restart_round(msg: dict, ws: WebSocket, session: Session) -> None:
	room, player = _require_host(session)
	if room.state != STATE_IN_ROUND:
		raise GameError("No round in progress to restart")
	# Replay the same round: undo the counters start_round will re-apply so the
	# classic codemaker stays the same player rather than rotating on.
	room.round_no -= 1
	room.codemaker_turn = max(0, room.codemaker_turn - 1)
	room.round = None
	modes.start_round(room)
	await broadcast_round_start(room)


async def handle_next_round(msg: dict, ws: WebSocket, session: Session) -> None:
	room, player = _require_host(session)
	if room.state != STATE_ROUND_OVER:
		raise GameError("Round still in progress")
	modes.start_round(room)
	await broadcast_round_start(room)


async def handle_rematch(msg: dict, ws: WebSocket, session: Session) -> None:
	room, player = _require_host(session)
	if room.state != STATE_GAME_OVER:
		raise GameError("Match is not over")
	cancel_turn_timer(room)
	room.reset_scores()
	room.round = None
	room.round_no = 0
	room.state = STATE_LOBBY
	await broadcast_lobby(room)


HANDLERS = {
	p.CREATE_ROOM: handle_create_room,
	p.JOIN_ROOM: handle_join_room,
	p.RECONNECT: handle_reconnect,
	p.SET_MODE: handle_set_mode,
	p.SET_CONFIG: handle_set_config,
	p.START_GAME: handle_start_game,
	p.SET_SECRET: handle_set_secret,
	p.SUBMIT_GUESS: handle_submit_guess,
	p.NEXT_ROUND: handle_next_round,
	p.RESTART_ROUND: handle_restart_round,
	p.REMATCH: handle_rematch,
}


# ---------------------------------------------------------------------------
# WebSocket endpoint
# ---------------------------------------------------------------------------


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
	await ws.accept()
	session = Session()
	try:
		while True:
			msg = await ws.receive_json()
			handler = HANDLERS.get(msg.get("type"))
			if handler is None:
				await ws.send_json(p.error(f"Unknown message type: {msg.get('type')}"))
				continue
			try:
				await handler(msg, ws, session)
			except (RoomError, GameError) as exc:
				await ws.send_json(p.error(str(exc)))
	except WebSocketDisconnect:
		await _handle_disconnect(session)


# ---------------------------------------------------------------------------
# Disconnect handling
# ---------------------------------------------------------------------------


async def _handle_disconnect(session: Session) -> None:
	room, player = session.room, session.player
	if room is None or player is None:
		return
	player.connected = False
	manager.unregister(player.id)

	if room.all_disconnected():
		cancel_turn_timer(room)
		registry.remove(room.code)
		return

	if room.host_id == player.id:
		room.host_id = room.connected_players()[0].id

	await broadcast_lobby(room)

	if room.state == STATE_IN_ROUND:
		await _resolve_after_disconnect(room, player)


async def _resolve_after_disconnect(room: Room, dropped: Player) -> None:
	rnd = room.round
	if isinstance(rnd, CompetitionRound):
		if modes.competition_barrier_ready(room):
			await _resolve_barrier(room)
		else:
			await manager.broadcast(room, barrier_msg(room))
		return

	if isinstance(rnd, ClassicRound):
		if dropped.id == rnd.codemaker_id and rnd.secret is None:
			rnd.finished = True
			await emit_round_over(room, None, "aborted")
			return
		outcome = modes.classic_resolve_if_stalled(room)
		if outcome is not None:
			await emit_round_over(room, outcome["winner_id"], outcome["reason"])


# ---------------------------------------------------------------------------
# Session / validation helpers
# ---------------------------------------------------------------------------


def _bind(session: Session, room: Room, player: Player, ws: WebSocket) -> None:
	session.room = room
	session.player = player
	manager.register(player.id, ws)


async def _send_joined(room: Room, player: Player) -> None:
	await manager.send(
		player.id,
		p.make(
			p.ROOM_JOINED,
			room_code=room.code,
			player_id=player.id,
			player_token=player.token,
			host_id=room.host_id,
			you=player.public_dict(),
		),
	)


def _require_active(session: Session) -> tuple[Room, Player]:
	if session.room is None or session.player is None:
		raise GameError("Not in a room")
	return session.room, session.player


def _require_host(session: Session) -> tuple[Room, Player]:
	room, player = _require_active(session)
	if room.host_id != player.id:
		raise GameError("Only the host can do that")
	return room, player


def _require_host_in_lobby(session: Session) -> tuple[Room, Player]:
	room, player = _require_host(session)
	if room.state != STATE_LOBBY:
		raise GameError("Can only change this in the lobby")
	return room, player


def _clamp(value, low: int, high: int) -> int:
	try:
		value = int(value)
	except (TypeError, ValueError):
		raise GameError("Config values must be integers")
	return max(low, min(high, value))
