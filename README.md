# PyRedis

A Redis clone built from scratch in Python, using only the standard library.

It speaks the real Redis protocol (RESP2), so you can talk to it with `redis-cli`
or with the official `redis-py` client library.

## Features

- **RESP protocol parser.** Handles partial reads, pipelined commands and binary-safe values.
- **Single-threaded event loop.** Uses `asyncio`, the same concurrency model as real Redis.
- **Key expiry.** Both lazy (checked when a key is read) and active (a background job samples keys 10 times a second).
- **Persistence.** An append-only file (AOF) records writes and is replayed on startup. Relative TTLs are stored as absolute timestamps, so restarts don't extend key lifetimes.
- **Commands:**
  - Connection: `PING`, `ECHO`, `HELLO`, `CLIENT`, `SELECT`, `COMMAND`
  - Strings: `SET` (with `EX`/`PX`/`NX`/`XX`), `GET`, `DEL`, `EXISTS`, `INCR`, `DECR`, `INCRBY`
  - Expiry: `EXPIRE`, `PEXPIRE`, `PEXPIREAT`, `TTL`, `PTTL`, `PERSIST`
  - Keyspace: `KEYS`, `DBSIZE`, `FLUSHALL`

## Quick start

```bash
python3 -m pyredis                  # listens on 127.0.0.1:6379
python3 -m pyredis --port 6380 --aof ""   # custom port, persistence off
```

Then, in another terminal:

```bash
redis-cli ping                      # PONG
redis-cli set name Adi              # OK
redis-cli get name                  # "Adi"
redis-cli set session abc EX 60
redis-cli ttl session               # (integer) 60
```

Or from Python:

```python
import redis
r = redis.Redis(port=6379, protocol=2)
r.set("visits", 0)
r.incr("visits")
```

## How it works

```
client ──TCP──▶ server.py ──bytes──▶ resp.Parser ──[b"SET", b"k", b"v"]──▶ commands.execute()
                    ▲                                                          │
                    └──────────────── resp.encode(reply) ◀─────────────────────┤
                                                                               ▼
                                                              store.py (dict + expiry dict)
                                                                               │
                                                        write commands ──▶ aof.py (appendonly.aof)
```

| File | What it does |
|---|---|
| `pyredis/resp.py` | Parses incoming RESP bytes into commands and encodes replies |
| `pyredis/store.py` | The keyspace: a dict of values plus a dict of expiry timestamps |
| `pyredis/commands.py` | Command handlers, registered with a `@command` decorator |
| `pyredis/server.py` | The asyncio TCP server, per-client loop and background expiry job |
| `pyredis/aof.py` | Append-only file logging and replay |

## Tests

```bash
python3 -m unittest discover -s tests -t . -v
```

There are 17 tests: unit tests for the protocol parser, plus end-to-end tests that
start a real server and cover expiry, concurrency (10 clients at once) and
persistence across a restart.

## Roadmap

- [ ] Lists (`LPUSH`, `RPOP`, `LRANGE`)
- [ ] Hashes (`HSET`, `HGET`)
- [ ] Sorted sets (`ZADD`, `ZRANGE`)
- [ ] Pub/Sub
- [ ] RDB snapshots and AOF rewriting
- [ ] RESP3 protocol
