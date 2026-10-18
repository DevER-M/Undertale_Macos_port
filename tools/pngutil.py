#!/usr/bin/env python3
"""Minimal PNG writer (stdlib only)."""
import struct
import zlib


def write_png(path, width, height, rgba):
    """Writes an 8-bit RGBA PNG. `rgba` is a flat bytes/bytearray of w*h*4."""
    def chunk(tag, data):
        return (struct.pack(">I", len(data)) + tag + data +
                struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    raw = b"".join(b"\x00" + bytes(rgba[y * width * 4:(y + 1) * width * 4])
                   for y in range(height))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    png = (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) +
           chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)
