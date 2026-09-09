"""Screenshot the GUI against realistic stub data and audit for layout overflow.

Companion to tools/smoke_gui.py: that one checks behaviour, this one checks fit.
The overflow audit is the useful part — it walks every dashboard card and reports
any descendant whose box sticks out past it, which is how the oversized gauges
were caught (a square gauge in a width:100% slot grew as tall as the card was
wide and spilled its label out of the bottom).

    py -3 tools/shot_gui.py [outdir]
"""
import importlib.util
import os
import sys
import threading
import time
from http.server import ThreadingHTTPServer

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
sys.stdout.reconfigure(encoding='utf-8', errors='replace')

_spec = importlib.util.spec_from_file_location('sg', os.path.join(_ROOT, 'tools', 'smoke_gui.py'))
sg = importlib.util.module_from_spec(_spec)
sg.__name__ = 'sg'
_spec.loader.exec_module(sg)

#: a positional argument overrides the scratch directory; flags are not it
_ARGS = [a for a in sys.argv[1:] if not a.startswith('-')]
OUT = _ARGS[0] if _ARGS else os.path.join(_ROOT, 'references')
PORT = 8801

# a workspace the size of a real one: 13 projects, 10 MCP servers, 3 accounts.
# Small stub data hides exactly the bugs that matter — an oversized gauge looks
# fine next to two projects and breaks the card next to thirteen.
_N = time.time()
# Deliberately fictional. These fixtures feed the README screenshots, so
# anything copied from a real workspace becomes a published project list.
_PROJ = [('acme-api', 4199000, 'now', ['default', 'teamA']),
         ('acme-web', 4562000, '12h', ['default', 'teamA']),
         ('acme-docs', 163000, '6h', ['default']),
         ('forecasting-model', 48000, '8h', ['default']),
         ('checkout-service', 91000, '1d', ['default', 'teamA']),
         ('vision-finetune', 22000, '2d', ['default']),
         ('mobile-client', 18000, '3d', ['default']),
         ('billing-worker', 9000, '4d', ['teamA']),
         ('search-index', 7000, '5d', ['default']),
         ('infra-terraform', 5000, '6d', ['teamB']),
         ('design-system', 4000, '7d', ['default']),
         ('data-pipeline', 3000, '8d', ['teamA']),
         ('scratchpad', 2000, '9d', ['default'])]
sg.DASH['breakdown']['projects'] = [
    {'name': n, 'enc': n.lower(), 'tokens': t, 'cost': t / 2e5, 'age': a,
     'mtime': _N - i * 4000, 'accounts': acc, 'omni': i % 3 == 0,
     'sparkline': [(i * j) % 9 + 1 for j in range(7)]}
    for i, (n, t, a, acc) in enumerate(_PROJ)]
sg.DASH['mcp'] = [{'name': 'server-%d' % i, 'running': i == 0} for i in range(10)]
sg.ROUTES['/api/mcp'] = {'servers': [{'name': 'server-%d' % i,
                                      'status': 'ok' if i == 0 else 'down'}
                                     for i in range(10)]}
# FIVE, because five is what the plan-usage rail has to hold and three is what
# hid the bug: `.acct-card{flex:0 0 232px}` in a half-width dashboard area fits
# three and clips the fourth, which is exactly what a user photographed. A stub
# is only as strong as the state it puts the UI in.
# The email is its own value, not the account name again: every account row in
# the app prints name and email side by side, and a stub that repeats itself
# reads as a bug on screen ("default default") while hiding the real width.
_ACCTS = [('default', 87, '01:40', 59, 'Sun 09:00'),
          ('teamA', 82, '03:09', 57, 'Sat 08:59'),
          ('teamB', 45, '04:50', 48, 'Mon 02:00'),
          ('teamC', 12, '05:20', 31, 'Tue 07:30'),
          ('research', 99, '00:25', 77, 'Wed 11:00')]
sg.PLAN['accounts'] = [
    {'account': n, 'email': '%s@example.invalid' % n, 'plan': 'max', 'status': 'ok',
     'windows': [{'label': 'session', 'pct': sp, 'resets': sr},
                 {'label': 'weekly', 'pct': wp, 'resets': wr}]}
    for n, sp, sr, wp, wr in _ACCTS]
sg.STATE['accounts'] = [{'name': n, 'dir': n, 'active': n == 'default'}
                        for n, *_ in _ACCTS]
# The lessons table is the widest table in the app — five columns, one of them a
# button group — and the behaviour stub carries four rows because four is enough
# to prove the endpoint. Nine rows with real summaries is what the screen looks
# like, and a table only reads as cramped when it has something in it.
sg.ROUTES['/api/lessons'] = {
    'counter': 34, 'ttl': 30,
    'lessons': sg.ROUTES['/api/lessons']['lessons'] + [
        {'id': 'l%d' % (5 + i), 'status': st, 'confidence': cf, 'kind': kd,
         'last_used': lu, 'name': nm, 'summary': sm}
        for i, (st, cf, kd, lu, nm, sm) in enumerate((
            ('approved', 0.9, 'decision', 30,
             'Idempotency keys live on the request, not the row',
             'Two clients retried the same capture and the ledger took it '
             'twice; the key is minted by the caller now.'),
            ('approved', 0.7, 'error_fix', 21,
             'Timezones are stored as UTC and rendered in the account zone',
             'A nightly rollup ran twice in one October and skipped a day in '
             'March, because the cutoff was local midnight.'),
            ('pinned', 0.9, 'decision', 2,
             'The webhook receiver validates the signature before parsing',
             'Parsing first meant a malformed payload from anyone could raise '
             'inside the handler and be logged as our own fault.'),
            ('approved', 0.4, 'preference', 12,
             'One migration per pull request',
             'Two schema changes in one branch could not be rolled back '
             'independently when the second one turned out to be wrong.'),
            ('pending', 0.5, 'correction', 34,
             'Search indexes rebuild from the read replica',
             'The rebuild saturated the primary during business hours; it '
             'reads the replica and throttles now.')))]}
