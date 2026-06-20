import pytest

from app.rooms import (
	MAX_PLAYERS,
	STATE_IN_ROUND,
	GameAlreadyStarted,
	InvalidNickname,
	RoomFull,
	RoomNotFound,
	RoomRegistry,
)


@pytest.fixture
def registry():
	return RoomRegistry()


class TestCreateAndJoin:
	def test_create_room_makes_host(self, registry):
		room, host = registry.create_room("alice")
		assert host.nickname == "alice"
		assert room.host_id == host.id
		assert len(room.code) == 4
		assert room.players == {host.id: host}

	def test_join_by_code_is_case_insensitive(self, registry):
		room, _ = registry.create_room("alice")
		joined, bob = registry.join_room(room.code.lower(), "bob")
		assert joined is room
		assert bob.nickname == "bob"
		assert len(room.players) == 2

	def test_join_unknown_room_raises(self, registry):
		with pytest.raises(RoomNotFound):
			registry.join_room("ZZZZ", "bob")

	def test_each_player_gets_unique_id_and_token(self, registry):
		room, host = registry.create_room("alice")
		_, bob = registry.join_room(room.code, "bob")
		assert host.id != bob.id
		assert host.token != bob.token


class TestCapacityAndState:
	def test_room_full_at_max(self, registry):
		room, _ = registry.create_room("p0")
		for i in range(1, MAX_PLAYERS):
			registry.join_room(room.code, f"p{i}")
		assert len(room.players) == MAX_PLAYERS
		with pytest.raises(RoomFull):
			registry.join_room(room.code, "overflow")

	def test_cannot_join_started_game(self, registry):
		room, _ = registry.create_room("alice")
		room.state = STATE_IN_ROUND
		with pytest.raises(GameAlreadyStarted):
			registry.join_room(room.code, "bob")

	def test_empty_nickname_rejected(self, registry):
		with pytest.raises(InvalidNickname):
			registry.create_room("   ")


class TestMembershipHelpers:
	def test_reconnect_lookup_by_token(self, registry):
		room, host = registry.create_room("alice")
		assert room.get_player_by_token(host.token) is host
		assert room.get_player_by_token("nope") is None

	def test_connected_players_excludes_disconnected(self, registry):
		room, host = registry.create_room("alice")
		_, bob = registry.join_room(room.code, "bob")
		bob.connected = False
		assert room.connected_players() == [host]

	def test_winner_by_score(self, registry):
		room, host = registry.create_room("alice")
		_, bob = registry.join_room(room.code, "bob")
		assert room.winner_by_score() is None
		bob.score = room.config.target_score
		assert room.winner_by_score() is bob

	def test_prune_empty_rooms(self, registry):
		room, host = registry.create_room("alice")
		room.remove_player(host.id)
		assert room.is_empty()
		registry.prune_empty()
		assert registry.get(room.code) is None
