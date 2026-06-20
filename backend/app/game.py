"""Pure Mastermind game logic — no I/O, no state. Fully unit-testable."""

from __future__ import annotations

import secrets
from collections import Counter

DEFAULT_CODE_LENGTH = 4
DEFAULT_NUM_COLORS = 6


def generate_secret(length: int = DEFAULT_CODE_LENGTH, n_colors: int = DEFAULT_NUM_COLORS) -> tuple[int, ...]:
	"""Return a random secret code of `length` slots, each a color in [0, n_colors).

	Duplicates are allowed. Uses the `secrets` module so codes aren't predictable.
	"""
	if length < 1:
		raise ValueError(f"length must be >= 1, got {length}")
	if n_colors < 1:
		raise ValueError(f"n_colors must be >= 1, got {n_colors}")
	return tuple(secrets.randbelow(n_colors) for _ in range(length))


def is_valid_guess(guess: object, length: int, n_colors: int) -> bool:
	"""True if `guess` is a sequence of `length` ints, each a valid color in [0, n_colors)."""
	if not isinstance(guess, (list, tuple)):
		return False
	if len(guess) != length:
		return False
	return all(isinstance(c, int) and 0 <= c < n_colors for c in guess)


def score_guess(secret: tuple[int, ...], guess: tuple[int, ...]) -> tuple[int, int]:
	"""Score a guess against the secret.

	Returns (black, white):
	  - black: slots with the right color in the right position.
	  - white: right color in the wrong position (each peg counted once,
	    duplicates handled via per-color min counts).
	"""
	if len(secret) != len(guess):
		raise ValueError("secret and guess must be the same length")

	black = sum(s == g for s, g in zip(secret, guess))

	secret_counts = Counter(secret)
	guess_counts = Counter(guess)
	total_matches = sum((secret_counts & guess_counts).values())

	white = total_matches - black
	return black, white


def score_guess_per_slot(secret: tuple[int, ...], guess: tuple[int, ...]) -> list[str]:
	"""Return per-slot feedback: "exact", "present", or "absent" for each position.

	Handles duplicates correctly: a color is only marked "present" as many times as
	it appears in the secret, minus the number of exact matches for that color.
	"""
	if len(secret) != len(guess):
		raise ValueError("secret and guess must be the same length")
	length = len(secret)
	result: list[str | None] = [None] * length
	secret_pool = list(secret)
	guess_pool = list(guess)

	for i in range(length):
		if secret[i] == guess[i]:
			result[i] = "exact"
			secret_pool[i] = None
			guess_pool[i] = None

	for i in range(length):
		if result[i] is not None:
			continue
		g = guess_pool[i]
		if g is not None and g in secret_pool:
			result[i] = "present"
			secret_pool[secret_pool.index(g)] = None
		else:
			result[i] = "absent"

	return result  # type: ignore[return-value]


def is_solved(black: int, length: int) -> bool:
	"""True when every slot is correct."""
	return black == length