# The project's own Usage tab, which was being audited in its empty state while
# the Sessions tab beside it listed five. Oldest cost first, as the page says.
sg.ROUTES['/api/usage/project'] = {'sessions': [
    {'age': a, 'name': nm, 'account': acct, 'msgs': m, 'exact': ex,
     'cost': c, 'usage': {'in': i, 'out': o}}
    for a, nm, acct, m, ex, c, i, o in (
        ('4d', 'cache the search index warm-up', 'teamA', 25, False, 0.42,
         61_000, 16_000),
        ('2d', 'add the migration gate to deploy', 'default', 42, True, 0.88,
         121_000, 35_000),
        ('1d', 'split the checkout handler', 'teamA', 137, False, 4.71,
         702_000, 208_000),
        ('3h', 'move invoice totals to integer cents', 'default', 61, True, 1.63,
         224_000, 64_000),
        ('12m', 'retry storm on the payments upstream', 'default', 84, False,
         2.35, 318_000, 94_000))]}

# The auto-memory schedule, which the Updates page lists with a checkbox each.
# Two of the thirteen are on the schedule, which is the state STATE['projects']
# already describes with its own `auto_memory` flag.
sg.ROUTES['/api/memory/auto'] = {'interval': 1800, 'projects': [
    {'name': p['name'], 'path': '/demo/' + p['name'], 'enc': p['enc'],
     'auto': i < 2, 'running': i == 0}
    for i, p in enumerate(sg.DASH['breakdown']['projects'][:6])]}

# Account sync, in the state the card exists for: two accounts that differ, so
# the seven-column table is audited instead of its empty branch.
sg.ROUTES['/api/accounts/sync'] = {'clean': False, 'accounts': [
    {'name': 'default', 'todo': 0,
     'have': {'plugins': 1, 'marketplaces': 1, 'hooks': 2, 'agents': 3,
              'statusline': True, 'claude_md': True},
     'missing': {}},
    {'name': 'teamA', 'todo': 3,
     'have': {'plugins': 0, 'marketplaces': 1, 'hooks': 1, 'agents': 3,
              'statusline': False, 'claude_md': True},
     'missing': {'plugins': ['demo'], 'hooks': ['inject-memory'],
                 'statusline': True}},
    {'name': 'teamB', 'todo': 2,
     'have': {'plugins': 1, 'marketplaces': 0, 'hooks': 2, 'agents': 0,
              'statusline': True, 'claude_md': False},
     'missing': {'marketplaces': ['official'], 'claude_md': True}}]}

sg.STATE['projects'] = [
    {'name': p['name'], 'path': '/demo/' + p['name'],
     'encoded': p['enc'], 'accounts': p['accounts'], 'primary_cfgdir': '',
     'auto_memory': i < 2, 'last_active': p['age']}
    for i, p in enumerate(sg.DASH['breakdown']['projects'])]

# A child of a scrolling container legitimately has a rect outside it — that is
# what scrolling means — so those are skipped or every long list reads as broken.
OVERFLOW_JS = """[...document.querySelectorAll('.dash>.card')].map(c=>{
  const cb=c.getBoundingClientRect();const bad=[];
  const clipped=e=>{
    for(let p=e.parentElement;p&&p!==c.parentElement;p=p.parentElement){
      const o=getComputedStyle(p).overflowY;
      if(o==='auto'||o==='scroll'||o==='hidden')return true;}
    return false;};
  c.querySelectorAll('*').forEach(e=>{
    const b=e.getBoundingClientRect();
    if(!b.height||clipped(e))return;
    const over=Math.max(b.bottom-cb.bottom,b.right-cb.right);
    if(over>1.5)bad.push((typeof e.className==='string'?e.className.split(' ')[0]:e.tagName)
      +'+'+Math.round(over)+'px');});
  return (c.className.match(/d-[\\w]+/)||['?'])[0]+': '+(bad.length?bad.join(', '):'clean');})"""

#: `.d-i1..4` grouped by the line they sit on. The four are one row when the
#: dashboard has four columns, two rows of two when it has two, and four rows
#: of one when it has one — and `align-self:stretch` equalises within a grid
#: ROW. Comparing all four regardless reported RAGGED on every skin at 1280px
#: for a dashboard whose every row was level.
IHEIGHTS_JS = """(()=>{const rows=new Map();
  ['d-i1','d-i2','d-i3','d-i4'].forEach(k=>{
    const e=document.querySelector('.'+k); if(!e)return;
    const b=e.getBoundingClientRect(),r=Math.round(b.top/8);
    if(!rows.has(r))rows.set(r,[]);
    rows.get(r).push(Math.round(b.height));});
  return [...rows.values()];})()"""


#: the widths the fluid content grid actually has to survive. One column at
#: 1280, two at 1920, three at 2560 — decided by `auto-fill`, not by a
#: breakpoint, which is exactly why it has to be MEASURED rather than reasoned
#: about. Auditing at one width could never see a card that only breaks when the
#: browser fits another column in and every column gets narrower.
WIDTHS = (1280, 1920, 2560)

