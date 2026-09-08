"""The archeus GUI single-page app. Pure static markup — all data arrives
via fetch() from gui.py / gui_api.py endpoints. Self-contained: no CDN, no
external fonts, works offline. Full TUI parity: sessions, transcript,
memory suite, CLAUDE.md ops (job + diff-approve), usage, search, managers."""

import posixpath
from pathlib import Path

_WEB = Path(__file__).parent / "web"
_VENDOR = _WEB / "vendor"
_cache = {}

def _read(name):
    if name not in _cache:
        _cache[name] = (_WEB / name).read_text(encoding="utf-8")
    return _cache[name]

#: JS bundle order. motion.js, instruments.js and stage.js define MO / INST /
#: STAGE, which app.js calls at boot, so they must be concatenated ahead of it.
#: Everything lands in one <script>, so this is plain source order — no modules,
#: no fetch, and every `assert … in PAGE` test still sees the whole app in one
#: string.
#:
#: The VENDORED libraries (three.js, anime.js) are deliberately NOT here. They
#: are ~890KB; inlining them would put that in the page string on every single
#: load for no benefit, and they are not ours to assert on. They are served
#: separately from /vendor/ (see VENDOR_FILES) and cached by the browser, and
#: stage.js/motion.js both degrade gracefully when they never arrive.
#: cluster-spec.js is GENERATED (tools/gen_cluster_spec.py) and defines
#: CLUSTER, which stage.js reads at build time, so it leads.
_JS = ("cluster-spec.js", "motion.js", "instruments.js", "stage.js", "app.js")


def _scan_vendor():
    """Relative POSIX paths of every vendored asset, as a frozen allowlist.

    Membership against a set built by walking the directory is what makes the
    /vendor/ route traversal-safe: '../../secrets' is simply not in the set, so
    no path arithmetic is needed and none can be got wrong."""
    if not _VENDOR.is_dir():
        return {}
    out = {}
    for p in sorted(_VENDOR.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(_VENDOR).as_posix()
        out[rel] = p
    return out


#: name -> Path. Built once at import; the vendor tree is static.
VENDOR_FILES = _scan_vendor()

_VENDOR_TYPES = {".js": "text/javascript", ".mjs": "text/javascript",
                 ".css": "text/css", ".txt": "text/plain",
                 ".map": "application/json"}


def vendor_asset(rel):
    """(bytes, content-type) for a vendored file, or None if not allowlisted."""
    rel = posixpath.normpath((rel or "").lstrip("/"))
    p = VENDOR_FILES.get(rel)
    if p is None:
        return None
    ctype = _VENDOR_TYPES.get(p.suffix.lower(), "application/octet-stream")
    return p.read_bytes(), ctype


def _build_html():
    html = _read("index.html")
    html = html.replace("<!--CSS-->", _read("app.css"))
    html = html.replace("<!--JS-->", "\n".join(_read(n) for n in _JS))
    return html

PAGE = _build_html()
