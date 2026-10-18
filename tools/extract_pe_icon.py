#!/usr/bin/env python3
"""Extracts icon resources from a Windows PE executable (no external tools).

Usage:
    extract_pe_icon.py <file.exe> [outdir]

Prints every RT_ICON/RT_GROUP_ICON entry it finds and writes each decoded
image as a PNG into <outdir> (default: alongside the exe).
"""
import os
import struct
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pngutil import write_png  # noqa: E402

RT_ICON = 3
RT_GROUP_ICON = 14


def parse_sections(data):
    e_lfanew = struct.unpack_from("<I", data, 0x3C)[0]
    if data[e_lfanew:e_lfanew + 4] != b"PE\0\0":
        raise SystemExit("not a PE file")
    coff = e_lfanew + 4
    num_sections = struct.unpack_from("<H", data, coff + 2)[0]
    size_opt = struct.unpack_from("<H", data, coff + 16)[0]
    opt = coff + 20
    magic = struct.unpack_from("<H", data, opt)[0]
    dd_off = opt + (96 if magic == 0x10B else 112)
    res_rva, res_size = struct.unpack_from("<II", data, dd_off + 2 * 8)

    sections = []
    sec_off = opt + size_opt
    for i in range(num_sections):
        s = sec_off + i * 40
        vsize, vaddr, rawsize, rawptr = struct.unpack_from("<IIII", data, s + 8)
        sections.append((vaddr, vsize, rawptr, rawsize))

    def rva_to_off(rva):
        for vaddr, vsize, rawptr, rawsize in sections:
            span = max(vsize, rawsize)
            if vaddr <= rva < vaddr + span:
                return rawptr + (rva - vaddr)
        return None

    return res_rva, rva_to_off


def walk_resources(data, base):
    """Returns {type_id: {name_id: (rva, size)}} following the 3-level tree."""
    out = {}

    def read_dir(off):
        n_named = struct.unpack_from("<H", data, base + off + 12)[0]
        n_id = struct.unpack_from("<H", data, base + off + 14)[0]
        entries = []
        p = base + off + 16
        for _ in range(n_named + n_id):
            name_or_id, data_off = struct.unpack_from("<II", data, p)
            p += 8
            entries.append((name_or_id, data_off))
        return entries

    for type_id, type_off in read_dir(0):
        if type_off & 0x80000000 == 0:
            continue
        names = {}
        for name_id, name_off in read_dir(type_off & 0x7FFFFFFF):
            if name_off & 0x80000000 == 0:
                continue
            langs = read_dir(name_off & 0x7FFFFFFF)
            if not langs:
                continue
            _, data_off = langs[0]
            if data_off & 0x80000000:
                continue
            rva, size = struct.unpack_from("<II", data, base + data_off)
            names[name_id & 0xFFFF] = (rva, size)
        out[type_id & 0xFFFF] = names
    return out


def dib_to_rgba(dib):
    (hdr_size, w, h2, planes, bpp, compression, size_image,
     _, _, _, _) = struct.unpack_from("<IiiHHIIiiII", dib, 0)
    h = h2 // 2
    palette = b""
    if bpp <= 8:
        count = 1 << bpp
        palette = dib[hdr_size:hdr_size + count * 4]
    pix_off = hdr_size + len(palette)

    xor_stride = ((w * bpp + 31) // 32) * 4
    and_stride = ((w + 31) // 32) * 4
    and_off = pix_off + xor_stride * h

    rgba = bytearray(w * h * 4)
    any_alpha = False
    for y in range(h):
        src = pix_off + (h - 1 - y) * xor_stride
        for x in range(w):
            if bpp == 32:
                b, g, r, a = dib[src + x * 4:src + x * 4 + 4]
            elif bpp == 24:
                b, g, r = dib[src + x * 3:src + x * 3 + 3]
                a = 255
            elif bpp == 8:
                idx = dib[src + x]
                b, g, r = palette[idx * 4:idx * 4 + 3]
                a = 255
            elif bpp == 4:
                byte = dib[src + x // 2]
                idx = (byte >> 4) if x % 2 == 0 else (byte & 0x0F)
                b, g, r = palette[idx * 4:idx * 4 + 3]
                a = 255
            elif bpp == 1:
                byte = dib[src + x // 8]
                idx = (byte >> (7 - x % 8)) & 1
                b, g, r = palette[idx * 4:idx * 4 + 3]
                a = 255
            else:
                raise SystemExit(f"unsupported bpp {bpp}")
            if a:
                any_alpha = True
            i = (y * w + x) * 4
            rgba[i:i + 4] = bytes((r, g, b, a))

    # Icons with a 32bpp image often leave alpha at 0 and rely on the AND mask.
    # For sub-32bpp images the AND mask is always the source of transparency.
    if bpp != 32 or not any_alpha:
        for y in range(h):
            row = and_off + (h - 1 - y) * and_stride
            for x in range(w):
                bit = (dib[row + x // 8] >> (7 - x % 8)) & 1
                rgba[(y * w + x) * 4 + 3] = 0 if bit else 255
    return w, h, rgba


def main():
    exe = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else os.path.dirname(os.path.abspath(exe))
    os.makedirs(outdir, exist_ok=True)
    data = open(exe, "rb").read()

    res_rva, rva_to_off = parse_sections(data)
    base = rva_to_off(res_rva)
    res = walk_resources(data, base)

    icons = res.get(RT_ICON, {})
    groups = res.get(RT_GROUP_ICON, {})
    print(f"RT_ICON entries: {sorted(icons)}")
    print(f"RT_GROUP_ICON entries: {sorted(groups)}")

    emitted = []
    for gid, (rva, size) in sorted(groups.items()):
        grp = data[rva_to_off(rva):rva_to_off(rva) + size]
        _, _, count = struct.unpack_from("<HHH", grp, 0)
        print(f"group {gid}: {count} image(s)")
        for i in range(count):
            e = 6 + i * 14
            (w, h, colors, _, planes, bpp, bytes_in_res, iid) = struct.unpack_from("<BBBBHHIH", grp, e)
            if iid not in icons:
                continue
            irva, isize = icons[iid]
            blob = data[rva_to_off(irva):rva_to_off(irva) + isize]
            if blob[:8] == b"\x89PNG\r\n\x1a\n":
                iw, ih, rgba = None, None, None
            else:
                iw, ih, rgba = dib_to_rgba(blob)
            name = f"icon_{gid}_{iid}_{iw or 'png'}x{ih or 'png'}.png"
            path = os.path.join(outdir, name)
            if rgba is not None:
                write_png(path, iw, ih, rgba)
            else:
                open(path, "wb").write(blob)
            print(f"  id={iid} {iw}x{ih} bpp={bpp} -> {name}")
            emitted.append((iw or 0, name, path))

    if not emitted:
        raise SystemExit("no icons extracted")
    emitted.sort()
    print("largest:", emitted[-1][1])


if __name__ == "__main__":
    main()
