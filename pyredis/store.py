"""The in-memory keyspace: a dict of values plus a dict of expiry times."""
import fnmatch
import random
import time


def now_ms() -> int:
    return int(time.time() * 1000)


class Store:
    def __init__(self):
        self.data = {}      # key (bytes) -> value (bytes)
        self.expires = {}   # key -> absolute expiry time in ms

    # Redis expires keys two ways:
    #  1. lazily: when you touch a key, check if it's dead first
    #  2. actively: a background job samples random keys and deletes dead ones,
    #     so keys nobody reads again don't sit in memory forever
    def _expired(self, key) -> bool:
        exp = self.expires.get(key)
        if exp is not None and now_ms() >= exp:
            self.delete(key)
            return True
        return False

    def get(self, key):
        if self._expired(key):
            return None
        return self.data.get(key)

    def set(self, key, value, expire_at_ms=None):
        self.data[key] = value
        if expire_at_ms is None:
            self.expires.pop(key, None)   # a plain SET clears any old TTL
        else:
            self.expires[key] = expire_at_ms

    def delete(self, key) -> bool:
        self.expires.pop(key, None)
        return self.data.pop(key, None) is not None

    def exists(self, key) -> bool:
        return not self._expired(key) and key in self.data

    def set_expiry(self, key, expire_at_ms) -> bool:
        if not self.exists(key):
            return False
        self.expires[key] = expire_at_ms
        return True

    def persist(self, key) -> bool:
        return self.exists(key) and self.expires.pop(key, None) is not None

    def ttl_ms(self, key) -> int:
        """-2 = no such key, -1 = key has no expiry (same as real Redis)."""
        if not self.exists(key):
            return -2
        exp = self.expires.get(key)
        return -1 if exp is None else max(exp - now_ms(), 0)

    def keys(self, pattern=b"*"):
        pat = pattern.decode()
        return [k for k in list(self.data) if not self._expired(k)
                and fnmatch.fnmatchcase(k.decode(errors="replace"), pat)]

    def flush(self):
        self.data.clear()
        self.expires.clear()

    def active_expire_cycle(self, sample_size=20):
        """Sample random keys with a TTL and delete expired ones."""
        if not self.expires:
            return 0
        sample = random.sample(list(self.expires), min(sample_size, len(self.expires)))
        return sum(self._expired(k) for k in sample)
