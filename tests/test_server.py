"""End-to-end tests: start a real server and talk to it over TCP."""
import asyncio
import os
import tempfile
import unittest

from pyredis.aof import AOF
from pyredis.resp import Parser, encode_command
from pyredis.server import RedisServer


class Client:
    """A tiny Redis client, just enough for testing."""

    async def connect(self, port):
        self.reader, self.writer = await asyncio.open_connection("127.0.0.1", port)

    async def call(self, *args):
        self.writer.write(encode_command(*args))
        await self.writer.drain()
        return await self._read_reply()

    async def _read_reply(self):
        line = (await self.reader.readline())[:-2]
        kind, rest = line[:1], line[1:]
        if kind == b"+":
            return rest.decode()
        if kind == b"-":
            return Exception(rest.decode())
        if kind == b":":
            return int(rest)
        if kind == b"$":
            n = int(rest)
            if n == -1:
                return None
            data = await self.reader.readexactly(n + 2)
            return data[:-2]
        if kind == b"*":
            return [await self._read_reply() for _ in range(int(rest))]
        raise ValueError(line)

    async def close(self):
        self.writer.close()
        await self.writer.wait_closed()


class ServerTest(unittest.IsolatedAsyncioTestCase):
    port = 6399

    async def asyncSetUp(self):
        self.tmp = tempfile.mkdtemp()
        self.aof_path = os.path.join(self.tmp, "test.aof")
        self.server = RedisServer(port=self.port, aof=AOF(self.aof_path))
        await self.server.start()
        self.c = Client()
        await self.c.connect(self.port)

    async def asyncTearDown(self):
        await self.c.close()
        await self.server.stop()

    async def test_ping_echo(self):
        self.assertEqual(await self.c.call("PING"), "PONG")
        self.assertEqual(await self.c.call("ECHO", "hey"), b"hey")

    async def test_set_get_del(self):
        self.assertEqual(await self.c.call("SET", "name", "Adi"), "OK")
        self.assertEqual(await self.c.call("GET", "name"), b"Adi")
        self.assertEqual(await self.c.call("EXISTS", "name", "nope"), 1)
        self.assertEqual(await self.c.call("DEL", "name"), 1)
        self.assertIsNone(await self.c.call("GET", "name"))

    async def test_set_nx_xx(self):
        self.assertIsNone(await self.c.call("SET", "k", "1", "XX"))
        self.assertEqual(await self.c.call("SET", "k", "1", "NX"), "OK")
        self.assertIsNone(await self.c.call("SET", "k", "2", "NX"))
        self.assertEqual(await self.c.call("GET", "k"), b"1")

    async def test_incr(self):
        self.assertEqual(await self.c.call("INCR", "n"), 1)
        self.assertEqual(await self.c.call("INCRBY", "n", "10"), 11)
        self.assertEqual(await self.c.call("DECR", "n"), 10)
        await self.c.call("SET", "s", "abc")
        self.assertIsInstance(await self.c.call("INCR", "s"), Exception)

    async def test_expiry(self):
        await self.c.call("SET", "temp", "x", "PX", "100")
        self.assertEqual(await self.c.call("GET", "temp"), b"x")
        self.assertGreater(await self.c.call("PTTL", "temp"), 0)
        await asyncio.sleep(0.15)
        self.assertIsNone(await self.c.call("GET", "temp"))
        self.assertEqual(await self.c.call("TTL", "temp"), -2)

    async def test_expire_and_persist(self):
        await self.c.call("SET", "k", "v")
        self.assertEqual(await self.c.call("TTL", "k"), -1)
        self.assertEqual(await self.c.call("EXPIRE", "k", "100"), 1)
        self.assertEqual(await self.c.call("TTL", "k"), 100)
        self.assertEqual(await self.c.call("PERSIST", "k"), 1)
        self.assertEqual(await self.c.call("TTL", "k"), -1)

    async def test_active_expiry_removes_untouched_keys(self):
        for i in range(10):
            await self.c.call("SET", f"k{i}", "v", "PX", "50")
        await asyncio.sleep(0.4)   # never read them; background job should clean up
        self.assertEqual(len(self.server.store.data), 0)

    async def test_keys_and_dbsize(self):
        for k in ("user:1", "user:2", "post:1"):
            await self.c.call("SET", k, "x")
        self.assertEqual(sorted(await self.c.call("KEYS", "user:*")), [b"user:1", b"user:2"])
        self.assertEqual(await self.c.call("DBSIZE"), 3)

    async def test_errors(self):
        self.assertIsInstance(await self.c.call("NOPE"), Exception)
        self.assertIsInstance(await self.c.call("GET"), Exception)

    async def test_many_clients(self):
        async def worker(i):
            c = Client()
            await c.connect(self.port)
            for _ in range(20):
                await c.call("INCR", "counter")
            await c.close()
        await asyncio.gather(*(worker(i) for i in range(10)))
        self.assertEqual(await self.c.call("GET", "counter"), b"200")

    async def test_persistence_survives_restart(self):
        await self.c.call("SET", "name", "Adi")
        await self.c.call("INCR", "visits")
        await self.c.call("SET", "session", "abc", "EX", "100")
        await self.c.call("SET", "name", "ignored", "NX")   # must not be logged
        await self.c.call("SET", "gone", "x")
        await self.c.call("DEL", "gone")

        # restart the server on the same AOF file
        await self.c.close()
        await self.server.stop()
        self.server = RedisServer(port=self.port, aof=AOF(self.aof_path))
        await self.server.start()
        self.c = Client()
        await self.c.connect(self.port)

        self.assertEqual(await self.c.call("GET", "name"), b"Adi")
        self.assertEqual(await self.c.call("GET", "visits"), b"1")
        self.assertIsNone(await self.c.call("GET", "gone"))
        self.assertTrue(0 < await self.c.call("TTL", "session") <= 100)


if __name__ == "__main__":
    unittest.main()
