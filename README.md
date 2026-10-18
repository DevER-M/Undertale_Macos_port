# Undertale for macOS — native port

A native Apple-silicon build of Undertale v1.08 that replaces the previous
Wine-based approach.

**~1.7 GB → ~160 MB.** Roughly a **10.6× reduction in footprint**, with no
compatibility layer, no x86 translation, and no emulation in the path.

> The 1.7 GB figure is from the previous Wine-based setup and is reported, not
> re-measured here — Wine is not installed on this machine. Every number in the
> breakdown below was measured directly against the shipped bundle. See
> [Honest caveats](#honest-caveats).

---

## Contents

- [What changed and why](#what-changed-and-why)
- [Size breakdown](#size-breakdown)
- [What "160 MB" actually consists of](#what-160-mb-actually-consists-of)
- [Changes on top of stock Butterscotch](#changes-on-top-of-stock-butterscotch)
- [Honest caveats](#honest-caveats)
- [Requirements](#requirements)
- [Building from source](#building-from-source)
- [Repository layout](#repository-layout)
- [Credits and licensing](#credits-and-licensing)

---

## What changed and why

### The old approach ran the game *on top of a Windows reimplementation*

`sikarugir/wine` ran the shipped `Undertale.exe` through Wine — a compatibility
layer that reimplements Win32, DirectX, the registry, and a large slice of the
Windows filesystem and threading model. On top of that, on Apple Silicon, the
x86 Windows binary needs a translation layer.

The result worked, but it bought a full Windows userland to render a game whose
actual content is 150 MB.

### The new approach doesn't emulate anything

Undertale is a **GameMaker: Studio 1.4** game. `Undertale.exe` is not the game —
it is YoYo's generic ~4 MB runner. The game itself is **VM bytecode inside
`data.win`** (WAD Version 16). There is no game code in the `.exe` to lift, so
this was never a case of "porting native x86".

Instead the port uses **[Butterscotch](https://github.com/ButterscotchRunner/Butterscotch)**,
an open-source C reimplementation of the GameMaker runner, built with its native
macOS (AppKit) backend. It reads `data.win` directly and executes the bytecode.
Music is streamed from the loose `.ogg` files.

### Where the savings come from

| | Wine approach | Native port |
|---|---|---|
| Windows compatibility layer | ~1 GB+ prefix, installed on first run | none |
| x86 → ARM translation | required (Rosetta/Wine-on-ARM) | none — compiled `arm64` |
| DirectX shims (DXVK/vkd3d) | required | none |
| Registry + Windows filesystem emulation | required | none |
| First-run setup | prefix creation, multi-minute, downloads | none |
| Game payload | 150 MB | 150 MB (unchanged) |
| Engine/runtime | Wine's runtime + the 4 MB `Undertale.exe` | 2.7 MB, single binary |

The last two rows are the important ones. **The game payload is identical in
both** — that 150 MB is the game, and any correct distribution has to ship it.
What the native port removes is everything *around* it: the compatibility
layer, the translation layer, and the duplicated runtime.

The single largest win is not bytes on disk but **first-run cost**. A Wine setup
downloads and builds a prefix before the game ever appears. This one is a
double-click.

---

## Size breakdown

Measured against the shipped bundle. Units are **decimal MB** (10⁶ bytes)
throughout, which is where the "160 MB" headline comes from.

| Component | Size | Bytes | Notes |
|---|---|---|---|
| **`Undertale.app` (total)** | **160 MB** | 160,267,311 | what you install |
| ├ `Resources/game/` | 157 MB | 156,731,986 | the game itself |
| │ ├ `data.win` | 63 MB | 62,921,978 | bytecode + textures |
| │ └ `*.ogg` | 94 MB | 212 files | music, streamed |
| ├ `Resources/butterscotch` | 2.8 MB | 2,844,480 | the entire engine, `arm64` Mach-O |
| └ `Resources/Undertale.icns` | 0.04 MB | 41,249 | icon, from `Undertale.exe` |
| **`Undertale-1.08-macOS.dmg`** | **132 MB** | 131,519,553 | compressed |

> For reference, the app bundle is 152.8 MiB / the DMG 125.4 MiB if you
> measure in binary units.

---

## What "160 MB" actually consists of

This is the part worth internalising:

```
160 MB  total app
├─157 MB  game data      ← irreducible; any port ships this
└─  3 MB  everything we wrote
```

**The port itself costs about 3 MB.** The 2.8 MB engine binary plus a 40 KB icon.
The other 157 MB is Undertale's own assets.

So the comparison is more precise than "1.7 GB vs 160 MB":

- **Wine approach:** ~1.7 GB of *infrastructure* to ship 157 MB of game.
- **Native port:** ~3 MB of *infrastructure* to ship the same 157 MB.

Roughly **98% of what ships is the game itself**, and the port's own code is
about **1.8%** of the download.

---

## Changes on top of stock Butterscotch

Stock Butterscotch already runs on macOS; these are the changes made for this
port.

**Engine fixes**

- Implemented `texture_set_interpolation` / `texture_get_interpolation` in
  `src/vm_builtins.c`. This was a dead stub the game actually calls. Unimplemented
  function count went **10 → 9** of 427 referenced functions.

**macOS-native integration** (`src/backends/appkit.m`)

- **App icon** — the original Undertale SOUL heart, extracted from
  `Undertale.exe`'s PE icon resource via `tools/make_icon.py`.
- **View menu** — `Integer Scaling` (⌘⇧I) and `Take Screenshot` (⌘⇧S).
- **Integer scaling** — window locked to the game's 4:3 aspect and resizable only
  in whole multiples of 640×480, so the game is always a pixel-exact crisp
  integer upscale (2× on Retina) instead of a blurry fractional resample.
- **Window state memory** — size and position restored between launches.
- **Standard menus** — About, Services, Hide, Quit ⌘Q, plus Window
  (Minimize, Zoom, Enter Full Screen ⌃⌘F).
- **Display stays awake** while running, via an IOKit power assertion.
- Removed a dead "Settings…" menu item whose selector had no implementation.

**Removed**

- A from-scratch native **Metal renderer** was written and then removed. It was
  bit-exact against the GL path but had a whole-screen flicker when dialogue was
  on screen that could not be diagnosed without running the game to capture
  frames. GL renders that content correctly, so carrying a second backend with a
  known defect was not worth it. The binary no longer links Metal. Details are in
  [`PORT_NOTES.md`](PORT_NOTES.md).

---

## Honest caveats

Things this README does not claim:

- **No FPS benchmark against the Wine version.** Wine is not installed on this
  machine, so no like-for-like runtime comparison was made. The port was verified
  to run at Undertale's native ~30 fps (the engine caps to the game's room speed;
  use `--speed N` or fast-forward ⇥ to go faster). Native rendering is expected to
  be faster and to avoid Wine's translation overhead, but that expectation is
  **not measured**.
- **The 1.7 GB is reported, not measured here.** It comes from the previous setup.
- **The app is ad-hoc signed, not notarized.** On another Mac, Gatekeeper will
  block it and it must be opened via right-click → Open (or
  `xattr -d com.apple.quarantine`). Fine locally or via AirDrop to someone who
  knows; not suitable for a public download.
- **Only 9 of 427 game functions are unimplemented** (mostly Steam Cloud calls
  like `steam_file_write_file`, plus `sprite_prefetch`, `draw_getpixel`,
  `sprite_replace`, `sprite_collision_mask`). Unknown calls are logged once and
  return a default, so the game continues.

---

## Requirements

- macOS on **Apple silicon** (`arm64`)
- **Your own copy of Undertale v1.08** — no game data is redistributed in this
  repository or in the DMG's git history. See the build step below for where the
  files go.

---

## Building from source

```sh
export SDKROOT=/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk

cd butterscotch
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DBACKEND=appkit
cmake --build build -j
```

`SDKROOT` is required on some machines: the Command Line Tools SDK can be newer
than the installed Xcode linker, so `xcrun` resolves to a `.tbd` that `ld` cannot
parse. Pointing `SDKROOT` at Xcode's own SDK fixes it.

Then drop the engine into the bundle and sign:

```sh
cp butterscotch/build/butterscotch ../Undertale.app/Contents/Resources/
codesign --force --deep --sign - ../Undertale.app
```

### Supplying the game files

The engine resolves game assets relative to the directory containing `data.win`.
Put your `data.win` and `*.ogg` files in `Undertale.app/Contents/Resources/game/`.

### Rebuilding the icon

```sh
python3 tools/make_icon.py \
  "Undertale.v1.08/Undertale/Undertale.exe" tools/Undertale.icns
cp tools/Undertale.icns ../Undertale.app/Contents/Resources/Undertale.icns
codesign --force --deep --sign - ../Undertale.app
```

---

## Repository layout

```
Undertale-1.08-macOS.dmg     distributable disk image
Undertale.app/               self-contained app (153 MB)
PORT_NOTES.md                detailed engineering notes, including the
                             full record of the removed Metal backend
butterscotch/                engine source + out-of-source build
tools/                       icon helpers (PE icon extraction → .icns)
```

Note: `butterscotch/` is tracked as ordinary source in this repo, not as a
submodule, so the port's modifications are visible in-tree.

---

## Credits and licensing

- Engine: [Butterscotch](https://github.com/ButterscotchRunner/Butterscotch) —
  **AGPL-3.0**.
- Undertale and its assets are the property of their respective owners. This
  repository contains **no game data**; `Undertale.app`, `data.win`, and the DMG
  are all excluded via `.gitignore`. You must supply your own copy of the game.

Because the engine is AGPL-3.0, derivative distributions of this port carry the
same license obligation.
