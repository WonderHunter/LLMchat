import math
import time
from collections import deque

from fastapi import HTTPException, status


class RateLimiter:
    """Compte des événements par clé sur une fenêtre glissante, en mémoire.

    Suffisant pour un serveur à un seul processus ; avec plusieurs processus ou plusieurs
    machines, chaque instance aurait son propre compteur.
    """

    _MAX_KEYS = 50_000

    def __init__(self, limit: int, window_seconds: int):
        self.limit = limit
        self.window = window_seconds
        self._events: dict[str, deque[float]] = {}
        self.now = time.monotonic

    def _recent(self, key: str) -> deque[float]:
        events = self._events.get(key)
        if events is None:
            return deque()
        threshold = self.now() - self.window
        while events and events[0] <= threshold:
            events.popleft()
        if not events:
            del self._events[key]
        return events

    def retry_after(self, key: str) -> int | None:
        """Secondes à attendre si la limite est atteinte, sinon None."""
        events = self._recent(key)
        if len(events) < self.limit:
            return None
        return max(1, math.ceil(events[0] + self.window - self.now()))

    def record(self, key: str) -> None:
        if len(self._events) >= self._MAX_KEYS:
            for stale in list(self._events):
                self._recent(stale)
        self._events.setdefault(key, deque()).append(self.now())

    def forget(self, key: str) -> None:
        self._events.pop(key, None)

    def clear(self) -> None:
        self._events.clear()


def too_many(retry_after: int) -> HTTPException:
    minutes = math.ceil(retry_after / 60)
    wait = "une minute" if minutes <= 1 else f"{minutes} minutes"
    return HTTPException(
        status.HTTP_429_TOO_MANY_REQUESTS,
        f"Trop de tentatives. Réessayez dans {wait}.",
        headers={"Retry-After": str(retry_after)},
    )


_QUARTER_HOUR = 15 * 60

# Échecs de connexion : par adresse (attaque large) et par compte visé (attaque ciblée).
login_failures_by_ip = RateLimiter(limit=20, window_seconds=_QUARTER_HOUR)
login_failures_by_email = RateLimiter(limit=8, window_seconds=_QUARTER_HOUR)
# Créations de compte par adresse.
registrations_by_ip = RateLimiter(limit=5, window_seconds=60 * 60)

ALL_LIMITERS = (login_failures_by_ip, login_failures_by_email, registrations_by_ip)
