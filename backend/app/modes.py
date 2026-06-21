"""Per-round game flow for both modes.

`ClassicRound`  — one rotating codemaker sets the secret; the others race in
real time on private boards. First to crack the code wins the round; if nobody
cracks it within `max_guesses`, the codemaker scores.

`CompetitionRound` — server generates one shared secret; play advances in
synchronized barrier rounds. Every connected player submits a guess for the
current barrier round; only once the last has submitted is the barrier resolved.
The first to crack it (earliest submission within the resolving barrier) wins.

These classes mutate the `Room` and its `Player.score` but perform no I/O. The
caller (`main.py`) turns the returned outcome data into protocol messages.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import count

from . import game
from .rooms import (
	MODE_CLASSIC,
	MODE_COMPETITION,
	MODE_DAILY,
	MODE_SOLO,
	STATE_GAME_OVER,
	STATE_IN_ROUND,
	STATE_ROUND_OVER,
	Player,
	Room,
)


class GameError(Exception):
	"""Invalid game action the caller should surface to the offending client."""


@dataclass
class GuessResult:
	guess: tuple[int, ...]
	black: int
	white: int
	guess_no: int
	per_slot: list[str] = field(default_factory=list)

	@property
	def solved(self) -> bool:
		return self.black == len(self.guess)

	def to_dict(self) -> dict:
		return {
			"guess": list(self.guess),
			"black": self.black,
			"white": self.white,
			"guess_no": self.guess_no,
			"per_slot": self.per_slot,
		}


def _score(secret: tuple[int, ...], guess: tuple[int, ...], guess_no: int) -> GuessResult:
	black, white = game.score_guess(secret, guess)
	per_slot = game.score_guess_per_slot(secret, guess)
	return GuessResult(guess=tuple(guess), black=black, white=white, guess_no=guess_no, per_slot=per_slot)


def _validate_guess(room: Room, guess) -> tuple[int, ...]:
	cfg = room.config
	if not game.is_valid_guess(guess, cfg.code_length, cfg.effective_colors()):
		raise GameError("Invalid guess: wrong length or color out of range")
	return tuple(guess)


def _check_hard_mode(room: Room, guess: tuple[int, ...], board: list[GuessResult]) -> None:
	if not room.config.hard_mode:
		return
	history = [(r.guess, r.black, r.white) for r in board]
	if not game.is_consistent_with_history(guess, history):
		raise GameError("Hard mode: guess must be consistent with previous clues")


def board_to_dicts(board: list[GuessResult]) -> list[dict]:
	return [r.to_dict() for r in board]


# ---------------------------------------------------------------------------
# Classic mode
# ---------------------------------------------------------------------------


@dataclass
class ClassicRound:
	codemaker_id: str
	breaker_ids: list[str]
	secret: tuple[int, ...] | None = None
	boards: dict[str, list[GuessResult]] = field(default_factory=dict)
	out: set[str] = field(default_factory=set)
	finished: bool = False
	winner_id: str | None = None

	def board(self, player_id: str) -> list[GuessResult]:
		return self.boards.setdefault(player_id, [])


def start_classic_round(room: Room) -> ClassicRound:
	"""Begin a classic round, rotating the codemaker to the next connected player."""
	order = room.connected_players()
	if len(order) < 2:
		raise GameError("Need at least 2 players")
	codemaker = order[room.codemaker_turn % len(order)]
	room.codemaker_turn += 1
	breaker_ids = [p.id for p in order if p.id != codemaker.id]
	rnd = ClassicRound(codemaker_id=codemaker.id, breaker_ids=breaker_ids)
	room.round = rnd
	room.round_no += 1
	room.state = STATE_IN_ROUND
	return rnd


def set_classic_secret(room: Room, player_id: str, secret) -> None:
	rnd = _require_classic(room)
	if player_id != rnd.codemaker_id:
		raise GameError("Only the codemaker can set the secret")
	if rnd.secret is not None:
		raise GameError("Secret already set")
	rnd.secret = _validate_guess(room, secret)


def submit_classic_guess(room: Room, player_id: str, guess) -> dict:
	"""Apply a breaker's guess. Returns an outcome dict for the caller to relay."""
	rnd = _require_classic(room)
	if rnd.finished:
		raise GameError("Round already over")
	if rnd.secret is None:
		raise GameError("Codemaker has not set the secret yet")
	if player_id == rnd.codemaker_id:
		raise GameError("The codemaker cannot guess")
	if player_id not in rnd.breaker_ids:
		raise GameError("You are not a breaker in this round")
	if player_id in rnd.out:
		raise GameError("You have used all your guesses")

	board = rnd.board(player_id)
	if len(board) >= room.config.max_guesses:
		raise GameError("You have used all your guesses")

	guess_t = _validate_guess(room, guess)
	_check_hard_mode(room, guess_t, board)
	result = _score(rnd.secret, guess_t, len(board) + 1)
	board.append(result)

	outcome: dict = {"result": result, "round_over": False}

	if result.solved:
		rnd.finished = True
		rnd.winner_id = player_id
		room.players[player_id].score += 1
		outcome.update(round_over=True, winner_id=player_id, reason="cracked")
		return outcome

	if len(board) >= room.config.max_guesses:
		rnd.out.add(player_id)

	if _all_breakers_done(room, rnd):
		rnd.finished = True
		rnd.winner_id = None
		room.players[rnd.codemaker_id].score += 1
		outcome.update(round_over=True, winner_id=rnd.codemaker_id, reason="unbroken")

	return outcome


