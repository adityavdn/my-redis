"""Command handlers. Each takes (store, args) and returns a Python value
that resp.encode() turns into the reply."""
from .resp import OK, Error, SimpleString
from .store import now_ms

COMMANDS = {}
WRITE_COMMANDS = set()   # these get logged to the AOF


def command(name, arity, write=False):
    """Register a handler. arity = exact arg count; negative = 'at least N';
    None = any number."""
    def wrap(fn):
        COMMANDS[name] = (fn, arity)
        if write:
            WRITE_COMMANDS.add(name)
        return fn
    return wrap


def execute(store, parts):
    if not parts:
        return Error("ERR empty command")
    name = parts[0].upper().decode(errors="replace")
    args = parts[1:]
    if name not in COMMANDS:
        return Error(f"ERR unknown command '{name}'")
    fn, arity = COMMANDS[name]
    if arity is not None and ((arity >= 0 and len(args) != arity)
                              or (arity < 0 and len(args) < -arity)):
        return Error(f"ERR wrong number of arguments for '{name.lower()}' command")
    try:
        return fn(store, args)
    except ValueError:
        return Error("ERR value is not an integer or out of range")


def to_int(b: bytes) -> int:
    return int(b)


# ---- connection ----

@command("PING", None)
def ping(store, args):
    return args[0] if args else SimpleString("PONG")


@command("ECHO", 1)
def echo(store, args):
    return args[0]


# ---- strings ----

@command("SET", -2, write=True)
def set_(store, args):
    key, value, opts = args[0], args[1], [a.upper() for a in args[2:]]
    expire_at = None
    nx = xx = False
    i = 0
    while i < len(opts):
        opt = opts[i]
        if opt in (b"EX", b"PX") and i + 1 < len(opts):
            n = to_int(args[2 + i + 1])
            if n <= 0:
                return Error("ERR invalid expire time in 'set' command")
            expire_at = now_ms() + (n * 1000 if opt == b"EX" else n)
            i += 2
        elif opt == b"NX":
            nx, i = True, i + 1
        elif opt == b"XX":
            xx, i = True, i + 1
        else:
            return Error("ERR syntax error")
    exists = store.exists(key)
    if (nx and exists) or (xx and not exists):
        return None
    store.set(key, value, expire_at)
    return OK


@command("GET", 1)
def get(store, args):
    return store.get(args[0])


@command("DEL", -1, write=True)
def delete(store, args):
    return sum(store.delete(k) for k in args)


@command("EXISTS", -1)
def exists(store, args):
    return sum(store.exists(k) for k in args)


def _incr_by(store, key, delta):
    current = store.get(key)
    value = (to_int(current) if current is not None else 0) + delta
    exp = store.expires.get(key)            # INCR keeps the existing TTL
    store.set(key, str(value).encode(), exp)
    return value


@command("INCR", 1, write=True)
def incr(store, args):
    return _incr_by(store, args[0], 1)


@command("DECR", 1, write=True)
def decr(store, args):
    return _incr_by(store, args[0], -1)


@command("INCRBY", 2, write=True)
def incrby(store, args):
    return _incr_by(store, args[0], to_int(args[1]))


# ---- expiry ----

@command("EXPIRE", 2, write=True)
def expire(store, args):
    return store.set_expiry(args[0], now_ms() + to_int(args[1]) * 1000)


@command("PEXPIRE", 2, write=True)
def pexpire(store, args):
    return store.set_expiry(args[0], now_ms() + to_int(args[1]))


@command("PEXPIREAT", 2, write=True)
def pexpireat(store, args):
    return store.set_expiry(args[0], to_int(args[1]))


@command("TTL", 1)
def ttl(store, args):
    t = store.ttl_ms(args[0])
    return t if t < 0 else (t + 999) // 1000


@command("PTTL", 1)
def pttl(store, args):
    return store.ttl_ms(args[0])


@command("PERSIST", 1, write=True)
def persist(store, args):
    return store.persist(args[0])


# ---- keyspace ----

@command("KEYS", 1)
def keys(store, args):
    return store.keys(args[0])


@command("DBSIZE", 0)
def dbsize(store, args):
    return len(store.keys())


@command("FLUSHALL", None, write=True)
def flushall(store, args):
    store.flush()
    return OK


@command("COMMAND", None)
def command_(store, args):
    # redis-cli calls this on connect; an empty list keeps it happy
    return []


# ---- handshake commands that real client libraries send on connect ----

@command("HELLO", None)
def hello(store, args):
    if args and args[0] not in (b"2",):
        return Error("NOPROTO this server only speaks RESP2")
    # RESP2 has no map type, so a map is sent as a flat [key, value, ...] list
    return [b"server", b"pyredis", b"version", b"0.1.0", b"proto", 2,
            b"id", 1, b"mode", b"standalone", b"role", b"master", b"modules", []]


@command("CLIENT", -1)
def client(store, args):
    # CLIENT SETNAME / SETINFO: accept and ignore
    return OK


@command("SELECT", 1)
def select(store, args):
    return OK if args[0] == b"0" else Error("ERR only database 0 is supported")
