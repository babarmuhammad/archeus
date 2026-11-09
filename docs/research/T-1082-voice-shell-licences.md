# T-1082 — Licence and notice plan: the desktop shell and a future voice extra (note only)

Card **T-1082** · date **2026-11-09** · snapshot: this container's checkout of the MXC
integration branch; the package is `name = "archeus"`, `version = "2.8.1"`
(`pyproject.toml:6,11`). `git` is not installed in this container, so no commit hash could be
read for the snapshot line.

> **Caveat.** Facts **F1–F24** are quoted from the project's own research reports of
> 2026-11-09 and are **not verified here** — this container has no network and no package
> index. Nothing in this file is legal advice. Every licence word below carries a
> `file:line` opened in this checkout, an `F<n>`, an `[?]` (could not be sourced from this
> container) or an `[I]` (my inference). **This note changes nothing**: `docs/credits.md`,
> `pyproject.toml`, `mkdocs.yml`, every source and every test file are untouched. The credits
> entries in §6 are *listed*, never applied. Nothing of the voice work is built, and nothing
> of it enters V1 (F20).

Location note: `docs/research/` is excluded from the published site by `mkdocs.yml:26-33`
(`exclude_docs:` … `/research/`), so no nav change is needed for this file.

---

## 0. What the repository says today (quoted, as read)

`pyproject.toml`:

- `pyproject.toml:1-2` — `[build-system]` / `requires = ["setuptools>=61"]`
  (line 3 `build-backend = "setuptools.build_meta"`).
- `pyproject.toml:14-15` — `requires-python = ">=3.10"` and `license = { text = "MIT" }`
  (and `pyproject.toml:31` classifier `"License :: OSI Approved :: MIT License"`).
- `pyproject.toml:79-81` —

  ```toml
  [project.optional-dependencies]
  dev = ["pytest"]
  gui = ["PyQt6", "PyQt6-WebEngine"]   # optional native desktop shell (gui_qt.py)
  ```

- `pyproject.toml:120-136` — `[tool.setuptools.package-data]`, with the vendor globs at
  `pyproject.toml:122-127`:

  ```toml
  # web/vendor/** is three.js + anime.js (both MIT, vendored so the GUI stays
  # offline); the nested globs are needed because package-data does not recurse.
  claude_sessions = [
      "web/*.html", "web/*.css", "web/*.js",
      "web/vendor/*.js", "web/vendor/*.txt",
      "web/vendor/*/*.js",
  ```

- Verify command run in this container (as the card allows):

  ```
  $ grep -n "dependencies" pyproject.toml
  79:[project.optional-dependencies]
  $ grep -n "vendor" pyproject.toml
  20:# not about one vendor's CLI. `claude-code` stays, because that IS the surface.
  122:# web/vendor/** is three.js + anime.js (both MIT, vendored so the GUI stays
  126:    "web/vendor/*.js", "web/vendor/*.txt",
  127:    "web/vendor/*/*.js",
  ```

  The only hit for `dependencies` is the `[project.optional-dependencies]` header itself:
  there is **no `dependencies = [...]` entry in `[project]`**, so the installed package ships
  zero runtime dependencies (matching `CONTRIBUTING.md:144` "Zero runtime dependencies.
  Everything the installed package imports comes from the standard library").

`claude_sessions/gui_qt.py`:

- `gui_qt.py:1-6` — module docstring: *"Native desktop shell for the archeus GUI — a PyQt6
  window hosting the local web app … PyQt6 is an OPTIONAL dependency: gui.run_gui() only
  calls run_desktop() when the import succeeds, falling back to an Edge app-mode window, then
  the default browser."*
- `gui_qt.py:46-50` — `def run_desktop(on_ready=None)`: *"Serve the GUI and show it in a
  native Qt window. Blocks until the window closes. Raises ImportError if PyQt6/WebEngine is
  unavailable — caller falls back."* (The card points at "lines 44-50"; the function opens at
  line 46 in this snapshot.)