def classic_resolve_if_stalled(room: Room) -> dict | None:
	"""If every breaker has dropped/exhausted without solving, the codemaker scores.

	Called after a disconnect so a classic round can't hang. Returns an outcome
	dict (like `submit_classic_guess`) or None if the round should continue.
	"""
	rnd = room.round
	if not isinstance(rnd, ClassicRound) or rnd.finished or rnd.secret is None:
		return None
	if not _all_breakers_done(room, rnd):
		return None
	rnd.finished = True
	rnd.winner_id = rnd.codemaker_id
	room.players[rnd.codemaker_id].score += 1
	return {"round_over": True, "winner_id": rnd.codemaker_id, "reason": "unbroken"}


def _all_breakers_done(room: Room, rnd: ClassicRound) -> bool:
	active = [
		pid
		for pid in rnd.breaker_ids
		if room.players.get(pid) and room.players[pid].connected and pid not in rnd.out
	]
	return len(active) == 0


def _require_classic(room: Room) -> ClassicRound:
	if not isinstance(room.round, ClassicRound):
		raise GameError("Not a classic round")
	return room.round


# ---------------------------------------------------------------------------
# Competition mode
# ---------------------------------------------------------------------------


@dataclass
class Submission:
	result: GuessResult
	seq: int


@dataclass
class CompetitionRound:
	secret: tuple[int, ...]
	boards: dict[str, list[GuessResult]] = field(default_factory=dict)
	pending: dict[str, Submission] = field(default_factory=dict)
	guess_no: int = 1
	finished: bool = False
	winner_id: str | None = None
	_seq: count = field(default_factory=lambda: count())

	def board(self, player_id: str) -> list[GuessResult]:
		return self.boards.setdefault(player_id, [])


def start_competition_round(room: Room) -> CompetitionRound:
	if len(room.connected_players()) < 2:
		raise GameError("Need at least 2 players")
	return _start_server_secret_round(room)


def start_solo_round(room: Room) -> CompetitionRound:
	"""Begin a single-player round against a server-generated secret."""
	if len(room.connected_players()) < 1:
		raise GameError("Need at least 1 player")
	return _start_server_secret_round(room)


def start_daily_round(room: Room) -> CompetitionRound:
	"""Begin the deterministic daily-challenge round (single player)."""
	if len(room.connected_players()) < 1:
		raise GameError("Need at least 1 player")
	if room.daily_day is None:
		raise GameError("Daily room missing its day number")
	secret = game.generate_daily_secret(room.daily_day, room.config.code_length, room.config.effective_colors())
	return _make_competition_round(room, secret)