# Does every card's content fit the grid CELL it landed in?
#
# RIGHT-EDGE ONLY, and deliberately so: `#content` scrolls vertically, so a page
# taller than the viewport is not a bug — a card wider than its column is. The
# probe is rooted on each grid item rather than on `#content` because the cell
# is the box that narrows when auto-fill adds a column.
#
# A descendant of a horizontally scrolling ancestor is skipped for the same
# reason OVERFLOW_JS skips one inside a scroller: `.diff`, `.dlist` and
# `.acct-rail` are *supposed* to hold content wider than themselves. The root
# itself is excluded from that walk — `#content` and `.modal` both scroll, so a
# probe that consulted the root's own overflow skipped every element it was
# asked to measure and reported `clean` for measuring nothing.
GRID_JS = """(()=>{const out=[];
  const c0=document.querySelector('#content');
  if(c0&&c0.scrollWidth-c0.clientWidth>1.5)
    out.push('#content scrolls sideways by '+Math.round(c0.scrollWidth-c0.clientWidth)+'px');
  document.querySelectorAll('.content>*').forEach(c=>{
    const cb=c.getBoundingClientRect();
    if(!cb.width||!cb.height)return;
    const scrolls=e=>{
      for(let p=e.parentElement;p&&p!==c.parentElement;p=p.parentElement){
        if(p===c)continue;
        const o=getComputedStyle(p).overflowX;
        if(o==='auto'||o==='scroll'||o==='hidden')return true;}
      return false;};
    const bad=[];
    c.querySelectorAll('*').forEach(e=>{
      const b=e.getBoundingClientRect();
      if(!b.width||!b.height||scrolls(e))return;
      const over=b.right-cb.right;
      if(over>1.5)bad.push((typeof e.className==='string'
        ?e.className.split(' ')[0]:e.tagName)+'+'+Math.round(over)+'px');});
    if(bad.length)out.push(((typeof c.className==='string'&&c.className)
      ||c.tagName)+' > '+[...new Set(bad)].slice(0,4).join(', '));});
  return [...new Set(out)];})()"""

