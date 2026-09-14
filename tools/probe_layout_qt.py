"""Does the layout that headless Chromium measured behave in the shell we ship?

`tools/shot_gui.py` drives Playwright's Chromium (149 at the time of writing);
the Qt shell embeds QtWebEngine's (140). Everything the container/pile pass is
built on — `@container`, `:has()`, `column-span:all`, `container-type`'s layout
containment — shipped in Chromium long before either, so this is a formality in
the sense that a compiler flag is a formality: cheap, and the only way to know.

It is the same mechanism as `tools/probe_qt.py`: Playwright cannot attach to
QtWebEngine (`connect_over_cdp` needs `Browser.setDownloadBehavior`, which Qt
answers "not supported"), so the window is driven through `run_desktop(
on_ready=...)` and `page().runJavaScript()`.

    py tools/probe_layout_qt.py            # opens the real GUI, reports, closes

Reads only. It navigates the app you already have and prints what it measured.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

#: Everything the pass depends on, asked of the engine itself and then of the
#: live page — support is not the same as "the rule matched", and the second is
#: what actually holds a five-column table open.
CHECK = """(() => {
  const out = {};
  out.ua = navigator.userAgent.match(/Chrome\\/[\\d.]+/)?.[0] || '?';
  out.supports = {
    container: CSS.supports('container-type: inline-size'),
    has: CSS.supports('selector(:has(.x))'),
    span: CSS.supports('column-span: all'),
    autofit: CSS.supports('grid-template-columns: repeat(auto-fit,minmax(10px,1fr))'),
  };
  const card = document.querySelector('#content .card');
  out.cardIsContainer = card ? getComputedStyle(card).containerType : 'no card';
  const content = document.querySelector('#content');
  out.contentIsContainer = getComputedStyle(content).containerType;
  out.contentCols = getComputedStyle(content).gridTemplateColumns
    .trim().split(/\\s+/).length;
  const pile = document.querySelector('.pile');
  out.pile = pile ? getComputedStyle(pile).columnWidth + ' -> '
    + [...pile.children].filter(e => e.getBoundingClientRect().width
        >= pile.clientWidth - 2).length + ' spanning of ' + pile.children.length
    : 'none on this page';
  /* the rule the photographed defect turns on: a card holding a >=4-column
     table takes the whole row (grid) or the whole width (pile) */
  const wide = [...document.querySelectorAll('#content .card')]
    .filter(c => c.querySelector('.tbl th:nth-child(4)'));
  out.wideTables = wide.map(c => Math.round(c.getBoundingClientRect().width)
    + '/' + Math.round((c.parentElement || c).clientWidth));
  return out;})()"""


def main():
    from PyQt6.QtCore import QTimer
    from claude_sessions.gui_qt import run_desktop
    seen = {}

    def ready(view, app):
        page = view.page()

        def done(res):
            seen.update(res or {})
            print('chromium        ', seen.get('ua'))
            for k, v in (seen.get('supports') or {}).items():
                print(f'  supports {k:<10} {v}')
            print('#content        ', seen.get('contentIsContainer'),
                  '·', seen.get('contentCols'), 'column(s)')
            print('.card           ', seen.get('cardIsContainer'))
            print('pile            ', seen.get('pile'))
            print('wide tables     ', seen.get('wideTables') or 'none here')
            bad = [k for k, v in (seen.get('supports') or {}).items() if not v]
            if seen.get('cardIsContainer') != 'inline-size':
                bad.append('card is not a container in this engine')
            print(chr(10) + 'VERDICT:', 'clean' if not bad
                  else 'MISSING ' + ', '.join(bad))
            app.quit()

        def measure():
            page.runJavaScript(CHECK, done)

        def open_memory():
            # the Memory tab, which is where the photograph was taken
            page.runJavaScript(
                "(()=>{const p=(ST.projects||[])[0];"
                "if(p){openProject(p);TAB='memory';go('project');}"
                "else{go('helpp');}})()")
            QTimer.singleShot(4000, measure)

        # loadFinished means the document loaded, not that the app has booted
        # and fetched its state — poll for what we are about to drive, the same
        # way probe_qt does, rather than guessing an interval.
        tries = [0]

        def wait_ready(ok):
            tries[0] += 1
            if ok or tries[0] > 60:
                QTimer.singleShot(400, open_memory)
            else:
                QTimer.singleShot(250, lambda: page.runJavaScript(
                    '!!(window.ST && window.NAV && document.querySelector("#content"))',
                    wait_ready))

        wait_ready(False)

    run_desktop(on_ready=ready)
    return 0 if seen else 1


if __name__ == '__main__':
    sys.exit(main())
