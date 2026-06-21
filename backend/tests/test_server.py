"""End-to-end WebSocket tests driving the real FastAPI app via TestClient."""

import pytest
from starlette.testclient import TestClient

from app import protocol as p
from app.main import app, registry


@pytest.fixture(autouse=True)
def clean_registry():
	registry._rooms.clear()
	yield
	registry._rooms.clear()


def recv_until(ws, type_):
	"""Read messages until one of the given type arrives, returning it."""
	for _ in range(20):
		msg = ws.receive_json()
		if msg["type"] == type_:
			return msg
	raise AssertionError(f"never received {type_}")


def create(ws, nickname, mode="classic"):
	ws.send_json({"type": p.CREATE_ROOM, "nickname": nickname, "mode": mode})
	joined = recv_until(ws, p.ROOM_JOINED)
	return joined


def join(ws, code, nickname):
	ws.send_json({"type": p.JOIN_ROOM, "room_code": code, "nickname": nickname})
	return recv_until(ws, p.ROOM_JOINED)


def test_create_and_join_flow():
	client = TestClient(app)
	with client.websocket_connect("/ws") as host, client.websocket_connect("/ws") as guest:
		hj = create(host, "alice")
		code = hj["room_code"]
		gj = join(guest, code, "bob")
		assert gj["room_code"] == code
		lobby = recv_until(guest, p.LOBBY_UPDATE)
		names = {pl["nickname"] for pl in lobby["players"]}
		assert names == {"alice", "bob"}


def test_competition_barrier_and_win():
	client = TestClient(app)
	with client.websocket_connect("/ws") as host, client.websocket_connect("/ws") as guest:
		hj = create(host, "alice", mode="competition")
		code = hj["room_code"]
		join(guest, code, "bob")

		host.send_json({"type": p.START_GAME})
		rs_host = recv_until(host, p.ROUND_START)
		recv_until(guest, p.ROUND_START)

		# Reach into server state to learn the secret (test-only shortcut).
		room = registry.get(code)
		secret = list(room.round.secret)

		# Host guesses wrong, guest guesses right -> guest wins this barrier.
		wrong = [(c + 1) % room.config.n_colors for c in secret]
		host.send_json({"type": p.SUBMIT_GUESS, "guess": wrong})
		recv_until(host, p.BARRIER_UPDATE)
		guest.send_json({"type": p.SUBMIT_GUESS, "guess": secret})

		over = recv_until(host, p.ROUND_OVER)
		assert over["secret"] == secret
		winner = over["winner_id"]
		guest_id = [pl["id"] for pl in over["scoreboard"] if pl["nickname"] == "bob"][0]
		assert winner == guest_id


def test_classic_codemaker_sets_secret_then_breaker_cracks():
	client = TestClient(app)
	with client.websocket_connect("/ws") as host, client.websocket_connect("/ws") as guest:
		hj = create(host, "alice", mode="classic")
		code = hj["room_code"]
		join(guest, code, "bob")

		host.send_json({"type": p.START_GAME})
		recv_until(host, p.ROUND_START)
		recv_until(guest, p.ROUND_START)

		room = registry.get(code)
		codemaker_id = room.round.codemaker_id
		cm_ws, br_ws = (host, guest) if codemaker_id == hj["player_id"] else (guest, host)

		cm_ws.send_json({"type": p.SET_SECRET, "secret": [0, 1, 2, 3]})
		recv_until(br_ws, p.ROUND_START)  # secret_set broadcast

		br_ws.send_json({"type": p.SUBMIT_GUESS, "guess": [0, 1, 2, 3]})
		fb = recv_until(br_ws, p.GUESS_FEEDBACK)
		assert fb["result"]["black"] == 4
		over = recv_until(br_ws, p.ROUND_OVER)
		assert over["reason"] == "cracked"


def test_solo_skips_lobby_and_auto_starts():
	client = TestClient(app)
	with client.websocket_connect("/ws") as solo:
		solo.send_json({
			"type": p.CREATE_ROOM,
			"nickname": "",
			"mode": "solo",
			"config": {"code_length": 5, "n_colors": 8, "max_guesses": 7},
		})
		joined = recv_until(solo, p.ROOM_JOINED)
		# No lobby — a round starts immediately with the chosen difficulty.
		rs = recv_until(solo, p.ROUND_START)
		assert rs["config"]["code_length"] == 5
		assert rs["config"]["n_colors"] == 8
		assert rs["config"]["max_guesses"] == 7

		room = registry.get(joined["room_code"])
		secret = list(room.round.secret)
		solo.send_json({"type": p.SUBMIT_GUESS, "guess": secret})
		recv_until(solo, p.GUESS_FEEDBACK)
		over = recv_until(solo, p.ROUND_OVER)
		assert over["reason"] == "cracked"


def test_daily_skips_lobby_with_shared_config():
	client = TestClient(app)
	with client.websocket_connect("/ws") as solo:
		solo.send_json({"type": p.CREATE_ROOM, "nickname": "", "mode": "daily"})
		recv_until(solo, p.ROOM_JOINED)
		rs = recv_until(solo, p.ROUND_START)
		# Daily forces the shared standard ruleset and carries a puzzle number.
		assert rs["config"]["code_length"] == 4
		assert rs["config"]["n_colors"] == 6
		assert rs["config"]["max_guesses"] == 10
		assert rs["daily_no"] >= 1


def test_restart_round_keeps_same_classic_codemaker():
	client = TestClient(app)
	with client.websocket_connect("/ws") as host, client.websocket_connect("/ws") as guest:
		hj = create(host, "alice", mode="classic")
		code = hj["room_code"]
		join(guest, code, "bob")

		host.send_json({"type": p.START_GAME})
		recv_until(host, p.ROUND_START)
		recv_until(guest, p.ROUND_START)

		room = registry.get(code)
		first_codemaker = room.round.codemaker_id

		host.send_json({"type": p.RESTART_ROUND})
		recv_until(host, p.ROUND_START)
		recv_until(guest, p.ROUND_START)

		assert room.round.codemaker_id == first_codemaker
