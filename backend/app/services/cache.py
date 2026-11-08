"""Cache mémoire avec durée de vie, pour limiter les appels aux API externes.

Les clés sont des tuples dont le premier élément est le nom du service
("tmdb", "trakt", "plex"…), ce qui permet de vider un service entier.
"""

import time
from typing import Any

MISS = object()


class TTLCache:
    def __init__(self, maxsize: int = 5000):
        self.maxsize = maxsize
        self._data: dict[tuple, tuple[float, Any]] = {}

    def get(self, key: tuple) -> Any:
        entry = self._data.get(key)
        if entry is None:
            return MISS
        expires, value = entry
        if expires < time.monotonic():
            self._data.pop(key, None)
            return MISS
        return value

    def set(self, key: tuple, value: Any, ttl: float) -> None:
        if len(self._data) >= self.maxsize:
            now = time.monotonic()
            for k in [k for k, (exp, _) in self._data.items() if exp < now]:
                del self._data[k]
            while len(self._data) >= self.maxsize:
                self._data.pop(next(iter(self._data)))
        self._data[key] = (time.monotonic() + ttl, value)

    def clear(self, service: str | None = None) -> None:
        if service is None:
            self._data.clear()
        else:
            for k in [k for k in self._data if k and k[0] == service]:
                del self._data[k]


cache = TTLCache()
