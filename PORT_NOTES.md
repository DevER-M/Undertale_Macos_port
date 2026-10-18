# Undertale → macOS native port (Butterscotch)

A native Apple-silicon build of Undertale v1.08, made from the Windows game you
supplied. No Wine, no Rosetta, no emulation — the GameMaker bytecode is executed
by an open-source native runner.

## What it is (and isn't)

Undertale is a **GameMaker: Studio 1.4** game. The `Undertale.exe` in the Windows
release is just YoYo's generic 4 MB runner; the game itself is VM **bytecode**
inside `data.win` (WAD Version 16). So this is *not* static recompilation of
native x86 — there is no game code in the `.exe` to lift.

Instead we use **Butterscotch**, an open-source C reimplementation of the
GameMaker runner, built with its native macOS (AppKit) backend. It loads your
`data.win` and streams the `.ogg` music from the game folder.

## Layout

```
Undertale.app/                     self-contained app (153 MB)
  Contents/
    Info.plist
    MacOS/Butterscotch             launcher script
    Resources/
      butterscotch                 the engine binary (arm64)
      Undertale.icns               app icon, extracted from Undertale.exe
      gamecontrollerdb.txt
      game/                        data.win + *.ogg + options.ini
butterscotch/                      engine source + out-of-source build
tools/                             icon helpers (PE icon extraction + .icns build)
```

## Running

Double-click `Undertale.app`, or from a terminal:

```sh
open Undertale.app
```

Saves go to `~/Library/Application Support/Undertale (Butterscotch)/`.

## macOS-native features

Beyond the plain runner, the AppKit backend and app bundle provide:

- **App icon** — the original Undertale SOUL heart, extracted from
  `Undertale.exe`'s PE icon resource (`tools/make_icon.py`).
- **View menu** — `Integer Scaling` (⌘⇧I) and `Take Screenshot` (⌘⇧S).
  Screenshots land in `<save folder>/screenshots/`.
- **Integer scaling** — the window is locked to the game's 4:3 aspect ratio and
  can only be resized in whole multiples of 640×480, so the game is always a
  pixel-exact, crisp integer upscale (2× on Retina).
- **Window state memory** — size/position are restored between launches.
- **Standard menus** — About, Services, Hide, Quit ⌘Q, plus the Window menu
  (Minimize, Zoom, Enter Full Screen ⌃⌘F).
- **Display stays awake** while the game is running (IOKit power assertion).
- **GameController** support for console pads.

## Renderers

OpenGL (`modern-gl`) is the default and only GPU backend. The native Metal
renderer that previously lived here has been removed — see "Metal renderer
(removed)" below.

## Verified

- `data.win` loads: WAD Version 16, 6509 functions mapped.
- Renderer initializes, all 26 texture pages load.
- 3600-frame headless run: no errors, no crashes.
- Windowed render confirmed against the intro cutscene (1280×960 = 2× of 640×480).
- Only **9 of 427** referenced functions are unimplemented (Steam Cloud calls like
  `steam_file_write_file`, plus `sprite_prefetch`, `draw_getpixel`,
  `sprite_replace`, `sprite_collision_mask`, etc.). Unknown calls are logged once
  and return a default, so the game continues.

## Rebuilding

```sh
export SDKROOT=/Applications/Xcode.app/Contents/Developer/Platforms/MacOSX.platform/Developer/SDKs/MacOSX.sdk
cd butterscotch
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release -DBACKEND=appkit
cmake --build build -j
```

**`SDKROOT` is required on this machine.** The Command Line Tools SDK (27.0) is
newer than Xcode 26.1's linker, so `xcrun` resolves to a `.tbd` that `ld` cannot
parse. Pointing `SDKROOT` at Xcode's own SDK fixes it. A permanent fix is to
reinstall matching Command Line Tools.

Then re-copy `butterscotch/build/butterscotch` into
`Undertale.app/Contents/Resources/`, and rebuild the icon with:

```sh
python3 tools/make_icon.py \
  "Undertale.v1.08/Undertale/Undertale.exe" tools/Undertale.icns
cp tools/Undertale.icns Undertale.app/Contents/Resources/Undertale.icns
codesign --force --deep --sign - Undertale.app
```

## Local engine changes

Changes made to Butterscotch itself:

- `src/vm_builtins.c` — implemented `texture_set_interpolation` /
  `texture_get_interpolation` (previously an unimplemented stub the game calls).
- `src/backends/appkit.m` — View menu, integer scaling, window-state memory,
  display-sleep assertion, plain window title, and removal of a dead
  "Settings…" menu item whose selector had no implementation.
- `CMakeLists.txt` — link `IOKit` (power assertion).

## Metal renderer (removed)

A native Metal backend was written and then removed again. The
`src/metal/` directory, the `ENABLE_METAL` CMake option and its
`Metal`/`QuartzCore`/`Foundation` framework links, the `METAL` value in the
`GraphicsAPI` enum, the `--renderer metal` argument, and the `MetalGameView`
plus `platformGetNativeView` hooks in the AppKit backend are all gone. The
binary no longer links Metal. Everything else (the GL path, the macOS-native
extras above) is untouched.

