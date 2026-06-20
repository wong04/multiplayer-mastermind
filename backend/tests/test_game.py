import pytest

from app.game import (
	generate_secret,
	is_solved,
	is_valid_guess,
	score_guess,
)


class TestGenerateSecret:
	def test_default_length_and_range(self):
		secret = generate_secret()
		assert len(secret) == 4
		assert all(0 <= c < 6 for c in secret)

	def test_custom_dimensions(self):
		secret = generate_secret(length=5, n_colors=8)
		assert len(secret) == 5
		assert all(0 <= c < 8 for c in secret)

	def test_invalid_args_raise(self):
		with pytest.raises(ValueError):
			generate_secret(length=0)
		with pytest.raises(ValueError):
			generate_secret(n_colors=0)


class TestScoreGuess:
	@pytest.mark.parametrize(
		"secret,guess,expected",
		[
			# perfect match
			((0, 1, 2, 3), (0, 1, 2, 3), (4, 0)),
			# all wrong colors
			((0, 0, 0, 0), (1, 1, 1, 1), (0, 0)),
			# all right colors, all wrong positions
			((0, 1, 2, 3), (3, 2, 1, 0), (0, 4)),
			# mix of black and white
			((0, 1, 2, 3), (0, 2, 1, 4), (1, 2)),
			# duplicates in secret, single in guess -> white capped at secret count
			((1, 1, 2, 3), (1, 0, 0, 0), (1, 0)),
			# duplicate guess against single secret occurrence -> only one peg
			((1, 2, 3, 4), (1, 1, 1, 1), (1, 0)),
			# duplicate-heavy: two of a color present in both
			((1, 1, 2, 2), (2, 2, 1, 1), (0, 4)),
			# partial duplicate overlap
			((1, 1, 1, 2), (1, 1, 2, 2), (3, 0)),
		],
	)
	def test_scoring(self, secret, guess, expected):
		assert score_guess(secret, guess) == expected

	def test_white_never_double_counts_blacks(self):
		# a black-matched color must not also be counted as white
		secret = (5, 5, 0, 1)
		guess = (5, 0, 5, 1)
		black, white = score_guess(secret, guess)
		assert black == 2  # positions 0 and 3
		# the second 5 (guess pos2 vs secret pos1) and the 0 (guess pos1 vs secret pos2)
		assert white == 2

	def test_length_mismatch_raises(self):
		with pytest.raises(ValueError):
			score_guess((0, 1, 2), (0, 1, 2, 3))


class TestValidation:
	def test_valid_guess(self):
		assert is_valid_guess([0, 1, 2, 3], length=4, n_colors=6)

	def test_wrong_length(self):
		assert not is_valid_guess([0, 1, 2], length=4, n_colors=6)

	def test_color_out_of_range(self):
		assert not is_valid_guess([0, 1, 2, 6], length=4, n_colors=6)
		assert not is_valid_guess([0, 1, 2, -1], length=4, n_colors=6)

	def test_non_int_rejected(self):
		assert not is_valid_guess([0, 1, 2, "3"], length=4, n_colors=6)

	def test_non_sequence_rejected(self):
		assert not is_valid_guess("0123", length=4, n_colors=6)


def test_is_solved():
	assert is_solved(4, 4)
	assert not is_solved(3, 4)