- `gui_qt.py:76-79` — `from PyQt6.QtWidgets import QApplication, QMainWindow` /
  `from PyQt6.QtWebEngineWidgets import QWebEngineView` / `from PyQt6.QtGui import …` /
  `from PyQt6.QtCore import …`.
- `gui_qt.py:166-170` — `from PyQt6.QtCore …` / `PyQt6.QtGui …` /
  `PyQt6.QtWebEngineCore import QWebEnginePage, QWebEngineProfile` /
  `PyQt6.QtWebEngineWidgets …` / `PyQt6.QtWidgets …`.
  → the shell is **in-process**: Archeus's own Python code imports PyQt6 and runs in the same
  process, hosting the local web GUI (`gui_qt.py:80-86` starts the server in that process).
- The fallback is real code, not prose: `claude_sessions/gui.py:1065-1081` —
  *"'auto' tries PyQt6 native window → Edge app-mode window → browser tab"*, with
  `except ImportError:` at `gui.py:1079` and `print('  PyQt6 not installed — falling back')`.
- Vendor serving: `gui.py:719-727` `_serve_vendor` — *"Vendored browser libraries (three.js,
  anime.js) … these are public MIT libraries, byte-identical to their npm originals"*.

`CONTRIBUTING.md:144-147` — *"**Zero runtime dependencies.** Everything the installed package
imports comes from the standard library. Test, docs and build tooling live in their own
install steps — `requirements-docs.txt` and the CI job that needs them — never in
`pyproject.toml`. **PyQt6 is the one optional extra**, and the GUI falls back to the browser
without it."*

`docs/desktop.md:17` — *"**Shells** — PyQt6 native window if installed, else an Edge app-mode
window, else the browser (`gui_shell` setting: auto / qt / edge / browser)."* (and
`docs/desktop.md:12-13` — *"No Python dependencies; the browser bundle vendors three.js and
anime.js (both MIT, served from `/vendor/`, never a CDN)"*).

`docs/installation.md:152-159` — *"### GUI setup / The [desktop app](desktop.md) needs no
extra dependencies for the Edge/browser shells. For the native window install PyQt6
(optional): `pip install PyQt6 PyQt6-WebEngine`"* → the toolkit arrives through the **user's
own pip install**, which is the easy LGPL case (F23).

`requirements-docs.txt:1-4` — *"Documentation site only. Deliberately NOT in pyproject.toml —
archeus ships zero runtime dependencies…"* / `mkdocs-material>=9.5`. Docs tooling, not a
dependency of the package.

`claude_sessions/web/vendor/` — contains `LICENSE-anime.txt`, `LICENSE-three.txt`,
`anime.esm.min.js`, `three.core.min.js`, `three.module.min.js`, `postprocessing/`
(7 `.js` files: EffectComposer, MaskPass, OutputPass, Pass, RenderPass, ShaderPass,
UnrealBloomPass) and `shaders/` (3 `.js` files: CopyShader, LuminosityHighPassShader,
OutputShader). Heads as read:

- `LICENSE-three.txt:1-3` — *"The MIT License" / "Copyright © 2010-2026 three.js authors"*.
  `three.core.min.js:1-5` header — *"@license / Copyright 2010-2026 Three.js Authors /
  SPDX-License-Identifier: MIT"*.
- `LICENSE-anime.txt:1-3` — *"The MIT License" / "Copyright (c) 2025 Julian Garnier"*.
  `anime.esm.min.js:1-6` header — *"@version v4.5.0 / @license MIT / @copyright 2026 -
  Julian Garnier"*.
- All 10 files under `postprocessing/` and `shaders/` were opened: **none carries a
  `@license`, `SPDX` or copyright header** (e.g. `postprocessing/EffectComposer.js:1-8`
  imports from `'three'` and `'../shaders/CopyShader.js'`; `shaders/CopyShader.js:1-4` says
  `@module CopyShader` / `@three_import import { CopyShader } from
  'three/addons/shaders/CopyShader.js'`). Their licence is therefore `[?]` here, i.e. reported
  as three.js-MIT-by-inheritance `[I]`, not read.

