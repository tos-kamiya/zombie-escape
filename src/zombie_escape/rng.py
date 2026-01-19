"""Deterministic random number helpers for reproducible runs."""

from __future__ import annotations

import secrets
from typing import MutableSequence, Sequence, TypeVar

T = TypeVar("T")


def generate_seed() -> int:
    """Return a positive 63-bit seed for ad-hoc runs."""
    return secrets.randbits(63) or 1


class DeterministicRNG:
    """Mersenne Twister MT19937 implementation for deterministic runs."""

    _N = 624
    _M = 397
    _MATRIX_A = 0x9908B0DF
    _UPPER_MASK = 0x80000000
    _LOWER_MASK = 0x7FFFFFFF

    def __init__(self, seed: int | None = None) -> None:
        self._state = [0] * self._N
        self._index = self._N
        self.__seed_value: int | None = None
        self._seed(seed)

    def _seed(self, value: int | None) -> None:
        """Seed using the MT19937 initialization routine."""
        if value is None:
            value = generate_seed()
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Invalid seed value: {value}") from exc
        self.__seed_value = normalized
        seed32 = normalized & 0xFFFFFFFF
        if seed32 == 0:
            seed32 = 5489  # default MT seed
        self._state[0] = seed32
        for i in range(1, self._N):
            prev = self._state[i - 1]
            self._state[i] = (
                (1812433253 * (prev ^ (prev >> 30)) + i) & 0xFFFFFFFF
            )
        self._index = self._N

    @property
    def _seed_value(self) -> int | None:
        return self.__seed_value

    def random(self) -> float:
        """Return a float in the range [0.0, 1.0)."""
        return self._next() / 4294967296.0  # 2**32

    def randint(self, a: int, b: int) -> int:
        if a > b:
            raise ValueError("Lower bound must be <= upper bound for randint")
        return a + self._randbelow(b - a + 1)

    def choice(self, seq: Sequence[T]) -> T:
        if not seq:
            raise IndexError("Cannot choose from an empty sequence")
        idx = self._randbelow(len(seq))
        return seq[idx]

    def shuffle(self, seq: MutableSequence[T]) -> None:
        for i in range(len(seq) - 1, 0, -1):
            j = self._randbelow(i + 1)
            seq[i], seq[j] = seq[j], seq[i]

    def uniform(self, a: float, b: float) -> float:
        return a + (b - a) * self.random()

    def _next(self) -> int:
        return self._extract_number()

    def _randbelow(self, bound: int) -> int:
        if bound <= 0:
            raise ValueError("Upper bound must be positive")
        # Rejection sampling to avoid bias
        limit = (1 << 32) - ((1 << 32) % bound)
        while True:
            value = self._next()
            if value < limit:
                return value % bound

    def _extract_number(self) -> int:
        if self._index >= self._N:
            self._twist()
        y = self._state[self._index]
        self._index += 1
        y ^= (y >> 11)
        y ^= (y << 7) & 0x9D2C5680
        y ^= (y << 15) & 0xEFC60000
        y ^= (y >> 18)
        return y & 0xFFFFFFFF

    def _twist(self) -> None:
        for i in range(self._N):
            x = (self._state[i] & self._UPPER_MASK) + (
                self._state[(i + 1) % self._N] & self._LOWER_MASK
            )
            xA = x >> 1
            if x & 1:
                xA ^= self._MATRIX_A
            self._state[i] = self._state[(i + self._M) % self._N] ^ xA
        self._index = 0


_GLOBAL_RNG = DeterministicRNG()


def get_rng() -> DeterministicRNG:
    return _GLOBAL_RNG


def seed_rng(seed: int | None) -> int:
    _GLOBAL_RNG._seed(seed)
    assert _GLOBAL_RNG._seed_value is not None
    return _GLOBAL_RNG._seed_value


__all__ = [
    "DeterministicRNG",
    "generate_seed",
    "get_rng",
    "seed_rng",
]