# Does the page USE the space it has?
#
# Every probe above this one asks whether something sticks OUT. Not one of them
# can see the opposite failure, which is the one people photograph: a five-column
# table squeezed into one 730px track while the other half of the row is dark, a
# card stretched to twice the height of its contents, a sentence 200 characters
# wide. All three passed every audit in this file for as long as it has existed.
#
# Four measurements, all in pixels of visible emptiness rather than opinions:
#
#   ragged   two cards side by side whose bottoms are far apart. This is the
#            dead space you actually see mid-page, and `align-items:start` on a
#            grid row means it is unavoidable unless the composition changes.
#   dead     a grid row holding fewer items than the grid has tracks, reported
#            only when the resulting hole is bigger than a card-sized area — a
#            60px stub at the end of a list is not what anyone means by empty.
#   slack    a card whose last child stops well short of its own floor.
#   cramped  a SHORT label in a table cell that wraps at all: the column is
#            too narrow for its own content. This is the Memory tab's
#            misaligned status column, and the threshold is calibrated against
#            that photograph rather than guessed — at 2.4 line-heights it slept
#            through the two-line cell that was actually reported.
#   measure  prose wider than 110ch, measured with the element's own font
#            rather than an assumed 0.5em advance.
#
# It also returns what it PROBED, because a probe that silently stops finding
# containers reports "clean" — the same failure as smoke_gui's check floor.
SPACE_JS = """(()=>{
  const out=[],seen=[];
  const cn=e=>(typeof e.className==='string'&&e.className.trim().split(' ')[0])
    ||e.tagName.toLowerCase();
  const vis=e=>!e.checkVisibility||e.checkVisibility(
    {contentVisibilityAuto:true,visibilityProperty:true});
  const box=e=>e.getBoundingClientRect();
  const cv=document.createElement('canvas').getContext('2d');
  /* `.cctable` and the galleries are deliberately not in this list: the first
     puts `display:contents` rows between the grid and its cells, so its
     children are not its items, and a gallery's last row is short by
     construction. */
  document.querySelectorAll('#content,.dash,.tpane,.cols3,.grid2').forEach(g=>{
    const st=getComputedStyle(g);
    if(st.display!=='grid')return;
    const tracks=st.gridTemplateColumns.trim().split(/\\s+/)
      .filter(x=>parseFloat(x)>0.5).length;
    const kids=[...g.children].filter(e=>vis(e)&&box(e).height>0);
    if(tracks<2||!kids.length)return;
    seen.push('grid:'+cn(g)+':'+tracks);
    /* the CONTENT width, not the border box: #content carries 26px of padding
       each side, and comparing a full-row card against the padded width made
       every `.wide` card look like a row one item short. */
    const gw=g.clientWidth-parseFloat(st.paddingLeft||0)
      -parseFloat(st.paddingRight||0),rows=new Map();
    kids.forEach(e=>{const b=box(e),k=Math.round(b.top/8);
      if(!rows.has(k))rows.set(k,[]);rows.get(k).push([e,b]);});
    const rl=[...rows.values()];
    rl.forEach((row,i)=>{
      const top=Math.min(...row.map(([,b])=>b.top));
      const hi=Math.max(...row.map(([,b])=>b.bottom));
      const lo=Math.min(...row.map(([,b])=>b.bottom));
      const h=hi-top,who=row.map(([e])=>cn(e)).join(',');
      /* a single item as wide as the grid is a band, not a row one short */
      const band=row.length===1&&row[0][1].width>=gw-2;
      if(row.length>1&&hi-lo>Math.max(140,h*0.3))
        out.push(cn(g)+' row '+(i+1)+' ragged by '+Math.round(hi-lo)+'px ['+who+']');
      const holes=tracks-row.length;
      if(!band&&holes>0&&rl.length>1&&(holes/tracks)*h>260)
        out.push(cn(g)+' row '+(i+1)+' wastes '+holes+' of '+tracks
          +' cells ('+Math.round((holes/tracks)*gw)+'x'+Math.round(h)+'px) ['+who+']');
    });
  });
  /* A pile has no rows to be ragged, so the equivalent measurement is how far
     out of balance its COLUMNS are. Multicol balances them itself, which is the
     whole reason it is used here, so anything left is a card too tall to move
     — and that is worth seeing rather than trusting. */
  document.querySelectorAll('.pile').forEach(p=>{
    const kids=[...p.children].filter(e=>vis(e)&&box(e).height>0);
    if(!kids.length)return;
    seen.push('pile:'+kids.length);
    /* A spanning card ENDS one balanced run and STARTS another, so the column
       above it and the column below it are not the same column. Grouping by
       `left` across the whole pile measured from the top of the first run to
       the bottom of the last and counted the spanning card's own height in
       between: the Memory tab, whose two runs are each balanced, reported a
       1433px imbalance it does not have. */
    const runs = [[]];
    kids.forEach(e => {const b = box(e);
      if (b.width >= p.clientWidth - 2) {runs.push([]); return;}
      runs[runs.length - 1].push(b);});
    runs.forEach(run => {
      if (run.length < 2) return;
      const cols = new Map();
      run.forEach(b => {const k = Math.round(b.left / 8);
        if (!cols.has(k)) cols.set(k, []); cols.get(k).push(b);});
      if (cols.size < 2) return;
      const spans = [...cols.values()].map(bs =>
        Math.max(...bs.map(b => b.bottom)) - Math.min(...bs.map(b => b.top)));
      const gap = Math.max(...spans) - Math.min(...spans);
      /* A column is a stack of INDIVISIBLE cards, so an imbalance smaller than
         the tallest card in the run is arithmetic and not a layout fault: no
         rearrangement could improve it, and a fixed 260px threshold was
         reporting three pages where the shortest possible column already held
         every card it could. Above the tallest card something is genuinely not
         flowing — every card in one column, or one too tall to move. */
      const tallest = Math.max(...run.map(b => b.height));
      if (gap > tallest + 16)
        out.push('pile columns out of balance by ' + Math.round(gap)
          + 'px [' + spans.map(Math.round).join('/') + '], tallest card '
          + Math.round(tallest) + 'px');
    });
  });
  document.querySelectorAll('#content .card').forEach(c=>{
    /* A pane is not a card. Both halves of a split are stretched to the height
       of the row on purpose — that is what stops the short one leaving a dark
       column — so the space under a short detail is the surface it sits on,
       not a hole between two things. `ragged` on the .tpane grid is what
       guards these instead, and it is the stronger check: it fails the moment
       the two stop being level. */
    if(c.parentElement&&c.parentElement.classList.contains('tpane'))return;
    const kids=[...c.children].filter(e=>vis(e)&&box(e).height>0).map(box);
    if(!kids.length)return;
    seen.push('card:'+cn(c));
    const st=getComputedStyle(c);
    const floor=box(c).bottom-parseFloat(st.paddingBottom||0)
      -parseFloat(st.borderBottomWidth||0);
    const slack=floor-Math.max(...kids.map(b=>b.bottom));
    if(slack>40)out.push('card '+cn(c)+' has '+Math.round(slack)+'px of empty floor');
  });
  /* A cell's BOX is as tall as its row, so measuring that says only "some
     other column in this row is tall" — the first cut of this check reported
     twenty cells that were a perfectly ordinary one line inside a 66px row.
     What is wanted is the height of this cell's own INLINE CONTENT, which a
     Range over its contents gives directly: one client rect per line box. */
  const rng=document.createRange();
  document.querySelectorAll('#content .tbl').forEach(t=>{
    if(getComputedStyle(t).display!=='table')return;   /* stacked mode is block */
    seen.push('table');
    const blocky=td=>[...td.children].some(k=>{
      const d=getComputedStyle(k).display;
      return d==='block'||d==='flex'||d==='grid'||d==='table';});
    let worst=0,who='';
    t.querySelectorAll('td,th').forEach(td=>{
      if(blocky(td)||!td.textContent.trim())return;
      const cs=getComputedStyle(td);
      const lh=parseFloat(cs.lineHeight)||parseFloat(cs.fontSize)*1.4;
      rng.selectNodeContents(td);
      const rs=[...rng.getClientRects()].filter(r=>r.height>0);
      if(!rs.length)return;
      const tall=Math.max(...rs.map(r=>r.bottom))-Math.min(...rs.map(r=>r.top));
      /* A LABEL that wraps, not prose that wraps. `approved` beside its
         `error_fix` tag is 18 characters and belongs on one line; a summary
         cell in the same table is a sentence and belongs on several. Counting
         lines alone cannot tell them apart, and at three lines the metric
         slept through the exact cell that was photographed. */
      const txt=td.textContent.trim().replace(/\\s+/g,' ');
      if(tall>lh*1.6&&txt.length<=28&&tall>worst){
        worst=tall;
        who='col '+(td.cellIndex+1)+' ('+Math.round(box(td).width)+'px wide) '
          +JSON.stringify(txt.slice(0,32));}
    });
    if(worst)out.push('table cell wraps to '+Math.round(worst)+'px — '+who);
  });
  document.querySelectorAll('#content p,#content .sub,#content .cchelp')
    .forEach(p=>{
      if(!vis(p))return;
      const b=box(p);
      if(b.height<8||p.textContent.trim().length<140)return;
      seen.push('prose');
      const cs=getComputedStyle(p);
      cv.font=cs.fontSize+' '+cs.fontFamily;
      const ch=b.width/((cv.measureText('0').width)||parseFloat(cs.fontSize)*0.5);
      if(ch>110)out.push('prose runs '+Math.round(ch)+'ch wide ['+cn(p)+']');
    });
  return {issues:[...new Set(out)],probed:seen.length};})()"""


