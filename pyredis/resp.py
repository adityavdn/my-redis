"""RESP (REdis Serialization Protocol) — parsing and encoding.

Every Redis message starts with a one-byte type marker and ends with \r\n:

    +OK\r\n                 simple string
    -ERR oops\r\n           error
    :42\r\n                 integer
    $5\r\nhello\r\n         bulk string (length-prefixed, binary-safe)
    $-1\r\n                 null
    *2\r\n$3\r\nGET\r\n$1\r\nk\r\n   array (clients send commands this way)
"""

CRLF = b"\r\n"


class ProtocolError(Exception):
    pass


class Parser:
    """Incremental parser.

    TCP delivers a stream of bytes, not neat messages: one read can hold half
    a command, or three commands at once. So we buffer bytes with feed() and
    pull complete commands out with get_command(), which returns None when the
    buffer doesn't yet hold a full command.
    """

    def __init__(self):
        self.buf = b""

    def feed(self, data: bytes):
        self.buf += data

    def get_command(self):
        if not self.buf:
            return None
        if self.buf[:1] == b"*":
            result = self._parse_array(0)
        else:
            result = self._parse_inline(0)  # e.g. "PING\r\n" typed via telnet/nc
        if result is None:
            return None
        command, pos = result
        self.buf = self.buf[pos:]
        return command

    def _read_line(self, pos):
        end = self.buf.find(CRLF, pos)
        if end == -1:
            return None
        return self.buf[pos:end], end + 2

    def _parse_inline(self, pos):
        line = self._read_line(pos)
        if line is None:
            return None
        text, pos = line
        return text.split(), pos

    def _parse_array(self, pos):
        line = self._read_line(pos + 1)          # skip the '*'
        if line is None:
            return None
        count, pos = int(line[0]), line[1]
        items = []
        for _ in range(count):
            if self.buf[pos:pos + 1] != b"$":
                if pos >= len(self.buf):
                    return None
                raise ProtocolError("expected bulk string")
            line = self._read_line(pos + 1)
            if line is None:
                return None
            length, pos = int(line[0]), line[1]
            if len(self.buf) < pos + length + 2:   # data not fully arrived yet
                return None
            items.append(self.buf[pos:pos + length])
            pos += length + 2
        return items, pos


# ---- Encoding (server -> client) ----

class SimpleString(str):
    """Marker type so encode() sends +OK instead of a bulk string."""


class Error(str):
    """Marker type so encode() sends -ERR ..."""


OK = SimpleString("OK")


def encode(value) -> bytes:
    if value is None:
        return b"$-1\r\n"
    if isinstance(value, Error):
        return b"-" + value.encode() + CRLF
    if isinstance(value, SimpleString):
        return b"+" + value.encode() + CRLF
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, int):
        return b":" + str(value).encode() + CRLF
    if isinstance(value, str):
        value = value.encode()
    if isinstance(value, bytes):
        return b"$" + str(len(value)).encode() + CRLF + value + CRLF
    if isinstance(value, (list, tuple)):
        return b"*" + str(len(value)).encode() + CRLF + b"".join(encode(v) for v in value)
    raise TypeError(f"cannot encode {type(value)}")


def encode_command(*args) -> bytes:
    """Encode a command the way a client sends it (used by tests and the AOF)."""
    parts = [a if isinstance(a, bytes) else str(a).encode() for a in args]
    return encode(parts)
