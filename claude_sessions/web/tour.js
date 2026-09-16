/* ── the guided tour ──────────────────────────────────────────
   A coach-mark, not a modal. The point of a tour of an application is to be
   IN the application while it is explained, so this navigates to the screen a
   step is about, rings the thing it is pointing at, and docks a card in the
   corner. A full-screen dialog explaining a screen you cannot see is a manual
   with extra steps.

   The steps are not here. `claude_sessions/tour.py` is the one place the
   narrative is written, because the terminal UI prints the same words and
   `tools/gen_tour.py` writes them into the website — so this fetches them once
   per tour and holds them for the session.

   Two tours: `short` is the first five minutes and ends with a session
   launched; `long` is every function archeus has, what it is for, and the
   thing people miss about it.

   Motion: this obeys `motion:off` and it animates `transform`/`opacity` only —
   the ring is a `box-shadow` that is set, never transitioned to. Anything that
   forces a compositor readback tears the Qt surface (see CLAUDE.md), and a
   feature whose whole job is to draw attention is the last place to risk it. */
const TOUR = {
  steps: [], i: 0, which: '', on: false, _cache: {},

  /* localStorage, wrapped: it throws in a private window and comes back empty
     after cleared site data. Remembering where a tour got to is a per-viewer
     convenience and nothing may depend on it. */
  _seen(v) {
    try {
      if (v === undefined) return localStorage.getItem('archeus.tour') || '';
      localStorage.setItem('archeus.tour', v);
    } catch (e) { /* no store: the tour simply offers itself again */ }
    return '';
  },

  async start(which, from) {
    which = which || 'short';
    if (!this._cache[which]) {
      try {
        const d = await api('/api/tour?which=' + encodeURIComponent(which));
        this._cache[which] = (d && d.steps) || [];
      } catch (e) { this._cache[which] = []; }
    }
    this.steps = this._cache[which];
    if (!this.steps.length) { toast('The tour could not be loaded', 'err'); return; }
    this.which = which;
    this.i = Math.max(0, Math.min(this.steps.length - 1, from || 0));
    this.on = true;
    this._seen(which + ':running');
    document.addEventListener('keydown', this._key);
    this.show();
  },

  stop(done) {
    this.on = false;
    this._ring(null);
    const h = $('#tour'); if (h) { h.hidden = true; h.innerHTML = ''; }
    document.removeEventListener('keydown', this._key);
    this._seen(done ? this.which + ':done' : this.which + ':' + this.i);
  },

  next() { if (this.i + 1 >= this.steps.length) return this.stop(true); this.i++; this.show(); },
  back() { if (this.i > 0) { this.i--; this.show(); } },

  _key(e) {
    if (!TOUR.on) return;
    if (e.key === 'Escape') { TOUR.stop(); e.preventDefault(); }
    else if (e.key === 'ArrowRight') { TOUR.next(); e.preventDefault(); }
    else if (e.key === 'ArrowLeft') { TOUR.back(); e.preventDefault(); }
  },

  /* The ring is a class on the real element, so it follows the element through
     a re-render only as far as the element survives one — which is why `show()`
     re-resolves the target after navigating rather than holding a node. */
  _ring(el) {
    document.querySelectorAll('.tspot').forEach(n => n.classList.remove('tspot'));
    if (el) el.classList.add('tspot');
  },

  /* Where a step points. A `page` step rings its SECTION row in the sidebar
     (that is what the user would click), a `tab` step rings the tab — and when
     no project is open there is no tab to ring, which is not an error: the card
     still says what it is and where it lives. */
  _target(s) {
    if (s.tab) return document.querySelector('[data-tab="' + s.tab + '"]');
    if (s.page && SEC_OF[s.page]) return document.querySelector('[data-nav="' + SEC_OF[s.page] + '"]');
    if (s.page === 'home') return document.querySelector('#logo') || document.querySelector('#nav');
    return null;
  },

  async show() {
    const s = this.steps[this.i];
    if (!s) return this.stop(true);
    /* Navigate first, THEN resolve the target: `go()` rewrites the nav and the
       tab strip, so a node looked up before it is a node no longer in the
       document. */
    if (s.page && s.page !== PAGE_ && !s.tab) {
      if (s.page === 'home') go('home'); else go(s.page);
    } else if (s.tab && PAGE_ === 'project' && TAB !== s.tab) {
      openTab(s.tab);
    }
    await new Promise(r => setTimeout(r, 0));
    this._ring(this._target(s));
    this.paint(s);
  },

  paint(s) {
    const h = $('#tour'); if (!h) return;
    const n = this.steps.length, last = this.i + 1 >= n;
    const where = s.tab && PAGE_ !== 'project'
      ? '<div class="twhere">Open a project to see this one — it is a tab inside every project.</div>' : '';
    const key = s.key ? `<span class="tkey" title="The key that reaches this in the terminal UI">${esc(s.key)}</span>` : '';
    h.hidden = false;
    h.innerHTML = `<div class="tcard" role="dialog" aria-label="Guided tour">
      <div class="thead"><span class="tstep">${this.i + 1} / ${n}</span>${key}
        <span class="sp"></span>
        <button class="btn sm" id="tSkip" title="Esc">${ic('close')}</button></div>
      <h4>${esc(s.title)}</h4>
      <p>${esc(s.body)}</p>${where}
      ${s.docs_url ? `<a class="tdoc" href="${esc(s.docs_url)}" target="_blank"
        rel="noopener">Read more in the manual ${ic('ext')}</a>` : ''}
      <div class="tbar"><div class="tprog"><i style="transform:scaleX(${(this.i + 1) / n})"></i></div></div>
      <div class="trow">
        <button class="btn sm" id="tBack" ${this.i ? '' : 'disabled'}>Back</button>
        <button class="btn sm pri" id="tNext">${last ? 'Finish' : 'Next'}</button>
      </div></div>`;
    $('#tSkip').onclick = () => this.stop();
    $('#tBack').onclick = () => this.back();
    $('#tNext').onclick = () => this.next();
  },
};
window.TOUR = TOUR;