# Does the effort slider's thumb land on the label it names?
#
# Nothing here could answer that before: the audit walked boxes for overflow,
# and a label sitting under the WRONG tick overflows nothing. index.html carried
# six hand-typed labels while config.EFFORTS had grown to seven, so at xhigh the
# thumb sat at 4/6 of the track — under HIGH — and `ultracode` had no label at
# all. Every audit passed, partly because the stub offered two efforts.
#
# The thumb position is computed the way a browser lays a range out: centre to
# centre, inset by half the thumb at each end.
TICKS_JS = """(()=>{
  const sl=document.querySelector('#fEffort'),host=document.querySelector('#fEffTicks');
  if(!sl||!host)return ['effort slider or tick row missing'];
  const r=sl.getBoundingClientRect(),spans=[...host.querySelectorAll('span')],n=+sl.max;
  const thumb=parseFloat(getComputedStyle(document.documentElement)
      .getPropertyValue('--thumb'))||16;
  const bad=[];
  if(spans.length!==n+1)bad.push(`${n+1} stops but ${spans.length} labels`);
  const was=sl.value;
  for(let v=0;v<=n&&v<spans.length;v++){
    sl.value=v; sl.dispatchEvent(new Event('input'));
    const x=r.left+thumb/2+(n?v/n:0)*(r.width-thumb);
    const s=spans[v].getBoundingClientRect();
    const drift=Math.round(x-(s.left+s.width/2));
    if(Math.abs(drift)>12)
      bad.push(`${spans[v].textContent} thumb ${drift}px off its label`);
    const read=document.querySelector('#fEffLabel').textContent.trim();
    if(!read.includes(spans[v].textContent))
      bad.push(`label ${spans[v].textContent} but readout ${read}`);
  }
  sl.value=was; sl.dispatchEvent(new Event('input'));
  return bad;
})()"""

# Same idea as OVERFLOW_JS but scoped to whatever modal is open.
#
# The ancestor walk stops AT the root instead of at its parent. It used to
# include the root, and both roots this probe is used with scroll — `.modal` is
# `max-height:88vh;overflow-y:auto` and `#content` is the app's scroll area — so
# the very first ancestor it looked at said "scrolling" and every element was
# skipped. It reported `clean` for measuring nothing, on modals and on every
# manager page. And a root that IS scrolled legitimately holds content taller
# than itself, so there the right edge is the only fault worth reporting.
MODAL_JS = """(()=>{const m=document.querySelector('.ovl.show .modal');
  if(!m)return [];const mb=m.getBoundingClientRect();const bad=[];
  const scrolly=m.scrollHeight-m.clientHeight>1.5;
  const vis=e=>!e.checkVisibility||e.checkVisibility(
    {contentVisibilityAuto:true,visibilityProperty:true});
  m.querySelectorAll('*').forEach(e=>{
    if(!vis(e))return;
    const b=e.getBoundingClientRect(); if(!b.height)return;
    for(let p=e.parentElement;p&&p!==m;p=p.parentElement){
      const o=getComputedStyle(p).overflowY;
      if(o==='auto'||o==='scroll'||o==='hidden')return;}
    const over=scrolly?b.right-mb.right
                      :Math.max(b.bottom-mb.bottom,b.right-mb.right);
    if(over>1.5)bad.push((typeof e.className==='string'?e.className.split(' ')[0]
      :e.tagName)+'+'+Math.round(over)+'px');});
  return [...new Set(bad)];})()"""

# A pill radius is right for something one line tall and catastrophic for
# anything taller: 999px on a 130px-high card is an ellipse. Flag any element
# whose corner radius exceeds half its own height while being visibly tall.
OVAL_JS = """(()=>{const m=document.querySelector('.ovl.show .modal');
  if(!m)return [];const out=[];
  m.querySelectorAll('*').forEach(e=>{
    const b=e.getBoundingClientRect();
    if(b.height<40||b.width<40)return;
    const r=parseFloat(getComputedStyle(e).borderTopLeftRadius)||0;
    if(r>b.height/2)out.push((typeof e.className==='string'
      ?e.className.split(' ')[0]:e.tagName)+' r='+Math.round(r)
      +' h='+Math.round(b.height));});
  return [...new Set(out)];})()"""


# The same two probes rooted anywhere. Manager pages are cards too, and they
# were as unaudited as modals were before the ellipse: `.preset` now appears on
# the Output styles page as well as in the launch modal, and a row of buttons in
# an `.hrow` overflows exactly the way a card's contents do.
def _rooted(js, root):
    return js.replace("document.querySelector('.ovl.show .modal')", root)


PAGE_ROOT = "document.querySelector('#content')"


