"""Run with:  python -m pyredis [--port 6379] [--aof appendonly.aof]"""
import argparse
import asyncio
import logging

from .aof import AOF
from .server import RedisServer


def main():
    ap = argparse.ArgumentParser(description="PyRedis — a Redis clone in Python")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=6379)
    ap.add_argument("--aof", default="appendonly.aof",
                    help="append-only file for persistence ('' to disable)")
    args = ap.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
    server = RedisServer(args.host, args.port, AOF(args.aof) if args.aof else None)
    try:
        asyncio.run(server.serve_forever())
    except KeyboardInterrupt:
        print("\nbye")


if __name__ == "__main__":
    main()
