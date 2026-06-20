import pytest

from app import modes
from app.rooms import (
	MODE_CLASSIC,
	MODE_COMPETITION,
	STATE_GAME_OVER,
	STATE_ROUND_OVER,
	RoomRegistry,
)


def make_room(mode, n_players=3, **config):
	reg = RoomRegistry()
	room, host = reg.create_room("p0", mode=mode)
	players = [host]
	for i in range(1, n_players):
		_, p = reg.join_room(room.code, f"p{i}")
		players.append(p)
	for k, v in config.items():
		setattr(room.config, k, v)
	return room, players


# ---------------------------------------------------------------------------
# Classic
# ---------------------------------------------------------------------------


class TestClassic:
	def test_codemaker_rotates_each_round(self):
		room, players = make_room(MODE_CLASSIC)
		r1 = modes.start_classic_round(room)
		first = r1.codemaker_id
		room.round = None
		r2 = modes.start_classic_round(room)
		assert r2.codemaker_id != first

	def test_only_codemaker_sets_secret(self):
		room, players = make_room(MODE_CLASSIC)
		rnd = modes.start_classic_round(room)
		breaker = next(p for p in players if p.id != rnd.codemaker_id)
		with pytest.raises(modes.GameError):
			modes.set_classic_secret(room, breaker.id, [1, 2, 3, 4])
		modes.set_classic_secret(room, rnd.codemaker_id, [1, 2, 3, 4])
		assert rnd.secret == (1, 2, 3, 4)

	def test_codemaker_cannot_guess(self):
		room, players = make_room(MODE_CLASSIC)
		rnd = modes.start_classic_round(room)
		modes.set_classic_secret(room, rnd.codemaker_id, [1, 2, 3, 4])
		with pytest.raises(modes.GameError):
			modes.submit_classic_guess(room, rnd.codemaker_id, [1, 2, 3, 4])

	def test_first_to_crack_wins_and_scores(self):
		room, players = make_room(MODE_CLASSIC)
		rnd = modes.start_classic_round(room)
		modes.set_classic_secret(room, rnd.codemaker_id, [1, 2, 3, 4])
		breaker = next(p for p in players if p.id != rnd.codemaker_id)
		out = modes.submit_classic_guess(room, breaker.id, [1, 2, 3, 4])
		assert out["round_over"] is True
		assert out["winner_id"] == breaker.id
		assert breaker.score == 1
		# round is finished; further guesses rejected
		with pytest.raises(modes.GameError):
			modes.submit_classic_guess(room, breaker.id, [1, 2, 3, 4])

	def test_codemaker_scores_when_unbroken(self):
		room, players = make_room(MODE_CLASSIC, n_players=2, max_guesses=3)
		rnd = modes.start_classic_round(room)
		codemaker = room.players[rnd.codemaker_id]
		modes.set_classic_secret(room, rnd.codemaker_id, [0, 0, 0, 0])
		breaker = next(p for p in players if p.id != rnd.codemaker_id)
		out = None
		for _ in range(room.config.max_guesses):
			out = modes.submit_classic_guess(room, breaker.id, [1, 1, 1, 1])
		assert out["round_over"] is True
		assert out["winner_id"] == codemaker.id
		assert out["reason"] == "unbroken"
		assert codemaker.score == 1
		assert breaker.score == 0


# ---------------------------------------------------------------------------
# Competition (barrier)
# ---------------------------------------------------------------------------


class TestCompetition:
	def test_barrier_waits_for_all_players(self):
		room, players = make_room(MODE_COMPETITION, n_players=3)
		rnd = modes.start_competition_round(room)
		modes.submit_competition_guess(room, players[0].id, [0, 0, 0, 0])
		assert modes.competition_barrier_ready(room) is False
		modes.submit_competition_guess(room, players[1].id, [1, 1, 1, 1])
		assert modes.competition_barrier_ready(room) is False
		modes.submit_competition_guess(room, players[2].id, [2, 2, 2, 2])
		assert modes.competition_barrier_ready(room) is True

	def test_double_submit_rejected(self):
		room, players = make_room(MODE_COMPETITION)
		modes.start_competition_round(room)
		modes.submit_competition_guess(room, players[0].id, [0, 0, 0, 0])
		with pytest.raises(modes.GameError):
			modes.submit_competition_guess(room, players[0].id, [0, 0, 0, 0])

	def test_disconnected_player_does_not_block_barrier(self):
		room, players = make_room(MODE_COMPETITION, n_players=3)
		modes.start_competition_round(room)
		players[2].connected = False
		modes.submit_competition_guess(room, players[0].id, [0, 0, 0, 0])
		modes.submit_competition_guess(room, players[1].id, [1, 1, 1, 1])
		assert modes.competition_barrier_ready(room) is True

	def test_round_advances_when_no_one_solves(self):
		room, players = make_room(MODE_COMPETITION, n_players=2)
		rnd = modes.start_competition_round(room)
		# pick a guess guaranteed wrong: every slot differs from secret
		wrong = tuple((c + 1) % room.config.n_colors for c in rnd.secret)
		for p in players:
			modes.submit_competition_guess(room, p.id, list(wrong))
		out = modes.resolve_competition_barrier(room)
		assert out["round_over"] is False
		assert out["next_guess_no"] == 2
		assert rnd.guess_no == 2

	def test_first_to_crack_by_submission_order_wins(self):
		room, players = make_room(MODE_COMPETITION, n_players=2)
		rnd = modes.start_competition_round(room)
		secret = list(rnd.secret)
		# player[1] submits the correct code first, player[0] second
		modes.submit_competition_guess(room, players[1].id, secret)
		modes.submit_competition_guess(room, players[0].id, secret)
		out = modes.resolve_competition_barrier(room)
		assert out["round_over"] is True
		assert out["winner_id"] == players[1].id
		assert players[1].score == 1
		assert players[0].score == 0
		assert tuple(out["secret"]) == rnd.secret

	def test_no_winner_after_max_guesses(self):
		room, players = make_room(MODE_COMPETITION, n_players=2, max_guesses=2)
		rnd = modes.start_competition_round(room)
		wrong = tuple((c + 1) % room.config.n_colors for c in rnd.secret)
		for _ in range(room.config.max_guesses):
			for p in players:
				modes.submit_competition_guess(room, p.id, list(wrong))
			out = modes.resolve_competition_barrier(room)
		assert out["round_over"] is True
		assert out["winner_id"] is None


# ---------------------------------------------------------------------------
# Match lifecycle
# ---------------------------------------------------------------------------


class TestMatchLifecycle:
	def test_finish_round_detects_match_winner(self):
		room, players = make_room(MODE_COMPETITION, n_players=2, target_score=2)
		players[0].score = 2
		winner = modes.finish_round(room)
		assert winner is players[0]
		assert room.state == STATE_GAME_OVER

	def test_finish_round_continues_when_no_winner(self):
		room, players = make_room(MODE_COMPETITION, n_players=2, target_score=3)
		players[0].score = 1
		winner = modes.finish_round(room)
		assert winner is None
		assert room.state == STATE_ROUND_OVER
