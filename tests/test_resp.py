import unittest

from pyredis.resp import OK, Error, Parser, encode, encode_command


class TestParser(unittest.TestCase):
    def test_full_command(self):
        p = Parser()
        p.feed(b"*2\r\n$3\r\nGET\r\n$4\r\nname\r\n")
        self.assertEqual(p.get_command(), [b"GET", b"name"])
        self.assertIsNone(p.get_command())

    def test_partial_then_complete(self):
        msg = encode_command("SET", "k", "v")
        p = Parser()
        for i in range(len(msg) - 1):        # byte by byte: never complete early
            p.feed(msg[i:i + 1])
            self.assertIsNone(p.get_command())
        p.feed(msg[-1:])
        self.assertEqual(p.get_command(), [b"SET", b"k", b"v"])

    def test_pipelined_commands(self):
        p = Parser()
        p.feed(encode_command("PING") + encode_command("ECHO", "hi"))
        self.assertEqual(p.get_command(), [b"PING"])
        self.assertEqual(p.get_command(), [b"ECHO", b"hi"])

    def test_inline_command(self):
        p = Parser()
        p.feed(b"PING\r\n")
        self.assertEqual(p.get_command(), [b"PING"])

    def test_binary_safe(self):
        p = Parser()
        p.feed(encode_command("SET", "k", b"a\r\nb"))
        self.assertEqual(p.get_command()[2], b"a\r\nb")


class TestEncode(unittest.TestCase):
    def test_types(self):
        self.assertEqual(encode(OK), b"+OK\r\n")
        self.assertEqual(encode(Error("ERR x")), b"-ERR x\r\n")
        self.assertEqual(encode(42), b":42\r\n")
        self.assertEqual(encode(b"hi"), b"$2\r\nhi\r\n")
        self.assertEqual(encode(None), b"$-1\r\n")
        self.assertEqual(encode([b"a", 1]), b"*2\r\n$1\r\na\r\n:1\r\n")


if __name__ == "__main__":
    unittest.main()
