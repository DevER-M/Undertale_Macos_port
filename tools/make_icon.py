#!/usr/bin/env python3
"""Builds the macOS app icon (.icns) from the icon embedded in the original
Undertale.exe.

The executable ships a single 16x16 4bpp icon (the red SOUL heart) whose
transparency lives in the AND mask. We decode it, upscale it with nearest
neighbour so the pixel art stays crisp, and pack a full .iconset.

Usage:
    make_icon.py <Undertale.exe> <out.icns>
"""
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from extract_pe_icon import (parse_sections, walk_resources,  # noqa: E402
                             dib_to_rgba, RT_ICON)
from pngutil import write_png  # noqa: E402


def resample(rgba, w, h, target):
    """Nearest-neighbour resample to a target square size (crisp pixel art)."""
    if target == w == h:
        return bytearray(rgba)
    out = bytearray(target * target * 4)
    for y in range(target):
        sy = min(h - 1, y * h // target)
        for x in range(target):
            sx = min(w - 1, x * w // target)
            s = (sy * w + sx) * 4
            d = (y * target + x) * 4
            out[d:d + 4] = rgba[s:s + 4]
    return out


def extract_base_icon(exe):
    data = open(exe, "rb").read()
    res_rva, rva_off = parse_sections(data)
    res = walk_resources(data, rva_off(res_rva))
    icons = res.get(RT_ICON, {})
    if not icons:
        raise SystemExit("no RT_ICON resource found")
    # Pick the largest RT_ICON image available.
    best = None
    for iid, (rva, size) in icons.items():
        blob = data[rva_off(rva):rva_off(rva) + size]
        if blob[:8] == b"\x89PNG\r\n\x1a\n":
            raise SystemExit("PNG-compressed icon resource not supported")
        w, h, rgba = dib_to_rgba(blob)
        if best is None or w * h > best[0] * best[1]:
            best = (w, h, rgba)
    return best


def main():
    exe = sys.argv[1]
    out_icns = sys.argv[2]
    w, h, rgba = extract_base_icon(exe)
    print(f"source icon: {w}x{h}")

    iconset = os.path.join(os.path.dirname(os.path.abspath(out_icns)), "Undertale.iconset")
    if os.path.isdir(iconset):
        shutil.rmtree(iconset)
    os.makedirs(iconset)

    plan = [
        (16, "icon_16x16.png"), (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"), (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"), (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"), (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"), (1024, "icon_512x512@2x.png"),
    ]
    for size, name in plan:
        write_png(os.path.join(iconset, name), size, size, resample(rgba, w, h, size))

    subprocess.run(["iconutil", "-c", "icns", iconset, "-o", out_icns], check=True)
    shutil.rmtree(iconset)
    print("wrote", out_icns)


if __name__ == "__main__":
    main()
