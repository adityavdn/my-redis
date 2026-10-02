# My Redis

A Redis-compatible in-memory server built from scratch in Python, designed to speak the RESP protocol and support core Redis-style behaviour.

## Overview

My Redis implements a lightweight server that can be interacted with using redis-cli and Python clients. It covers core command handling, key-value storage, expiry, persistence and event-loop based server execution.

## Key features

- RESP parsing and response encoding
- key-value storage
- TTL and expiry handling
- AOF persistence
- support for common Redis commands
- asyncio-based server design

## Tech Stack

- Python
- asyncio
- Redis protocol (RESP)

## How to run

```bash
python3 -m pyredis
python3 -m pyredis --port 6380 --aof ""
```

Then test with redis-cli or Python clients.

## Project structure

```text
.
├── pyredis/
├── tests/
├── README.md
└── supporting server files
```