It was removed because of a whole-screen flicker/black-frame bug when dialogue
was on screen that could not be pinned down without running the game to
capture frames. The GL path renders that content correctly, so it was not
worth carrying a second backend with a known, undiagnosed defect. The bugs
found and fixed while it existed are recorded below for reference.

## Bugs found & fixed (Metal, since removed)

- **Gameplay freeze / stale screen (drawable leak).** The engine only calls
  `platformSwapBuffers()` (the present) when `runner->pendingRoom == -1`, so the
  present is skipped on every room change. `mtBeginFrame` used to overwrite the
  frame's `cmd`/`drawable` with `nil` without presenting or releasing them. Each
  skipped present permanently consumed one `CAMetalLayer` drawable; after 3 the
  pool was exhausted, `nextDrawable` blocked and returned `nil`, and the screen
  froze (only visible in a real window, which enforces the 3-drawable pool — it
  didn't show up in occluded/CLI runs). Fix: `mtBeginFrame` now presents any
  leftover command buffer/drawable before starting the new frame, keeping every
  acquired drawable balanced with a presentation.
- **Dropped screenshots.** Metal screenshots are written during the present, so a
  request landing on a skipped-present frame was silently dropped. `loop.c` now
  forces a present on the frame a Metal screenshot is requested.
- **`drawVertexBuffer` texture/texcoord divergence.** With a vertex format that
  has no texcoord attribute, GL keeps the bound texture and samples it at
  (0.5, 0.5); Metal wrongly substituted the white texture. Now matches GL.
- **Dialogue flicker (presentation latency).** The `CAMetalLayer` defaults to
  triple-buffering (3 drawables in flight) while GL is double-buffered. Combined
  with the offscreen app-surface → drawable composite, a changing message box /
  text landed 2–3 frames late and juddered. Now `maximumDrawableCount = 2` to
  match GL's latency.
- **`draw_clear` state divergence.** `mtClearScreen` force-reset the viewport and
  scissor to full-target and never restored the game's tracked values, whereas
  GL's `glClear` preserves them. Any `draw_clear` during dialogue transitions made
  the following draws use a wrong viewport (misaligned/flickering box).
  **Reverted:** restoring the tracked viewport made the dialogue box disappear
  entirely, and this was not the underlying cause. `mtClearScreen` again resets to
  the full target (and sets the missing `currentTargetWidth`).
- **Dialogue flicker (presentation ordering).** The offscreen app-surface →
  drawable composite was committed asynchronously, so the display could show
  frame N-1 or N depending on when the GPU caught up; a rapidly-changing element
  (the message box typing out) juddered/flickered between frames. GL's
  `flushBuffer` is effectively synchronous on the main thread, so `present()` now
  `waitUntilCompleted` after commit — exactly one frame in flight, deterministic
  presentation. Combined with `maximumDrawableCount = 2` this matches GL latency.
- **`endFrameEnd` host clear skipped (whole-screen flicker / blank frames).**
  GL's `glEndFrameEnd` (gl_renderer.c:982) *unconditionally* binds the host
  framebuffer and `glClear`s to black before blitting the application surface.
  Metal did not reliably match this: `Runner_drawPost` runs first targeting the
  host, so `mtSetTarget(HOST)` hit `mtBeginPass`'s early-return
  (`enc != nil && passTarget == HOST`) and the clear was silently skipped — letting
  drawPost's output survive underneath the letterbox composite, where GL wipes it.
  This only manifests in scenes where Draw POST events actually emit something
  (dialogue), which is why it showed up as whole-screen flicker / the screen
  sometimes being blank rather than as a localized artifact.
  **First attempt failed:** forcing the pass closed with `mtEndEncoder` alone made
  the dialogue box vanish, because `mtEndEncoder` does not emit queued vertices —
  the pending batch was silently discarded. Now `mtFlushBatch` runs *before*
  `mtEndEncoder`, so no draws are lost.
- **`present()` could drop the last batch.** `present()` ended the encoder without
  flushing `batchCount`, so any draws still queued at swap time were never encoded
  and the drawable was presented blank or half-drawn. It now flushes first.
- **Missing eager texture loading (root cause of the dialogue flicker).** Unlike
  GL, loop.c's startup eager-load loop had no Metal branch, so Metal lazily
  decoded each texture page *inside the draw that first needed it*. That
  mid-frame PNG/QOI decode caused irregular frame-time spikes — judder /
  perceived flicker — each time new content first appeared. It was worst early in
  the game (Flowey's first dialogue in the Ruins, where several pages load at
  once) and mostly gone by the time you reach Toriel, which is why only Flowey
  flickered. Added `MetalRenderer_ensureTextureLoaded` and wired it into the same
  eager-load loop GL uses, so pages decode at startup, never mid-frame.

## Notes

- The engine reads external files relative to the **directory containing
  `data.win`** — that's why the game bundle lives in `Resources/game/`.
- Engine backend: AppKit (Cocoa + GameController). Audio: miniaudio. Video
  playback: ffmpeg. Renderer: OpenGL 2.1 (Metal-backed) by default, with a
  native Metal renderer available via `--renderer metal`.
- Undertale's `data.win` contains an `AUDO` chunk (embedded audio) that the
  engine ignores, since music is streamed from the loose `.ogg` files.
- Engine: https://github.com/ButterscotchRunner/Butterscotch (AGPL-3.0).
  No game data is redistributed with the engine.
