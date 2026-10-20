/* LV2-X shell: ?d=a|b|c  &v=home|live|decide|mission  &s=normal|idle|primed|stopped  &id=<mission>  &prov=1 */
(function () {
  'use strict';
  const { Q, S, estop, icon, go } = window.AX;
  const d = Q.get('d') || 'a', v = Q.get('v') || 'home';
  const phone = Q.get('dev') ? Q.get('dev') === 'phone' : innerWidth < 600;
  const root = document.documentElement;
  root.dataset.d = d; root.dataset.dev = phone ? 'phone' : 'desk'; root.dataset.estop = estop.state; root.dataset.v = v;
  if (Q.get('prov')) root.dataset.prov = '1';
  if (Q.get('shot')) root.dataset.shot = '1';

  // the e-stop, shared: first press primes for 3 s and says what the second press does; second press stops;
  // no dialog; a lapse returns it to rest. Stopped shows the way back (PIN step-up, P20 D10), never "re-arm".
  AX.estopButton = (opts) => {
    const o = opts || {};
    if (estop.state === 'stopped')
      return `<a class="estop" data-state="stopped" href="${go({ s: null })}" title="Resume needs your PIN (P20 D10)">Resume work…</a>`;
    if (estop.state === 'primed')
      return `<a class="estop" data-state="primed" style="--left:.66" href="${go({ s: 'stopped' })}" aria-live="assertive">${icon.stop}${o.short ? 'Press again' : 'Press again to stop all work'}</a>`;
    return `<a class="estop" data-state="running" href="${go({ s: 'primed' })}">${icon.stop}${o.short ? 'Stop' : 'Stop all work'}</a>`;
  };
  AX.primedHint = () => `<div class="primed-hint estop-note">Stops <b>${AX.running.length} running missions</b> now and refuses new work. Lapses in ${estop.left} s if you do nothing. Resuming needs your PIN.</div>`;

  const D = (window.DIR || {})[d];
  document.getElementById('app').innerHTML = D ? D.render(v, phone) : `<p style="padding:24px">Direction ${d} not built yet.</p>`;
  document.title = 'Archeus — direction ' + d.toUpperCase() + ' · ' + v + (S !== 'normal' ? ' · ' + S : '');
  const tag = document.createElement('div');
  tag.className = 'review-banner';
  tag.textContent = `LV2-X prototype · direction ${d.toUpperCase()} · ${v} · ${S}`;
  document.body.appendChild(tag);

  // primed lapses after 3 s in the live page (frozen in captures, ?shot=1)
  if (estop.state === 'primed' && !Q.get('shot')) setTimeout(() => { location.search = go({ s: null }); }, estop.left * 1000);
})();
