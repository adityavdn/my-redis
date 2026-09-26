"""Append-Only File persistence.

Everything lives in RAM, so a restart would wipe it. The AOF fixes that:
every write command is appended to a file in RESP format, and on startup
we replay the file to rebuild the data.

One subtlety: relative expiry. "EXPIRE key 60" means 60s from *now*; replayed
tomorrow it would wrongly give the key another 60s. So we rewrite relative
expiries into absolute timestamps (PEXPIREAT) before logging.
"""
import os

from .commands import execute
from .resp import Parser, encode_command

RELATIVE_EXPIRY = {b"EXPIRE", b"PEXPIRE"}


class AOF:
    def __init__(self, path):
        self.path = path
        self.file = None

    def replay(self, store) -> int:
        count = 0
        if os.path.exists(self.path):
            parser = Parser()
            with open(self.path, "rb") as f:
                parser.feed(f.read())
            while (cmd := parser.get_command()) is not None:
                execute(store, cmd)
                count += 1
        self.file = open(self.path, "ab")
        return count

    def log(self, cmd, store):
        name, key = cmd[0].upper(), cmd[1] if len(cmd) > 1 else None
        if name == b"SET":
            # log the plain SET, then the absolute expiry if one was set
            entries = [(b"SET", key, cmd[2])]
            if key in store.expires:
                entries.append((b"PEXPIREAT", key, store.expires[key]))
        elif name in RELATIVE_EXPIRY:
            entries = [(b"PEXPIREAT", key, store.expires[key])] if key in store.expires else []
        else:
            entries = [cmd]
        for e in entries:
            self.file.write(encode_command(*e))
        self.file.flush()   # hand to the OS right away; the OS writes it to disk

    def close(self):
        if self.file:
            self.file.flush()
            os.fsync(self.file.fileno())
            self.file.close()