def _start_server_secret_round(room: Room) -> CompetitionRound:
	secret = game.generate_secret(room.config.code_length, room.config.effective_colors())
	return _make_competition_round(room, secret)


def _make_competition_round(room: Room, secret: tuple[int, ...]) -> CompetitionRound:
	rnd = CompetitionRound(secret=secret)
	room.round = rnd
	room.round_no += 1
	room.state = STATE_IN_ROUND
	return rnd


def submit_competition_guess(room: Room, player_id: str, guess) -> None:
	"""Record a player's guess for the current barrier round (no resolution yet)."""
	rnd = _require_competition(room)
	if rnd.finished:
		raise GameError("Round already over")
	if player_id not in room.players:
		raise GameError("Unknown player")
	if player_id in rnd.pending:
		raise GameError("You already submitted this round")
	guess_t = _validate_guess(room, guess)
	_check_hard_mode(room, guess_t, rnd.board(player_id))
	result = _score(rnd.secret, guess_t, rnd.guess_no)
	rnd.pending[player_id] = Submission(result=result, seq=next(rnd._seq))


def competition_barrier_ready(room: Room) -> bool:
	"""True when every connected player has submitted for the current barrier."""
	rnd = _require_competition(room)
	if rnd.finished:
		return False
	expected = [p.id for p in room.connected_players()]
	if not expected:
		return False
	return all(pid in rnd.pending for pid in expected)


def resolve_competition_barrier(room: Room) -> dict:
	"""Resolve the current barrier: commit guesses, pick a winner or advance.

	Returns {results: {pid: GuessResult}, round_over, winner_id, secret?, guess_no}.
	"""
	rnd = _require_competition(room)
	if rnd.finished:
		raise GameError("Round already over")

	submissions = sorted(rnd.pending.items(), key=lambda kv: kv[1].seq)
	results: dict[str, GuessResult] = {}
	winner_id: str | None = None
	for pid, sub in submissions:
		rnd.board(pid).append(sub.result)
		results[pid] = sub.result
		if sub.result.solved and winner_id is None:
			winner_id = pid

	rnd.pending = {}

	outcome: dict = {"results": results, "round_over": False, "guess_no": rnd.guess_no}

	if winner_id is not None:
		rnd.finished = True
		rnd.winner_id = winner_id
		room.players[winner_id].score += 1
		outcome.update(round_over=True, winner_id=winner_id, secret=rnd.secret)
		return outcome

	if rnd.guess_no >= room.config.max_guesses:
		rnd.finished = True
		rnd.winner_id = None
		outcome.update(round_over=True, winner_id=None, secret=rnd.secret)
		return outcome

	rnd.guess_no += 1
	outcome["next_guess_no"] = rnd.guess_no
	return outcome


def _require_competition(room: Room) -> CompetitionRound:
	if not isinstance(room.round, CompetitionRound):
		raise GameError("Not a competition round")
	return room.round


# ---------------------------------------------------------------------------
# Shared round/match lifecycle
# ---------------------------------------------------------------------------


def start_round(room: Room):
	if room.mode == MODE_CLASSIC:
		return start_classic_round(room)
	if room.mode == MODE_COMPETITION:
		return start_competition_round(room)
	if room.mode == MODE_SOLO:
		return start_solo_round(room)
	if room.mode == MODE_DAILY:
		return start_daily_round(room)
	raise GameError(f"Unknown mode: {room.mode}")


def finish_round(room: Room) -> Player | None:
	"""Mark the round over and return the match winner if the target score is reached.

	Solo and daily have no match target: they always return to `round_over` so the
	player can keep dealing fresh codes via `next_round`.
	"""
	if room.mode in (MODE_SOLO, MODE_DAILY):
		room.state = STATE_ROUND_OVER
		return None
	match_winner = room.winner_by_score()
	room.state = STATE_GAME_OVER if match_winner else STATE_ROUND_OVER
	return match_winner