def audit_page(pg, label, settle=6000):
    """Overflow + oval audit of one page. Waits for the page to actually RENDER
    first.

    A page still showing its spinner has no cards, so every probe below returns
    an empty list and it prints `clean` — a pass earned by measuring nothing.
    That is the same failure `smoke_gui`'s check floor exists for, one layer
    down: the memory tab grew a fourth fetch, went over the fixed 800ms wait,
    and was audited as a spinner for exactly as long as nobody looked at the
    screenshot."""
    try:
        pg.wait_for_function(
            "()=>{const c=document.querySelector('#content');"
            "return c && !c.querySelector('.spin') && c.querySelector('.card,.slist,.dash');}",
            timeout=settle)
    except Exception:
        print(f'  {label:<11} NEVER RENDERED (still loading after {settle}ms)')
        return False
    bad = pg.evaluate(_rooted(MODAL_JS, PAGE_ROOT))
    ovals = pg.evaluate(_rooted(OVAL_JS, PAGE_ROOT))
    state = ('OVERFLOW ' + '; '.join(bad)) if bad else             ('OVAL ' + '; '.join(ovals)) if ovals else 'clean'
    print(f'  {label:<11} {state}')
    return state == 'clean'


def _rendered(pg, settle=6000):
    try:
        pg.wait_for_function(
            "()=>{const c=document.querySelector('#content');"
            "return c && !c.querySelector('.spin') && c.querySelector('.card,.slist,.dash');}",
            timeout=settle)
        return True
    except Exception:
        return False


#: How many containers, cards, tables and paragraphs the space audit must have
#: looked at across the whole run before its silence means anything. A page that
#: never rendered, a selector that stopped matching or a probe accidentally
#: unreachable all read exactly like "clean" — the lesson smoke_gui's FLOOR
#: already carries, one tool over. Measured: 861, over 19 pages, 9 project tabs
#: and 8 looks at three widths each. The floor is well under that because a
#: probe is allowed to find less when a page legitimately holds less; it is not
#: allowed to find almost nothing.
# 844 on the current app. It was 600 when the card scan still walked the two
# panes of every split; those left it (a pane's empty bottom is not a card's
# empty floor) and the floor has to come back UP to keep meaning something —
# a probe that stops finding containers reports "clean", and a floor 244 below
# what the run actually reaches would sleep through most of that. Set with a
# margin, not at the number: unwrapping five `.grid2` pairs took 15 containers
# off the count without taking anything off the app.
SPACE_FLOOR = 780

#: filled by audit_space(); main() exits non-zero if it is not empty. Every
#: other audit in this file only PRINTS, which is why `instrument row RAGGED`
#: went unfixed for as long as it did.
SPACE_FAILS = []
SPACE_PROBED = [0]


def audit_space(pg, label):
    """The space audit for whatever is on screen, accumulated for the exit code."""
    r = pg.evaluate(SPACE_JS)
    SPACE_PROBED[0] += r['probed']
    for ln in r['issues']:
        SPACE_FAILS.append(f'{label}: {ln}')
    return r['issues']


def audit_widths(pg, pages, tabs):
    """Every page, at every width the fluid content grid has to survive.

    This is the pass that catches the failure the 940px cap used to hide: a card
    is no longer a fixed measure, so its contents have to fit whatever column
    auto-fill hands it — and the narrowest column happens at the WIDEST viewport,
    where the browser has just fitted one more in. A single-width audit cannot
    see that, which is why every page is walked three times."""
    print(chr(10) + '— content grid fit, per width —')
    total = 0
    for w in WIDTHS:
        pg.set_viewport_size({'width': w, 'height': 1000})
        found = []
        for page in pages:
            pg.evaluate(f"go('{page}')")
            pg.wait_for_timeout(400)
            if not _rendered(pg):
                found.append(f'{page}: NEVER RENDERED')
                continue
            found += [f'{page}: {ln}' for ln in pg.evaluate(GRID_JS)]
            found += [f'{page}: {ln}' for ln in audit_space(pg, f'{w}px {page}')]
        pg.evaluate("openProject(ST.projects[0])")
        pg.wait_for_timeout(500)
        for tab in tabs:
            pg.evaluate(f"TAB='{tab}';go('project')")
            pg.wait_for_timeout(400)
            if not _rendered(pg):
                found.append(f'tab {tab}: NEVER RENDERED')
                continue
            found += [f'tab {tab}: {ln}' for ln in pg.evaluate(GRID_JS)]
            found += [f'tab {tab}: {ln}'
                      for ln in audit_space(pg, f'{w}px tab {tab}')]
        pg.evaluate("go('home')")
        pg.wait_for_timeout(400)
        found += [f'home: {ln}' for ln in audit_space(pg, f'{w}px home')]
        cols = pg.evaluate(
            "getComputedStyle(document.querySelector('#content'))"
            ".gridTemplateColumns.trim().split(/\\s+/).length")
        print(f'  {w}px  {cols} column(s)  {"clean" if not found else str(len(found))+" issue(s)"}')
        for ln in found:
            print('    ' + ln)
        total += len(found)
    pg.set_viewport_size({'width': 1600, 'height': 1000})
    return total


