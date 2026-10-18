# Undertale for macOS - without wine

A native Apple-silicon build of Undertale v1.08 that replaces the previous
Wine-based approach.

**~1.7 GB → ~160 MB.** with no
compatibility layer, no x86 translation, and no emulation in the path.


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
cp tools/Undertale.icns ../Undertale.app/Contents/Resources/Undertale.icns
codesign --force --deep --sign - ../Undertale.app
```




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






## Credits and licensing

- Engine: [Butterscotch](https://github.com/ButterscotchRunner/Butterscotch) —
  **AGPL-3.0**.

Because the engine is AGPL-3.0, derivative distributions of this port carry the
same license obligation.