`LICENSE:1-3` — *"MIT License / Copyright (c) 2026 Babar Muhammad Anas"* (project's own).
`docs/credits.md` — 43 lines; the only licence sentence is line 43 *"archeus itself is MIT
licensed."*; `grep -i` for `pyqt|three|anime|whisper|voice|licen[cs]e` in that file returns
only that line → no entry exists for PyQt6, the vendored three.js/anime.js, or any voice
component, and the file has no licence column (it is a bullet list, `docs/credits.md:22-32`).

`clients/app/package.json` — lists npm packages (`qrcode-generator` 2.0.4, `react` 19.3.0,
`react-dom` 19.3.0; dev: typescript, vite, axe-core, @types/*). They exist, they are
build-time inputs of the V1 SPA, and they are **not analysed by this card** (out of scope).

---

## Table A — What the repository ships or lists today

| component | licence (read here, or fact id) | how linked / run | obligation | blocks shipping, or open | source |
|---|---|---|---|---|---|
| archeus itself | MIT (read) | the installed package | MIT notice + copyright must travel with copies (`LICENSE:12-13`) | open: nothing | `LICENSE:1-3,12-13`; `pyproject.toml:15,31` |
| setuptools (`[build-system] requires`) | not read in this container `[?]` | build tool (PEP 517 backend at build time; not imported at run time, not shipped) | none for the wheel | nothing blocks | `pyproject.toml:2-3` |
| pytest (`dev` extra) | not read in this container `[?]` | dev extra, installed by the developer; not shipped, not imported at run time | none for the wheel | nothing blocks (but see Observations: `dev = ["pytest"]` vs `CONTRIBUTING.md:144-146`) | `pyproject.toml:80`; `CONTRIBUTING.md:144-146` |
| PyQt6 (`gui` extra) | GPLv3 **or** commercial `[?]` — F2 is the researcher's background knowledge, not re-verified | **in-process import**: Archeus's own Python code imports PyQt6 in its own process and hosts the web GUI; installed by the user's own `pip install` (the easy LGPL case, F23) | nothing to ship while it stays an extra the user installs; a frozen single-file build would need a relink path (F23/F1) — and PyQt6 being GPL/commercial `[?]` means there is no LGPL relink story, only the commercial licence | open: the swap to PySide6 is owner decision item 97, **not taken by this card** (F1/F2); today the shell already degrades to Edge/browser without it | `pyproject.toml:81`; `gui_qt.py:76-79,166-170`; `gui.py:1065-1081`; F2, F23 |
| PyQt6-WebEngine (`gui` extra) | `[?]` — F22: the WebEngine/Chromium licences are not covered by the reports | **in-process import** (`QWebEngineView`, `QWebEnginePage`, `QWebEngineProfile`) | unverified `[?]`: if bundled, a Chromium-side notice set would have to ship | blocks shipping until the engine's own licence files are read from an installed wheel (possible offline on the review machine, F19: read the LICENSE file, not the GitHub field) | `pyproject.toml:81`; `gui_qt.py:77,168-169`; F22, F19 |
| three.js, vendored (`three.core.min.js`, `three.module.min.js`) | "The MIT License", Copyright © 2010-2026 three.js authors (read) | vendored file inside the wheel (`package-data` `web/vendor/*.js`), served locally from `/vendor/`, never a CDN | keep the copyright + permission notice with the copies (MIT condition); satisfied today — `web/vendor/*.txt` is in `package-data`, so `LICENSE-three.txt` ships | nothing open | `claude_sessions/web/vendor/LICENSE-three.txt:1-3`; `three.core.min.js:1-5`; `pyproject.toml:126-127`; `gui.py:719-727` |
| anime.js, vendored (`anime.esm.min.js`, v4.5.0 header) | "The MIT License", Copyright (c) 2025 Julian Garnier (read) | vendored file inside the wheel, same globs | keep the notice; ships with `web/vendor/*.txt` | nothing open (year mismatch noted in Observations) | `LICENSE-anime.txt:1-3`; `anime.esm.min.js:1-6`; `pyproject.toml:126-127` |
| `web/vendor/postprocessing/` (7 addons) | `[?]` — no licence/SPDX/copyright header in any of the 7 files (all opened); three.js-MIT-by-inheritance `[I]`; the covering file, if any, is `LICENSE-three.txt` | vendored files inside the wheel (`web/vendor/*/*.js`) | if they are the three.js addons, the same MIT notice covers them `[?]`; confirm before release | blocks: the `[?]` above. They `import … from 'three'`, so they are useless without the vendored three.js | `postprocessing/EffectComposer.js:1-8`; `pyproject.toml:127` |
| `web/vendor/shaders/` (3 shaders) | `[?]` — same: headers say `@module` / `@three_import … 'three/addons/…'`, no licence | vendored files inside the wheel | same as above `[?]` | blocks: the `[?]` above | `shaders/CopyShader.js:1-4`; `pyproject.toml:127` |
| mkdocs-material | not analysed; licence not read `[?]` | docs-site build tool (own CI install step), **not** a dependency of the package, not shipped | none for the wheel | nothing blocks | `requirements-docs.txt:1-4` |

One line on the SPA: `clients/app/package.json` lists npm packages (react, react-dom,
qrcode-generator; dev tools) — they exist as build-time inputs of the V1 SPA and are not
analysed here (out of scope).

---

## Table B — A future voice extra (**not built**; research only, F20: nothing of voice
### enters V1; it starts after phase P26, and the engine is decided by the T-1084 benchmark, not by these notes)

| candidate component | licence (read or fact id) | how run | obligation | blocks shipping, or open | source |
|---|---|---|---|---|---|
| pynput 1.8.2 (push-to-talk key listener) | LGPLv3 (F3) | in-process (a `WH_KEYBOARD_LL` global hook inside the shell's process) | LGPL duties if bundled/frozen: dynamic linking + user-swappable Qt-style relink path applies to LGPL code too, and one-file freezes complicate it (F1/F23 pattern `[I]`) | open: F3 also flags behaviour risk (a slow callback loses the hook after about 1 s) and that hook processes look like keyloggers to some vendors | F3, F1, F23 |
| `keyboard` library (alternative hotkey lib) | not stated in the reports `[?]` | in-process `[I]` | unknown `[?]` | blocks: unmaintained since 2020 (F3) and licence unread | F3 |
| `RegisterHotKey` / `GetAsyncKeyState` through `ctypes` | stdlib, no licence issue (F4) | in-process (stdlib call into the OS); press-only, so hold-to-talk needs ~30 ms polling of `GetAsyncKeyState`; `MOD_NOREPEAT`; Windows-reserved combinations fail | none | open: no licence issue; costs ~30 ms polling code `[I]` | F4 |
| faster-whisper 1.2.1 (2025-10-31) | MIT (F5) | in-process `[I]` (Python package; CTranslate2 underneath) | MIT notice on any copied code; F21 permits MIT as a code source with a `docs/credits.md` entry | open: GPU path needs CUDA 12 + cuDNN 9 (gigabytes of DLLs) and a heavy ctranslate2 dependency — an argument against the "zero runtime dependency" line (F20) | F5, F20, F21 |
| whisper.cpp v1.9.5 (2026-10-06) | MIT (F6) | **sidecar process** (separate exe, F6) | MIT notice on any copied code (F21) | open: named alternative if Parakeet loses the T-1084 benchmark (F20) | F6, F20, F21 |
| pywhispercpp 1.5.1 (binding for whisper.cpp) | not stated in the reports `[?]` | in-process binding that drives the sidecar `[I]` | unknown `[?]` | blocks: read its LICENSE before use (F19: the GitHub field often says NOASSERTION) | F6, F19 |
| ggml quantised whisper model files | not stated `[?]` | downloaded at run time | unknown `[?]` — model licences are separate from code licences | blocks: unread `[?]` | F6 |
| NVIDIA Parakeet-tdt-0.6b-v3 (model) | CC-BY-4.0 (F7) | downloaded at run time (not bundled) | **attribution is required** (F7, §4(b) below): credits entry + the model download step | open: attribution text not yet written; 25 European languages including Italian | F7 |
| onnx-asr 0.12.0 (driver for Parakeet) | MIT (F7) | in-process `[I]` through ONNX runtime, no PyTorch (F7) | MIT notice on copied code (F21); ONNX runtime itself: licence not covered by the reports `[?]` | open: the voice research recommends Parakeet via onnx-asr while the trends report prefers faster-whisper/sherpa-onnx — **unresolved** (F20) | F7, F20, F21 |
| sherpa-onnx (STT, VAD, diarisation, ONNX) | Apache-2.0 (F8) | sidecar process or in-process `[I]` (F15 shows it shipped as a bundled binary inside OpenWhispr) | Apache-2.0 requires attribution; permitted as a code source with a credits entry (F21) | open: engine choice (F20) | F8, F15, F21 |
| Moonshine Voice 0.1.6 | MIT (F9) | in-process `[I]` | MIT notice on copied code (F21) | blocks for this project: **no Italian speech-to-text**, and its non-English legacy models are **non-commercial** (F9) — Italian is a stated requirement (F7) | F9, F21, F7 |
| Windows WinRT `SpeechSynthesizer` / SAPI (speech output) | part of the operating system (F10); no licence to ship; use of the "natural voices" by a third party is unverified `[?]` | **OS component** (offline) | none for the OS parts; Cosimo and Elsa are the Italian voices (F10) | open: natural-voice redistribution terms `[?]`; this is the F14 recommendation (default Windows voices: free, offline) | F10, F14 |
| Piper (`piper-tts` 1.8.0, 2026-09-04) | GPL-3.0-or-later (F11) — it embeds espeak-ng; the original MIT repository was archived 2025-08 | **sidecar process** (F14: a SEPARATE process, downloaded, not bundled) | §4(c): GPL parts stay out of process, downloaded not bundled, never imported by Archeus's own Python code | open: acceptable only in the F14 shape; blocks if anyone imports it in-process | F11, F14, F21 |
| Piper voice models | separate files with their own licences `[?]` (F11) | downloaded at run time | unknown `[?]` per voice | blocks: unread `[?]` | F11 |
| espeak-ng | GPL (F12) — the reason Piper is GPL (F11) | not run by archeus; kept out of process `[I]` | §4(c) | blocks if bundled or imported | F12, F14 |
| Kokoro-82M weights (~300 MB; 80 MB quantised) | Apache-2.0 (F13) | downloaded at run time | Apache-2.0 attribution (F21) | open: size makes bundling unattractive `[I]` | F13, F21 |
| kokoro-onnx 0.6.1 (runner for Kokoro) | not stated in the reports `[?]` | in-process `[I]` (Python package), and it pulls espeakng-loader | unknown `[?]` | blocks: it pulls a GPL loader into the process — that is exactly the F14 shape to avoid | F13, F14 |
| espeakng-loader | GPL (F13, tagged `[I]` by the researcher) | in-process if kokoro-onnx is imported in-process `[I]` | §4(c) | blocks: GPL in process → must go, or kokoro-onnx must run as a sidecar `[I]` | F13, F14 |
| OpenWhispr (github.com/OpenWhispr/openwhispr) | MIT (F15) | not shipped; reference only. Its small native C helpers (clipboard + SendInput paste, key listener) could be vendored later | MIT code reuse needs a `docs/credits.md` entry (F21); its bundled third-party binaries (nircmd, whisper.cpp, sherpa-onnx, llama-server, qdrant, yt-dlp) have their own licences, **not checked** `[?]` (F15) | open: reference only; its Electron app is too heavy to embed | F15, F21 |
| Handy (cjpais/Handy, Rust/Tauri) | MIT (F16) | not shipped; reference only | credits entry if code is ever taken (F21) | open: reference for push-to-talk UX and a Windows global hotkey | F16, F21 |
| VoiceStudio (debpalash/VoiceStudio) | AGPL-3.0-only, dual licensed with a closed Pro build and a CLA (F17) | not shipped, not linked | **do not embed or link**; learn only (F17; F21: AGPL is not a code source) | blocks by rule; also: claude-squad, OpenViking and Nuitka are AGPL-3.0 (F17/F18) | F17, F21 |
| Briefcase (beeware/briefcase) — packaging | BSD-3-Clause (F18) | build tool (not shipped; runs at package time) | BSD-3 notice on any copied code | open: the ordinary (non-frozen) case is the easy LGPL case (F23) | F18, F23 |
| PyInstaller — packaging | shows **NOASSERTION** on GitHub (F18); its bootloader exception comes from the researcher's background knowledge `[?]` | build tool; the produced bundle wraps the app in its own bootloader process `[I]` | read its LICENSE file (F18/F19); the bootstrapper exception is the point of a frozen build's LGPL relink duty (F23) | blocks a *frozen single-file* build together with F1/F23 until the exception is read | F18, F19, F1, F23 |
| Nuitka — packaging | AGPL-3.0 (F18) | build tool | **no Nuitka without a licence review** (F18); F21 excludes AGPL as a code source | blocks if anyone proposes it as the packager | F18, F21, F17 |

Mic access (mentioned because §Table B touches the shell): on Windows, unpackaged desktop
apps get **no permission prompt** — there is one global setting "Let desktop apps access your
microphone"; detect silence or errors and show a hint (F24). No licence content.

> **Run-vocabulary note.** The four allowed values for `how run` (in-process / sidecar process
> / downloaded at run time / OS component) describe components that run inside or beside the
> app. The packaging tools (Briefcase, PyInstaller, Nuitka) and the reference-only repositories
> (OpenWhispr, Handy, VoiceStudio) never run at all in that sense, so their rows say
> "build tool" or "not shipped; reference only" instead `[I]`.

---

## 4. Obligations, in plain words

**(a) The LGPL relink path (F1, F23).** For any LGPL component the project bundles or freezes
— today that is the hotkey candidate pynput (F3) and, in the F1 researcher's framing, a
PySide6 shell (F1) — the user must be able to replace the LGPL part. In practice that means:
keep it **dynamically linked** (a real `.so`/`.dll` the user can swap, not statically linked
into one executable), ship or point to the licence text, provide the **build inputs needed to
relink** (the project's own object files / sources plus a written instruction), and let the
toolkit arrive by the **user's own `pip install`** — which is exactly how the `gui` extra works
today (`pyproject.toml:81`, `docs/installation.md:154-158`, F23). A dynamically linked Qt shell
installed by the user is the easy case; a **frozen single-file build is the hard case**
(F23/F1), and a frozen build is also where the PyInstaller bootloader exception (F18 `[?]`)
becomes load-bearing. Consequence to weigh: packaging (F18) and one-file freezes are what turn
an "optional extra, nothing to ship" into a relink-duty project.

**(b) CC-BY attribution for Parakeet (F7).** Parakeet-tdt-0.6b-v3 is CC-BY-4.0, and CC-BY
*requires attribution*. What must be shown: the model name, the fact that it is NVIDIA's, a
link to the model, and the licence identity (CC-BY-4.0). Where: a `docs/credits.md` entry
(the file's existing bullet style, `docs/credits.md:22-32`) **and** at the model download step
in the docs/UI, since the model is downloaded at run time rather than shipped (F7 `[I]` on
placement: attribution must sit where the user learns of the model). Consequence: an extra
line of user-visible text plus a credits entry; nothing to bundle.

**(c) The GPL parts: Piper, espeak-ng, espeakng-loader (F11, F12, F14).** GPL code is not used
as a code source (F21). The allowed shape is F14's: speech output uses the default Windows
voices (F10, free, offline); any "natural voice" is an optional download; Piper, if ever used,
runs in a **separate process** and is **downloaded, not bundled**; espeak-ng and espeakng-loader
stay in that out-of-process world too (F12, F14). The hard line: **never imported by Archeus's
own Python code** — no `import piper`, no `import espeakng_loader`, nothing that dlopen's them
in process — because an in-process GPL component is the case that contaminates, and a
non-MIT-compatible term for a derivative would become a shipping question for the whole wheel.
Consequence of getting it wrong: an MIT repository distributing a GPL-linked binary; the fix is
a sidecar boundary (F14), not a notice.

**(d) Notices for the vendored MIT files already in the wheel.** Checked in
`pyproject.toml:120-136`: `package-data` for `claude_sessions` includes
`"web/vendor/*.js", "web/vendor/*.txt"` (`pyproject.toml:126`) and `"web/vendor/*/*.js"`
(`pyproject.toml:127`). The `*.txt` glob **does** match `LICENSE-three.txt` and
`LICENSE-anime.txt`, which are the only `.txt` files in that directory (directory listing,
§0) — so **both MIT licence files ship inside the wheel**, which is what MIT's "The above
copyright notice and this permission notice shall be included in all copies or substantial
portions of the Software" asks for (`LICENSE:12-13`). Two residuals: (1) the 10 files under `postprocessing/` and
`shaders/` carry no header of their own (§0), so their coverage by `LICENSE-three.txt` is
`[?]`, and a future audit should confirm they are the three.js addons `[I]`; (2) the shipped
`LICENSE-anime.txt` says Copyright (c) 2025 while the bundle's own header says
`@copyright 2026 - Julian Garnier` — one of the two is stale `[?]` (Observations).

---

## 5. What blocks shipping

- **`gui = ["PyQt6", "PyQt6-WebEngine"]` (`pyproject.toml:81`)** — the open licence question,
  if the owner wants a repository that is clean MIT without a GPL-or-commercial toolkit:
  PyQt6 is GPLv3 or commercial (F2 `[?]`). Decision item 97 (the PySide6 swap) is a separate
  owner decision and is **not made or implemented here**; options and consequences only:
  *keep PyQt6* → the toolkit stays an optional, user-installed extra (nothing bundled; a GPL
  toolkit in an MIT repo remains a decision, not a bug) or *swap to PySide6* → LGPL-3.0-only OR
  GPL-2.0/3.0 with the researcher's verdict "adopt, with an LGPL notice and a relink path"
  (F1), which buys an LGPL relink duty in exchange for the GPL question (F1/F23).
- **Any GPL component bundled** (Piper, espeak-ng, espeakng-loader; F11/F12/F13/F14) —
  out of process and downloaded, or it does not ship.
- **A frozen single-file build with LGPL Qt** (F1/F23) — and the packaging tool itself is a
  licence question: PyInstaller's exception is unread `[?]` (F18), Nuitka is AGPL-3.0 and needs
  a licence review (F18).
- **Missing attribution** — CC-BY-4.0 Parakeet (F7) and any Apache-2.0 reuse (sherpa-onnx F8,
  Kokoro weights F13) need the credits entry (F21).
- **Anything marked `[?]` above that must be verified before release:** PyQt6's actual licence
  terms (F2), the PyQt6-WebEngine/Chromium notice set (F22), the licence of the header-less
  `postprocessing/` and `shaders/` files, the anime.js copyright-year mismatch, PyInstaller's
  bootloader exception (F18), pywhispercpp (F6), ggml model files (F6), Piper voice models
  (F11), kokoro-onnx and its pulled-in GPL loader (F13), onnx-asr's ONNX runtime (F7), the
  Windows "natural voices" third-party terms (F10), the `keyboard` library (F3), the
  third-party binaries inside OpenWhispr (F15), and setuptools/pytest/mkdocs-material
  (irrelevant to the wheel, still unread `[?]`). F19: read the LICENSE file, never the GitHub
  licence field.

---

## 6. Proposed `docs/credits.md` entries (**not applied** — listed only; `docs/credits.md` is
### not edited by this card, and no line is included for anything nothing was taken from)

Style follows the existing bullets (`docs/credits.md:22-32`: name, link, licence, what was
taken). Nothing below is merged; nothing is taken yet.

- **[three.js](https://github.com/mrdoob/three.js)** (MIT, as read from
  `claude_sessions/web/vendor/LICENSE-three.txt`) — code, vendored: `three.core.min.js` and
  `three.module.min.js` ship in the wheel and are served by the local GUI server from
  `/vendor/`, offline, never a CDN (`docs/desktop.md:12-13`; `gui.py:719-727`: "public MIT
  libraries, byte-identical to their npm originals"). Notice file shipped
  (`web/vendor/*.txt`, `pyproject.toml:126`).
- **[anime.js](https://github.com/juliangarnier/anime)** (MIT, as read from
  `claude_sessions/web/vendor/LICENSE-anime.txt`) — code, vendored: `anime.esm.min.js`
  (v4.5.0 per its own header) ships in the wheel and is served from `/vendor/` the same way
  (`docs/desktop.md:12-13`; `pyproject.toml:126`).
- **[OpenWhispr](https://github.com/OpenWhispr/openwhispr)** (MIT, F15) — idea and reference
  only, **no code taken**: push-to-talk UX shape and the small native clipboard/SendInput +
  key-listener helpers that could be vendored later (with this entry upgraded to "code").
- **[Handy](https://github.com/cjpais/Handy)** (MIT, F16) — idea and reference only, **no code
  taken**: push-to-talk UX and a Windows global hotkey.

(That is 4 of the allowed 8 lines. The `postprocessing/` and `shaders/` trees are covered by
the three.js line if the `[?]` in §4(d) resolves to three.js addons, and PySide6 gets no line
until a swap exists, since F1 is a decision not yet taken.)

---

## 7. Open questions for the owner (max 5)

1. Item 97: keep `gui = PyQt6` (GPLv3-or-commercial, F2 `[?]`) or swap to PySide6 (F1) — and if
   the swap, does the `gui` extra, `gui_qt.py`'s imports and `docs/installation.md:154-158` all
   move in one card?
2. Is "MIT repository, optional user-installed GPL toolkit" (PyQt6: GPLv3 or commercial,
   F2 `[?]`) acceptable as the shipping position, or must the repository be GPL-free end to
   end? (Options only; no recommendation.)
3. Will the desktop shell ever be a **frozen single-file** build? If yes, the LGPL relink
   package (F1/F23) and the packaging-tool licence (F18) must be settled first.
4. Which licence file do `web/vendor/postprocessing/` and `web/vendor/shaders/` come from —
   is `LICENSE-three.txt` the right notice for them (currently `[?]`)?
5. For the voice extra (post-P26): Parakeet-v3 via onnx-asr (F7) or faster-whisper /
   whisper.cpp / sherpa-onnx (F20, F5-F8) — does the owner want the CC-BY attribution text and
   the sidecar boundary fixed *before* the T-1084 benchmark, or after the engine is chosen?

## 8. Observations

- **`dev = ["pytest"]` vs CONTRIBUTING.** `CONTRIBUTING.md:144-146` says test, docs and build
  tooling live in their own install steps "never in `pyproject.toml`", yet `pyproject.toml:80`
  lists `dev = ["pytest"]`. Reported as an observation, **not fixed** (the card forbids editing
  `pyproject.toml` or `CONTRIBUTING.md`). `requirements-docs.txt:1-2` does follow the rule.
- The `gui` extra names `PyQt6-WebEngine`, but `docs/installation.md:158` shows the user
  installing both packages manually (`pip install PyQt6 PyQt6-WebEngine`), i.e. the docs
  duplicate the extra rather than pointing at `archeus[gui]`.
- Vendored anime.js carries two different copyright years: `LICENSE-anime.txt` says 2025, the
  bundle header says 2026 (§4(d)) — `[?]`.
- `claude_sessions/web/vendor/` has no `LICENSE` file for the two subdirectories, and none of
  their 10 files carries a header (§0) — `[?]`.
- The Qt shell's PyQt6 imports are function-local (`gui_qt.py:76-79`, `166-170`), which is what
  makes the browser fallback work (`gui.py:1065-1081`): no PyQt6, no import, `ImportError`,
  Edge/browser. Licence-relevant: the toolkit is never imported unless the user installed it.
- The `package-data` comment itself (`pyproject.toml:122-123`) states three.js and anime.js are
  "both MIT, vendored so the GUI stays offline"; both LICENSE files confirm it (§0).
- F19 applies to every `[?]` above: the GitHub licence field is unreliable (NOASSERTION), and
  nothing in this container can read any of them — verification belongs to the Windows review
  pass against the installed wheels.