def main():
    from playwright.sync_api import sync_playwright
    os.makedirs(OUT, exist_ok=True)
    srv = ThreadingHTTPServer(('127.0.0.1', PORT), sg.H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    errs = []
    with sync_playwright() as pw:
        # SwiftShader, so the screenshots actually contain the stage rather than
        # the static-gradient fallback (same reason as smoke_gui).
        br = pw.chromium.launch(args=[
            '--use-gl=angle', '--use-angle=swiftshader',
            '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'])
        pg = br.new_page(viewport={'width': 1600, 'height': 1000})
        pg.on('pageerror', lambda e: errs.append(str(e)))
        pg.goto(f'http://127.0.0.1:{PORT}/?k={sg.gui.TOKEN}')   # / is token-gated
        pg.wait_for_timeout(2500)
        print('stage:', pg.evaluate(
            "STAGE.ok?('live · '+STAGE.scene+(STAGE._post?' + bloom':'')):'FALLBACK'"))

        print('— overflow audit (dashboard cards) —')
        for line in pg.evaluate(OVERFLOW_JS):
            print('  ' + line)
        print('\ncard heights:', pg.evaluate(
            "[...document.querySelectorAll('.dash>.card')].map(c=>"
            "(c.className.match(/d-[\\w]+/)||['?'])[0]+':'"
            "+Math.round(c.getBoundingClientRect().height))"))
        rows = pg.evaluate(IHEIGHTS_JS)
        print('instrument rows level:',
              ' | '.join('/'.join(str(h) for h in r) for r in rows)
              + (' ✓' if all(len(set(r)) == 1 for r in rows) else ' RAGGED'))
        print('skeletons still on screen:',
              pg.evaluate("document.querySelectorAll('.shimmer').length"))
        print('readouts:', pg.evaluate(
            "[...document.querySelectorAll('.iread b')].map(e=>e.textContent)"))

        for name, w, h in (('dash', 1600, 1000), ('dash-narrow', 820, 1000)):
            pg.set_viewport_size({'width': w, 'height': h})
            pg.wait_for_timeout(700)
            pg.screenshot(path=os.path.join(OUT, f'_shot_{name}.png'))
        pg.set_viewport_size({'width': 1600, 'height': 1000})
        for page in ('usage', 'mcp', 'accounts', 'logs', 'settings'):
            pg.evaluate(f"go('{page}')")
            pg.wait_for_timeout(800)
            pg.screenshot(path=os.path.join(OUT, f'_shot_{page}.png'))

        # ── modals ──
        # The overflow audit only ever walked `.dash>.card`, so nothing in this
        # tool had ever looked at a modal. That is how a pill radius applied to
        # the launch presets shipped: every preset rendered as an ELLIPSE with
        # its own text outside the shape, on a screen the audit could not see.
        print(chr(10) + '— modal audit —')
        for name, opener in (
            ('launch', "askLaunch({title:'New session',sub:'Demo',isNew:true,"
                       "path:'/demo/acme-api',enc:'demo-acme-api',"
                       "choice:'new',cfgdir:''})"),
            ('guide', "openGuide&&openGuide()"),
            # the activity drawer renders from DASH_ACT, which the dashboard
            # poll has already populated by the time the audit reaches here
            ('activity', "openActivity&&openActivity()"),
        ):
            try:
                pg.evaluate(opener)
            except Exception as e:
                print(f'  {name:<8} could not open — {str(e)[:60]}')
                continue
            pg.wait_for_timeout(500)
            shown = pg.evaluate(
                "!!document.querySelector('.ovl.show .modal')")
            if not shown:
                print(f'  {name:<8} did not open')
                continue
            bad = pg.evaluate(MODAL_JS)
            # a control whose corner radius exceeds half its own height is a
            # pill, and a pill that is not one line tall is an ellipse
            ovals = pg.evaluate(OVAL_JS)
            state = 'clean'
            if bad:
                state = 'OVERFLOW ' + '; '.join(bad)
            elif ovals:
                state = 'OVAL ' + '; '.join(ovals)
            print(f'  {name:<8} {state}')
            if name == 'launch':
                # the effort slider lives behind Advanced ▸ "Pin an exact model"
                pg.evaluate("(()=>{const d=document.querySelector('.ovl.show details');"
                            "if(d)d.open=true;const c=document.querySelector('#fPinModel');"
                            "if(c&&!c.checked){c.checked=true;"
                            "c.dispatchEvent(new Event('change'));}})()")
                pg.wait_for_timeout(300)
                ticks = pg.evaluate(TICKS_JS)
                print('  %-8s %s' % ('  ticks', '; '.join(ticks) if ticks
                                     else 'every stop on its own label'))
            pg.screenshot(path=os.path.join(OUT, f'_modal_{name}.png'))
            pg.evaluate("document.querySelectorAll('.ovl').forEach("
                        "o=>o.classList.remove('show'))")
            pg.wait_for_timeout(200)

        # ── manager pages ──
        print(chr(10) + '— page audit —')
        # from NAV rather than a hardcoded list — see the same fix in
        # smoke_gui: the list had fallen a page behind, and an unaudited page
        # is where a wide table quietly breaks card fit
        for page in pg.evaluate('NAV.map(n => n[0])'):
            pg.evaluate(f"go('{page}')")
            pg.wait_for_timeout(700)
            audit_page(pg, page)
            # agents/skills/hooks are three of the densest pages in the app and
            # each groups its rows under a heading now; the overflow audit sees
            # a card that fits, not a list that reads
            if page in ('plugins', 'ostyles', 'client',
                        'agents', 'skills', 'hooks'):
                pg.screenshot(path=os.path.join(OUT, f'_shot_{page}.png'))
        # ── project tabs ──
        # The page walk above only drives the GLOBAL pages; the project side is
        # where most of the app lives, and it had never been captured.
        print(chr(10) + '— project tabs —')
        pg.evaluate("openProject(ST.projects[0])")
        pg.wait_for_timeout(800)
        tabs = pg.evaluate('TABS.map(t => t[0])')        # derived, not a 3-of-9 copy
        for tab in tabs:
            pg.evaluate(f"TAB='{tab}';go('project')")
            pg.wait_for_timeout(800)
            audit_page(pg, 'tab ' + tab)
            pg.screenshot(path=os.path.join(OUT, f'_shot_tab_{tab}.png'))
        pg.evaluate("go('home')")
        pg.wait_for_timeout(600)

        # ── the fluid grid, at every width ──
        audit_widths(pg, pg.evaluate('NAV.map(n => n[0])'), tabs)

        # ── per-skin pass ──
        # A skin changes card geometry, so it can break fit in ways the default
        # skin never would (a 3px border and a hard shadow, a clip-path, a
        # 0-radius panel). Shoot and audit every one.
        print('\n— per-skin audit —')
        pg.evaluate("go('home')")
        pg.wait_for_timeout(900)
        # worlds first (each locks its own palette), then the classic skins
        looks = ([('world', w) for w in pg.evaluate("Object.keys(ST.worlds||{})")]
                 + [('skin', s) for s in pg.evaluate("ST.classic_skins||[]")])
        for kind, sk in looks:
            if kind == 'world':
                pg.evaluate(f"ST.world='{sk}';applyTheme(ST.theme)")
            else:
                pg.evaluate(f"ST.world='';ST.skin='{sk}';applyTheme(ST.theme)")
            pg.wait_for_timeout(500)
            # every width, not just one: a skin's 3px border and hard shadow
            # break fit at the narrowest COLUMN, and the narrowest column shows
            # up at the widest viewport, where auto-fill has added one more
            for w in WIDTHS:
                pg.set_viewport_size({'width': w, 'height': 1000})
                pg.wait_for_timeout(320)
                bad = [ln for ln in pg.evaluate(OVERFLOW_JS) if 'clean' not in ln]
                bad += pg.evaluate(GRID_JS)
                # a skin changes card padding, border weight and cell padding,
                # so it can open a hole the default skin does not have
                bad += audit_space(pg, f'{sk} {w}px home')
                heights = pg.evaluate(IHEIGHTS_JS)
                even = all(len(set(r)) == 1 for r in heights)
                state = 'clean' if (not bad and even) else (
                    ('OVERFLOW ' + '; '.join(bad)) if bad else f'RAGGED {heights}')
                print(f'  {sk:<10} {w:>5}px  {state}')
            pg.set_viewport_size({'width': 1600, 'height': 1000})
            pg.wait_for_timeout(400)
            pg.screenshot(path=os.path.join(OUT, f'_skin_{sk}.png'))
        pg.evaluate("ST.world='';ST.skin='';applyTheme(ST.theme)")
        br.close()
    srv.shutdown()
    print('\nJS errors:', errs if errs else 'none')
    print('shots →', OUT)
    if '--docs' in sys.argv:
        export_docs()

    # ── the space audit's verdict ──
    # Grouped by finding rather than by page: one composition bug shows up on
    # three widths and eight skins, and printing it twenty-four times buries
    # the other nineteen.
    print(chr(10) + '— space audit —')
    print(f'  probed {SPACE_PROBED[0]} containers/cards/tables/paragraphs'
          f' (floor {SPACE_FLOOR})')
    shapes = {}
    for f in SPACE_FAILS:
        where, _, what = f.partition(': ')
        shapes.setdefault(what, []).append(where)
    for what, wheres in sorted(shapes.items(), key=lambda kv: -len(kv[1])):
        print(f'  {len(wheres):>3}x {what}')
        print('       ' + ', '.join(sorted(set(wheres))[:6])
              + (' …' if len(set(wheres)) > 6 else ''))
    if SPACE_PROBED[0] < SPACE_FLOOR:
        print(f'  FAIL only {SPACE_PROBED[0]} things measured — the probe is '
              f'not reaching the pages')
        return 1
    if shapes:
        print(f'  FAIL {len(SPACE_FAILS)} finding(s) in {len(shapes)} shape(s)')
        return 1
    print('  clean')
    return 0


#: the captures the README uses. `references/` is gitignored — it holds
#: third-party design material we cannot redistribute — so the handful of shots
#: that ship are copied into a tracked directory deliberately, by name, rather
#: than by publishing the whole scratch folder.
DOC_SHOTS = {
    '_shot_dash.png': 'gui-dashboard.png',
    '_shot_tab_sessions.png': 'gui-sessions.png',
    '_shot_tab_memory.png': 'gui-memory.png',
    '_shot_client.png': 'gui-claude-code.png',
    '_shot_usage.png': 'gui-usage.png',
    '_skin_graph.png': 'gui-skin-graph.png',
    '_skin_crt.png': 'gui-skin-crt.png',
}


def export_docs():
    """Publish into BOTH sites — the same reason make_og_card writes twice.

    mkdocs reads `docs/img` and the Next site reads `www/public/img`, and they
    embed the same captures. Copying to one and remembering the other by hand is
    how a re-shoot ships with the docs updated and the site a release behind."""
    import shutil
    dests = [os.path.join(_ROOT, 'docs', 'img'),
             os.path.join(_ROOT, 'www', 'public', 'img')]
    for dest in dests:
        os.makedirs(dest, exist_ok=True)
        n = 0
        for src, name in DOC_SHOTS.items():
            p = os.path.join(OUT, src)
            if not os.path.isfile(p):
                print('  MISSING', src)
                continue
            shutil.copyfile(p, os.path.join(dest, name))
            n += 1
        print('exported %d/%d shots → %s' % (n, len(DOC_SHOTS), dest))


if __name__ == '__main__':
    sys.exit(main())
