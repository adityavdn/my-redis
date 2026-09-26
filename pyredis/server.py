"""The TCP server.

Like real Redis, this runs on a single-threaded event loop (asyncio). While one
client is waiting on the network, the loop serves others, so we get
concurrency without threads — and without locks, because only one command
ever runs at a time.
"""
import asyncio
import logging

from .commands import WRITE_COMMANDS, execute
from .resp import Error, Parser, ProtocolError, encode
from .store import Store

log = logging.getLogger("pyredis")


class RedisServer:
    def __init__(self, host="127.0.0.1", port=6379, aof=None):
        self.host, self.port = host, port
        self.store = Store()
        self.aof = aof
        self._server = None

    async def handle_client(self, reader, writer):
        peer = writer.get_extra_info("peername")
        log.info("client connected: %s", peer)
        parser = Parser()
        try:
            while True:
                data = await reader.read(64 * 1024)
                if not data:                      # client closed the connection
                    break
                parser.feed(data)
                # A single read may contain several pipelined commands.
                while (cmd := parser.get_command()) is not None:
                    if not cmd:
                        continue
                    reply = execute(self.store, cmd)
                    name = cmd[0].upper().decode(errors="replace")
                    # Log successful writes. (SET NX/XX that didn't apply returns None.)
                    if (self.aof and name in WRITE_COMMANDS and not isinstance(reply, Error)
                            and not (name == "SET" and reply is None)):
                        self.aof.log(cmd, self.store)
                    writer.write(encode(reply))
                await writer.drain()
        except ProtocolError as e:
            writer.write(encode(Error(f"ERR Protocol error: {e}")))
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            log.info("client disconnected: %s", peer)
            writer.close()

    async def expire_loop(self):
        while True:
            await asyncio.sleep(0.1)          # 10 times a second, like Redis
            self.store.active_expire_cycle()

    async def start(self):
        if self.aof:
            n = self.aof.replay(self.store)
            log.info("loaded %d commands from AOF", n)
        self._server = await asyncio.start_server(self.handle_client, self.host, self.port)
        self._expirer = asyncio.create_task(self.expire_loop())
        log.info("PyRedis listening on %s:%d", self.host, self.port)

    async def serve_forever(self):
        await self.start()
        async with self._server:
            await self._server.serve_forever()

    async def stop(self):
        self._expirer.cancel()
        self._server.close()
        await self._server.wait_closed()
        if self.aof:
            self.aof.close()
