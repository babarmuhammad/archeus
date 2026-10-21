(function () {
  'use strict';

  var TAU = Math.PI * 2;
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
  var CORE = { x: 500, y: 320 };
  var IVORY = '#EFE9DA';
  var STATE = {
    waiting: { word: 'Needs you', color: '#F2B544' },
    running: { word: 'Running', color: '#6FB1FF' },
    done: { word: 'Done', color: '#6FD39A' },
    idle: { word: 'Idle', color: '#9AA5B8' },
    exec: { word: 'Execution', color: IVORY },
    planning: { word: 'Planning', color: '#B79CFF' },
    connected: { word: 'Connected', color: '#6FD39A' },
    recent: { word: 'Recent', color: '#6FB1FF' },
    future: { word: 'Future contract', color: '#9AA5B8' }
  };
  var RANK = { waiting: 0, running: 1, idle: 2, done: 3 };
  var PHASES = ['Understand', 'Plan', 'Approve', 'Run', 'Verify', 'Review'];
  var NEW_OFFSETS = [[-120, 92], [112, 104], [-150, -4], [128, -2]];

  var projects = [
    { id: 'archeus', name: 'Archeus', x: 300, y: 250, hue: '#7FCFC0' },
    { id: 'notes', name: 'Notes', x: 820, y: 230, hue: '#E7A3AE' },
    { id: 'atlas', name: 'Atlas', x: 640, y: 470, hue: '#C7B2F0' }
  ];

  var missions = [
    { id: 'm-search', title: 'Search provenance', project: 'archeus', branch: 'feat/search', state: 'waiting', stateText: 'Review plan', phase: 2, dx: -95, dy: -70, what: 'Search recorded sources and show where each result came from.', latest: 'Plan v1 waiting for your decision.', task: 'Plan v1, 3 tasks, not started.', exec: false },
    { id: 'm-date', title: 'Fix date test', project: 'archeus', branch: 'fix/date-test', state: 'running', stateText: 'Verifying', phase: 4, dx: 90, dy: -40, what: 'Run the date test suite and confirm the fix.', latest: 'Tool result received.', task: 'not recorded', exec: true },
    { id: 'm-done', title: 'Write changelog', project: 'archeus', branch: 'docs/changelog', state: 'done', stateText: 'Review passed', phase: 6, dx: -40, dy: 95, what: 'Summarise the merged changes for the release.', latest: 'Review passed.', task: 'none', exec: false },
    { id: 'm-index', title: 'Index notes', project: 'notes', branch: 'feat/index', state: 'idle', stateText: 'Not started', phase: -1, dx: -150, dy: -30, what: 'Build an index over the notes folder.', latest: 'none recorded', task: 'none', exec: false },
    { id: 'm-read', title: 'Reading list export', project: 'notes', branch: 'docs/reading', state: 'done', stateText: 'Done', phase: 6, dx: -10, dy: -110, what: 'Export the reading list as a file.', latest: 'Export completed.', task: 'none', exec: false },
    { id: 'm-map', title: 'Map relations', project: 'atlas', branch: 'feat/map', state: 'idle', stateText: 'Not started', phase: -1, dx: -110, dy: -40, what: 'Map recorded relations between notes.', latest: 'none recorded', task: 'none', exec: false },
    { id: 'm-export', title: 'Export graph', project: 'atlas', branch: 'fix/export', state: 'done', stateText: 'Review passed', phase: 6, dx: 120, dy: 30, what: 'Export the graph as an image.', latest: 'Review passed.', task: 'none', exec: false }
  ];

  var plans = {
    'm-search': {
      version: 1,
      why: 'Plan approval required.',
      tasks: [
        { key: 't1', text: 'Read the recorded sources for the search index.' },
        { key: 't2', text: 'Attach a provenance link to each result.' },
        { key: 't3', text: 'Add a test that every result links to a source.' }
      ],
      approve: 'Approving starts the run of 3 tasks on feat/search.',
      request: 'Sends the mission back to the planner with your note and the selected comments. Approval of v1 ends.',
      reject: 'Cancels the mission. A decided approval cannot be changed. No undo.'
    }
  };

  var comments = [];
  var planId = 'm-search';
  var planNote = '';
  var counter = 0;
  var stopArmed = 0;
  var pendingOk = '';
  var sheetOpen = null;
  var lastStar = null;

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function find(id) { return missions.filter(function (m) { return m.id === id; })[0]; }
  function projectOf(id) { return projects.filter(function (p) { return p.id === id; })[0]; }
  function count(state) { return missions.filter(function (m) { return m.state === state; }).length; }
  function isLive(m) { return m.state === 'waiting' || m.state === 'running'; }
  function stateLine(m) { return STATE[m.state].word + ', ' + m.stateText; }
  function say(text) { $('#say').textContent = text; }
  function sorted(list) { return list.slice().sort(function (a, b) { return RANK[a.state] - RANK[b.state]; }); }
  function sentence() {
    var w = count('waiting'), r = count('running');
    if (!w && !r) return 'Nothing running. Tell Archeus what to do.';
    return w + ' needs you, ' + r + ' running';
  }
  function commentsFor(id) { return comments.filter(function (c) { return c.mission === id; }); }
  function selectedComments() { return comments.filter(function (c) { return c.mission === planId && c.carry; }); }
  function rgba(hex, a) {
    var n = parseInt(hex.slice(1), 16);
    return 'rgba(' + (n >> 16 & 255) + ',' + (n >> 8 & 255) + ',' + (n & 255) + ',' + a + ')';
  }
  function missionPos(m) {
    var p = projectOf(m.project);
    return { x: p.x + m.dx, y: p.y + m.dy };
  }

  function nowScene() {
    var sc = {
      view: { x: 150, y: 90, w: 830, h: 500 },
      core: { x: CORE.x, y: CORE.y },
      projects: [], nodes: [], links: [], parent: {}
    };
    projects.forEach(function (p) {
      var ms = missions.filter(function (m) { return m.project === p.id; });
      var active = ms.some(isLive);
      sc.projects.push({ id: p.id, name: p.name, x: p.x, y: p.y, hue: p.hue, count: ms.length, live: ms.filter(isLive).length, active: active });
      sc.parent[p.id] = 'core';
      sc.links.push({ a: 'core', b: p.id, hue: p.hue, kind: 'project' });
      ms.forEach(function (m) {
        var pos = missionPos(m);
        sc.nodes.push({ id: m.id, kind: 'mission', state: m.state, x: pos.x, y: pos.y, live: isLive(m), title: m.title, sub: m.branch, st: STATE[m.state].word, detail: m.stateText, parent: p.id, hue: p.hue, hit: true, below: false });
        sc.parent[m.id] = p.id;
        sc.links.push({ a: p.id, b: m.id, hue: p.hue, kind: 'mission', state: m.state, live: isLive(m) });
        if (m.exec) {
          var ex = m.id + '-exec';
          sc.nodes.push({ id: ex, kind: 'exec', state: 'exec', x: pos.x, y: pos.y + 72, live: m.state === 'running', title: 'Codex', sub: 'execution', st: '', parent: m.id, hit: false });
          sc.parent[ex] = m.id;
          sc.links.push({ a: m.id, b: ex, hue: IVORY, kind: 'exec', live: m.state === 'running' });
        }
      });
    });
    return sc;
  }

  function missionScene(m) {
    var p = projectOf(m.project);
    var live = isLive(m);
    var sc = {
      view: { x: 60, y: 110, w: 880, h: 440 },
      core: { x: 150, y: 300 },
      projects: [{ id: p.id, name: p.name, x: 430, y: 300, hue: p.hue, count: missions.filter(function (x) { return x.project === p.id; }).length, live: missions.filter(function (x) { return x.project === p.id && isLive(x); }).length, active: live }],
      nodes: [{ id: m.id, kind: 'mission', state: m.state, x: 700, y: 300, live: live, title: m.title, sub: m.branch, st: STATE[m.state].word, detail: m.stateText, parent: p.id, hue: p.hue, hit: false, below: false }],
      links: [{ a: 'core', b: p.id, hue: p.hue, kind: 'project' }, { a: p.id, b: m.id, hue: p.hue, kind: 'mission', state: m.state, live: live }],
      parent: {}
    };
    sc.parent[p.id] = 'core';
    sc.parent[m.id] = p.id;
    if (m.exec) {
      sc.nodes.push({ id: m.id + '-exec', kind: 'exec', state: 'exec', x: 700, y: 470, live: m.state === 'running', title: 'Codex', sub: 'execution', st: '', parent: m.id, hit: false });
      sc.parent[m.id + '-exec'] = m.id;
      sc.links.push({ a: m.id, b: m.id + '-exec', hue: IVORY, kind: 'exec', live: m.state === 'running' });
    }
    return sc;
  }

  function phoneScene() {
    var list = sorted(missions).slice(0, 3);
    var slots = [[250, 430], [750, 430], [500, 500]];
    var sc = {
      view: { x: 120, y: 90, w: 760, h: 470 },
      core: { x: 500, y: 200 },
      projects: [], nodes: [], links: [], parent: {}
    };
    list.forEach(function (m, i) {
      sc.nodes.push({ id: m.id, kind: 'mission', state: m.state, x: slots[i][0], y: slots[i][1], live: isLive(m), title: m.title, sub: '', st: STATE[m.state].word, detail: m.stateText, parent: 'core', hue: '#7FCFC0', hit: true, below: true });
      sc.parent[m.id] = 'core';
      sc.links.push({ a: 'core', b: m.id, hue: '#7FCFC0', kind: 'mission', state: m.state, live: isLive(m) });
    });
    sc.overflow = missions.length - list.length;
    return sc;
  }

  function sharedScene() {
    var nodes = [
      { id: 'planner', kind: 'agent', state: 'waiting', x: 250, y: 150, live: true, title: 'Planner', sub: 'Search provenance', st: 'Needs you', hit: false, parent: 'core' },
      { id: 'codex', kind: 'agent', state: 'running', x: 750, y: 150, live: true, title: 'Codex', sub: 'Fix date test', st: 'Running', hit: false, parent: 'core' },
      { id: 'desktop', kind: 'device', state: 'connected', x: 230, y: 500, live: false, title: 'This desktop', sub: '', st: 'Connected', hit: false, parent: 'core' },
      { id: 'phone', kind: 'device', state: 'recent', x: 500, y: 560, live: false, title: 'Paired phone', sub: '', st: 'Recent', hit: false, parent: 'core' },
      { id: 'other', kind: 'device', state: 'future', x: 770, y: 500, live: false, title: 'Other people', sub: 'Future contract, not available', st: '', hit: false, parent: 'core' }
    ];
    var sc = { view: { x: 60, y: 90, w: 880, h: 500 }, core: { x: CORE.x, y: CORE.y }, projects: [], nodes: nodes, links: [], parent: {} };
    nodes.forEach(function (n) {
      sc.parent[n.id] = 'core';
      sc.links.push({ a: 'core', b: n.id, hue: n.kind === 'agent' ? STATE[n.state].color : IVORY, kind: n.kind, state: n.state, live: n.live });
    });
    return sc;
  }

  function makeStage(root, opts) {
    var S = {
      root: root,
      fx: $('.fx', root),
      sky: $('.sky', root),
      world: $('.world', root),
      card: $('.card', root),
      ctx: null,
      w: 0, h: 0, dpr: 1,
      scene: null, cam: null, focus: null, hover: null, cardFor: null,
      nodes: {}, meta: {},
      last: 0, raf: 0,
      onPick: opts && opts.onPick ? opts.onPick : null
    };
    S.ctx = S.fx.getContext('2d');

    function resize() {
      var w = root.clientWidth, h = root.clientHeight;
      if (!w || !h) return false;
      S.w = w; S.h = h;
      S.dpr = Math.min(window.devicePixelRatio || 1, 2);
      S.fx.width = Math.round(w * S.dpr);
      S.fx.height = Math.round(h * S.dpr);
      S.sky.width = Math.round((w + 60) * S.dpr);
      S.sky.height = Math.round((h + 60) * S.dpr);
      paintSky();
      return true;
    }

    function paintSky() {
      var g = S.sky.getContext('2d');
      var W = S.sky.width / S.dpr, H = S.sky.height / S.dpr;
      g.setTransform(S.dpr, 0, 0, S.dpr, 0, 0);
      g.clearRect(0, 0, W, H);
      var seed = 7 + Math.round(W);
      var rnd = function () {
        seed = (seed * 16807) % 2147483647;
        return seed / 2147483647;
      };
      for (var i = 0; i < 240; i++) {
        var depth = rnd();
        var r = 0.3 + depth * 0.9;
        g.fillStyle = 'rgba(239,233,218,' + (0.12 + depth * 0.45).toFixed(3) + ')';
        g.beginPath();
        g.arc(rnd() * W, rnd() * H, r, 0, TAU);
        g.fill();
      }
    }

    function view() { return S.scene ? S.scene.view : null; }

    function baseScale() {
      var v = view();
      return Math.min(S.w / v.w, S.h / v.h) * 0.9;
    }

    function goal() {
      if (!S.scene || !S.w) return null;
      var v = view();
      if (S.focus) {
        return { x: S.focus.x, y: S.focus.y, s: baseScale() * S.focus.zoom };
      }
      return { x: v.x + v.w / 2, y: v.y + v.h / 2, s: baseScale() };
    }

    function setFocus(f) {
      S.focus = f;
      kick();
    }

    function litSet() {
      var H = { core: true };
      var sc = S.scene;
      function chain(id) {
        var cur = id, guard = 0;
        while (cur && guard++ < 8) {
          H[cur] = true;
          cur = sc.parent[cur];
        }
      }
      sc.nodes.forEach(function (n) { if (n.live) chain(n.id); });
      sc.projects.forEach(function (p) { if (p.active) chain(p.id); });
      if (S.hover) {
        chain(S.hover);
        sc.nodes.forEach(function (n) { if (n.parent === S.hover) chain(n.id); });
      }
      return H;
    }

    function hasRunning() {
      return S.scene && S.scene.nodes.some(function (n) { return n.state === 'running'; });
    }

    function drawShape(g, n, p, lit, phase) {
      var x = p.x, y = p.y, st = n.state;
      var col = STATE[st] ? STATE[st].color : IVORY;
      g.save();
      g.globalAlpha = lit || n.live ? 1 : (st === 'done' || st === 'idle' ? 0.5 : 0.7);
      if (lit) { g.shadowColor = col; g.shadowBlur = 16; }
      if (n.kind === 'mission' && st === 'waiting') {
        g.strokeStyle = col; g.lineWidth = 1.2; g.setLineDash([3, 4]);
        g.beginPath(); g.arc(x, y, 17, 0, TAU); g.stroke();
        g.setLineDash([]);
        g.fillStyle = col;
        g.beginPath(); g.moveTo(x, y - 9); g.lineTo(x + 9, y); g.lineTo(x, y + 9); g.lineTo(x - 9, y); g.closePath(); g.fill();
      } else if (n.kind === 'mission' && st === 'running') {
        if (phase > 0) {
          var k = (phase * 1.0) % 1;
          g.strokeStyle = rgba('#6FB1FF', (1 - k) * 0.5); g.lineWidth = 1;
          g.beginPath(); g.arc(x, y, 15 + 12 * k, 0, TAU); g.stroke();
        }
        g.strokeStyle = rgba('#6FB1FF', 0.5); g.lineWidth = 1;
        g.beginPath(); g.arc(x, y, 15, 0, TAU); g.stroke();
        g.fillStyle = col;
        g.beginPath();
        g.moveTo(x, y - 11);
        g.quadraticCurveTo(x + 2, y - 2, x + 11, y);
        g.quadraticCurveTo(x + 2, y + 2, x, y + 11);
        g.quadraticCurveTo(x - 2, y + 2, x - 11, y);
        g.quadraticCurveTo(x - 2, y - 2, x, y - 11);
        g.fill();
      } else if (n.kind === 'mission' && st === 'done') {
        g.fillStyle = col;
        g.beginPath(); g.arc(x, y, 8, 0, TAU); g.fill();
        g.strokeStyle = '#0A0D13'; g.lineWidth = 1.8;
        g.beginPath(); g.moveTo(x - 3.5, y); g.lineTo(x - 1, y + 2.6); g.lineTo(x + 3.8, y - 3); g.stroke();
      } else if (n.kind === 'mission') {
        g.fillStyle = '#0A0D13'; g.strokeStyle = col; g.lineWidth = 1.6;
        g.beginPath(); g.arc(x, y, 7.5, 0, TAU); g.fill(); g.stroke();
      } else if (n.kind === 'exec' || n.kind === 'agent') {
        g.strokeStyle = col; g.lineWidth = 1.3;
        g.fillStyle = n.kind === 'agent' ? col : 'rgba(10,13,19,0.9)';
        g.beginPath(); g.moveTo(x, y - 10); g.lineTo(x + 10, y + 7); g.lineTo(x - 10, y + 7); g.closePath();
        g.fill(); g.stroke();
      } else if (n.kind === 'device') {
        g.strokeStyle = col; g.lineWidth = 1.5;
        if (st === 'future') g.setLineDash([3, 3]);
        g.fillStyle = 'rgba(10,13,19,0.9)';
        g.beginPath(); g.rect(x - 12, y - 9, 24, 18); g.fill(); g.stroke();
        g.setLineDash([]);
      }
      g.restore();
    }

    function drawCore(g, c, t, running) {
      var breath = running && t ? 1 + 0.035 * Math.sin(TAU * t / 6000) : 1;
      var glow = g.createRadialGradient(c.x, c.y, 0, c.x, c.y, 120 * breath);
      glow.addColorStop(0, 'rgba(239,233,218,0.24)');
      glow.addColorStop(1, 'rgba(239,233,218,0)');
      g.fillStyle = glow;
      g.beginPath(); g.arc(c.x, c.y, 120 * breath, 0, TAU); g.fill();
      g.fillStyle = IVORY;
      for (var i = 0; i < 4; i++) {
        var ang = Math.PI / 2 * i - Math.PI / 2;
        var L = 34 * breath, W = 3.4;
        var px = -Math.sin(ang) * W, py = Math.cos(ang) * W;
        g.beginPath();
        g.moveTo(c.x + px, c.y + py);
        g.lineTo(c.x + Math.cos(ang) * L, c.y + Math.sin(ang) * L);
        g.lineTo(c.x - px, c.y - py);
        g.closePath();
        g.fill();
      }
      for (var j = 0; j < 4; j++) {
        var ang2 = Math.PI / 4 + Math.PI / 2 * j;
        var L2 = 14 * breath, W2 = 1.8;
        var qx = -Math.sin(ang2) * W2, qy = Math.cos(ang2) * W2;
        g.beginPath();
        g.moveTo(c.x + qx, c.y + qy);
        g.lineTo(c.x + Math.cos(ang2) * L2, c.y + Math.sin(ang2) * L2);
        g.lineTo(c.x - qx, c.y - qy);
        g.closePath();
        g.fill();
      }
      g.save();
      g.shadowColor = IVORY; g.shadowBlur = 18;
      g.beginPath(); g.arc(c.x, c.y, 4.2, 0, TAU); g.fill();
      g.restore();
    }

    function draw(t) {
      if (!S.scene || !S.w || !S.cam) return;
      var sc = S.scene, g = S.ctx, w = S.w, h = S.h, cam = S.cam;
      g.setTransform(S.dpr, 0, 0, S.dpr, 0, 0);
      g.clearRect(0, 0, w, h);
      var pos = {};
      function P(x, y) { return { x: (x - cam.x) * cam.s + w / 2, y: (y - cam.y) * cam.s + h / 2 }; }
      pos.core = P(sc.core.x, sc.core.y);
      sc.projects.forEach(function (p) { pos[p.id] = P(p.x, p.y); });
      sc.nodes.forEach(function (n) { pos[n.id] = P(n.x, n.y); });
      var H = litSet();
      var running = hasRunning();
      var c = pos.core;

      S.sky.style.transform = 'translate3d(' + (-(cam.x - CORE.x) * cam.s * 0.05).toFixed(2) + 'px,' + (-(cam.y - CORE.y) * cam.s * 0.05).toFixed(2) + 'px,0)';

      g.save();
      g.setLineDash([2, 7]);
      g.lineWidth = 1;
      [[170, 0.6, 0.13], [262, 0.34, 0.06]].forEach(function (o) {
        g.strokeStyle = 'rgba(239,233,218,' + o[2] + ')';
        g.beginPath(); g.ellipse(c.x, c.y, o[0] * cam.s, o[0] * cam.s * o[1], -0.16, 0, TAU); g.stroke();
      });
      sc.projects.forEach(function (p) {
        var q = pos[p.id];
        g.strokeStyle = rgba(p.hue, p.active ? 0.3 : 0.1);
        g.beginPath(); g.arc(q.x, q.y, 70 * cam.s, 0, TAU); g.stroke();
      });
      g.restore();

      sc.links.forEach(function (l) {
        var a = pos[l.a], b = pos[l.b];
        if (!a || !b) return;
        var lit = !!(H[l.a] && H[l.b]);
        g.save();
        if (lit) {
          var col = l.kind === 'mission' && l.live ? STATE[l.state].color : (l.hue || IVORY);
          g.strokeStyle = col;
          g.globalAlpha = 0.95;
          g.lineWidth = 1.5;
          g.shadowColor = col; g.shadowBlur = 12;
          if (running && t && l.live) { g.setLineDash([3, 9]); g.lineDashOffset = -(t / 40); }
        } else {
          g.strokeStyle = 'rgba(239,233,218,0.16)';
          g.lineWidth = 0.8;
        }
        g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(b.x, b.y); g.stroke();
        g.restore();
      });

      sc.projects.forEach(function (p) {
        if (!p.active) return;
        var q = pos[p.id];
        var rg = g.createRadialGradient(q.x, q.y, 0, q.x, q.y, 90);
        rg.addColorStop(0, rgba(p.hue, 0.14));
        rg.addColorStop(1, rgba(p.hue, 0));
        g.fillStyle = rg;
        g.beginPath(); g.arc(q.x, q.y, 90, 0, TAU); g.fill();
      });
      sc.projects.forEach(function (p) {
        var q = pos[p.id], lit = !!H[p.id];
        g.save();
        g.globalAlpha = lit ? 1 : 0.6;
        g.fillStyle = p.hue;
        if (lit) { g.shadowColor = p.hue; g.shadowBlur = 14; }
        g.beginPath(); g.arc(q.x, q.y, 5, 0, TAU); g.fill();
        g.strokeStyle = rgba(p.hue, 0.55); g.lineWidth = 1;
        g.beginPath(); g.arc(q.x, q.y, 13, 0, TAU); g.stroke();
        g.restore();
      });

      var order = sc.nodes.slice().sort(function (a, b) { return (H[a.id] ? 1 : 0) - (H[b.id] ? 1 : 0); });
      order.forEach(function (n) {
        var phase = reduce.matches ? 0 : (t || 0) / 2400 + n.x * 0.001;
        drawShape(g, n, pos[n.id], !!H[n.id], phase);
      });

      drawCore(g, c, reduce.matches ? 0 : t, running);

      Object.keys(S.nodes).forEach(function (id) {
        var L = S.nodes[id], q = pos[id];
        if (!q) return;
        if (L.col) L.el.style.transform = 'translate(' + q.x.toFixed(1) + 'px,' + q.y.toFixed(1) + 'px) translate(-50%,' + L.dy + 'px)';
        else L.el.style.transform = 'translate(' + (q.x - 24).toFixed(1) + 'px,' + (q.y - 24).toFixed(1) + 'px)';
        L.el.classList.toggle('dim', !H[id]);
      });

      updateCard(pos);
    }

    function updateCard(pos) {
      var id = S.hover, meta = id && S.meta[id];
      if (!meta || !pos[id]) { S.card.hidden = true; S.cardFor = null; return; }
      if (S.cardFor !== id) {
        S.card.innerHTML = '';
        var k = document.createElement('p'); k.className = 'card-kicker'; k.textContent = meta.kicker;
        var t = document.createElement('p'); t.className = 'card-title'; t.textContent = meta.title;
        S.card.appendChild(k); S.card.appendChild(t);
        meta.lines.forEach(function (line) {
          var p = document.createElement('p'); p.className = 'card-line'; p.textContent = line;
          S.card.appendChild(p);
        });
        S.cardFor = id;
      }
      S.card.hidden = false;
      var cw = S.card.offsetWidth, ch = S.card.offsetHeight;
      var q = pos[id];
      var left = Math.min(Math.max(q.x - cw / 2, 8), S.w - cw - 8);
      var top = q.y - 30 - ch;
      if (top < 8) top = q.y + 30;
      S.card.style.transform = 'translate(' + left.toFixed(1) + 'px,' + top.toFixed(1) + 'px)';
    }

    function item(id, o) {
      var el = document.createElement(o.hit ? 'button' : 'div');
      if (o.hit) el.type = 'button';
      el.className = 'node ' + o.cls + (o.col ? ' col' : '');
      if (o.hue) el.style.setProperty('--hue', o.hue);
      el.innerHTML = '<span class="hit" aria-hidden="true"></span><span class="txt"><span class="nm"></span><span class="st"></span><span class="sub"></span></span>';
      el.querySelector('.nm').textContent = o.title;
      var st = el.querySelector('.st'), sub = el.querySelector('.sub');
      if (o.st) st.textContent = o.st; else st.remove();
      if (o.sub) sub.textContent = o.sub; else sub.remove();
      if (o.hit) {
        el.setAttribute('aria-label', o.aria);
        el.addEventListener('pointerenter', function () { setHover(id); });
        el.addEventListener('pointerleave', function () { setHover(null); });
        el.addEventListener('focus', function () { setHover(id); });
        el.addEventListener('blur', function () { setHover(null); });
        el.addEventListener('click', function () { if (S.onPick) S.onPick(id, o.kind); });
      }
      S.world.appendChild(el);
      S.nodes[id] = { el: el, col: !!o.col, dy: o.dy || 0 };
      if (o.meta) S.meta[id] = o.meta;
    }

    function setHover(id) {
      if (S.hover === id) return;
      S.hover = id;
      draw(0);
      kick();
    }

    function setScene(sc, keepFocus) {
      S.scene = sc;
      if (!keepFocus) S.focus = null;
      S.hover = null; S.cardFor = null;
      S.world.innerHTML = '';
      S.nodes = {}; S.meta = {};
      S.card.hidden = true;
      item('core', { cls: 'k-core', title: 'Archeus', st: 'Core connected', sub: '', col: true, dy: 34 });
      sc.projects.forEach(function (p) {
        item(p.id, {
          cls: 'k-project', hue: p.hue, title: p.name, st: p.count + ' missions, ' + p.live + ' live', sub: '',
          hit: S.onPick !== null, aria: p.name + ', ' + p.count + ' missions, ' + p.live + ' live', kind: 'project', col: true, dy: -24,
          meta: { kicker: 'Project', title: p.name, lines: [p.count + ' missions, ' + p.live + ' live.'] }
        });
      });
      sc.nodes.forEach(function (n) {
        var hit = S.onPick !== null && n.hit;
        var cls = 'k-' + n.kind + ' s-' + n.state + (n.below ? ' below' : '') + (n.live ? ' live' : '');
        item(n.id, {
          cls: cls, title: n.title, st: n.st, sub: n.sub || n.detail || '', hit: hit,
          aria: n.title + ', ' + (n.st || '') + (n.detail ? ', ' + n.detail : ''), kind: n.kind,
          col: !!n.below, dy: -24,
          meta: { kicker: n.kind === 'mission' ? 'Mission' : n.kind === 'exec' ? 'Execution' : n.kind === 'agent' ? 'Agent' : 'Device', title: n.title, lines: [n.st, n.sub || n.detail].filter(Boolean) }
        });
      });
      resize();
      S.cam = goal();
      draw(0);
      kick();
    }

    function stepCam(t) {
      var g = goal();
      if (!g || !S.cam) return false;
      var c = S.cam;
      if (reduce.matches) { S.cam = g; return false; }
      var dt = Math.min(64, t - S.last) / 1000;
      S.last = t;
      var k = 1 - Math.exp(-dt * 9);
      c.x += (g.x - c.x) * k;
      c.y += (g.y - c.y) * k;
      c.s += (g.s - c.s) * k;
      var moving = Math.abs(g.x - c.x) * c.s > 0.2 || Math.abs(g.y - c.y) * c.s > 0.2 || Math.abs(g.s - c.s) / g.s > 0.002;
      if (!moving) S.cam = g;
      return moving;
    }

    function frame(t) {
      S.raf = 0;
      if (document.hidden || !S.scene) return;
      var moving = stepCam(t);
      draw(reduce.matches ? 0 : t);
      if (moving || (!reduce.matches && hasRunning())) S.raf = requestAnimationFrame(frame);
    }

    function kick() {
      if (!S.raf && !document.hidden && S.scene) {
        S.last = performance.now();
        S.raf = requestAnimationFrame(frame);
      }
    }

    function relayout() {
      if (!S.scene || !resize()) return;
      S.cam = goal();
      draw(0);
    }

    root.addEventListener('pointerleave', function () { setHover(null); });

    S.setScene = setScene;
    S.setFocus = setFocus;
    S.relayout = relayout;
    S.kick = kick;
    S.resize = resize;
    return S;
  }

  var nowStage = makeStage($('#now-stage'), {
    onPick: function (id, kind) {
      if (kind === 'project') {
        var p = projectOf(id);
        nowStage.setFocus({ x: p.x, y: p.y, zoom: 2.2 });
        $('#now-overview').hidden = false;
        say('Zoomed into ' + p.name + '. Whole space returns you.');
      } else {
        location.hash = '#/mission/' + id;
      }
    }
  });
  var missionStage = makeStage($('#mission-stage'));
  var sharedStage = makeStage($('#shared-stage'));
  var phoneStage = makeStage($('#phone-stage'), {
    onPick: function (id) { openSheet(id); }
  });

  function renderNow() {
    $('#s-now [data-sentence]').textContent = sentence();
    nowStage.setScene(nowScene(), false);
    $('#now-overview').hidden = true;
    $('#now-list').innerHTML = sorted(missions).map(function (m) {
      return '<li><a href="#/mission/' + m.id + '">' + esc(m.title) + '</a>' +
        '<span class="row-meta">' + esc(projectOf(m.project).name) + ' · ' + esc(m.branch) + '</span>' +
        '<span class="row-state st-' + m.state + '">' + esc(stateLine(m)) + '</span>' +
        (m.state === 'waiting' ? '<a class="row-action" href="#/plan/' + m.id + '">Review plan</a>' : '') + '</li>';
    }).join('');
  }

  function phaseRows(m) {
    return PHASES.map(function (name, i) {
      var mark, word, cls = '';
      if (m.phase === 6 || i < m.phase) { mark = '✓'; word = 'Done'; }
      else if (i === m.phase) { mark = '●'; word = m.state === 'waiting' ? 'Waiting for you' : 'Current'; cls = 'current'; }
      else { mark = '○'; word = 'Not reached'; }
      return '<li class="' + cls + '"><span class="ph-mark" aria-hidden="true">' + mark + '</span><span class="ph-name">' + name + '</span><span class="ph-state">' + word + '</span></li>';
    }).join('');
  }

  function renderMission(id) {
    var m = find(id) || find('m-date');
    var sec = $('#s-mission');
    var p = projectOf(m.project);
    $('[data-m-project]', sec).textContent = p.name;
    $('[data-m-crumb]', sec).textContent = m.title;
    $('[data-m-title]', sec).textContent = m.title;
    $('[data-m-meta]', sec).textContent = p.name + ' · ' + m.branch;
    var st = $('[data-m-state]', sec);
    st.textContent = stateLine(m);
    st.className = 'state-line st-' + m.state;
    missionStage.setScene(missionScene(m), false);
    $('#m-phases').innerHTML = phaseRows(m);
    $('[data-m-latest]', sec).textContent = m.latest;
    $('[data-m-task]', sec).textContent = m.task;
    $('[data-m-links]', sec).innerHTML = plans[m.id]
      ? '<a href="#/plan/' + m.id + '">Plan v' + plans[m.id].version + '</a>'
      : 'No plan recorded.';
  }

  function renderShared() {
    $('#s-shared [data-sentence]').textContent = sentence();
    sharedStage.setScene(sharedScene(), false);
  }

  function closeSheet(silent) {
    var sheet = $('#sheet');
    phoneStage.setFocus(null);
    if (sheet.hidden) return;
    sheet.hidden = true;
    sheet.innerHTML = '';
    sheetOpen = null;
    if (!silent && lastStar && lastStar.isConnected) lastStar.focus();
  }

  function openSheet(id) {
    var m = find(id);
    var n = phoneStage.scene.nodes.filter(function (x) { return x.id === id; })[0];
    if (!n) return;
    lastStar = phoneStage.root.contains(document.activeElement) ? document.activeElement : null;
    phoneStage.setFocus({ x: n.x, y: n.y, zoom: 1.35 });
    var waiting = m.state === 'waiting', p = plans[m.id];
    var why = waiting && p ? p.why : 'Status: ' + stateLine(m) + '.';
    var consequence = waiting && p ? p.approve : 'Core records this run. This prototype changes nothing.';
    var sheet = $('#sheet');
    sheet.innerHTML =
      '<p class="sheet-state st-' + m.state + '">' + esc(stateLine(m)) + '</p>' +
      '<h2 id="sheet-h" tabindex="-1">' + esc(m.title) + '</h2>' +
      '<p><span class="lbl">What</span>' + esc(m.what) + '</p>' +
      '<p><span class="lbl">Why</span>' + esc(why) + '</p>' +
      '<p><span class="lbl">Core (fixture text)</span>' + esc(consequence) + '</p>' +
      '<div class="row"><a class="btn primary" href="' + (waiting ? '#/plan/' : '#/mission/') + m.id + '">' +
      (waiting ? 'Open decision' : 'Open mission') + '</a><button type="button" class="btn" data-act="close-sheet">Close</button></div>';
    sheet.hidden = false;
    sheetOpen = id;
    $('#sheet-h').focus();
  }

  function renderPhone() {
    closeSheet(true);
    $('#s-phone [data-sentence]').textContent = sentence();
    var waiting = missions.filter(function (m) { return m.state === 'waiting'; });
    var sc = phoneScene();
    var line = waiting.length ? 'Waiting for you: ' + waiting.map(function (m) { return m.title; }).join(', ') + '.' : 'Nothing waiting for you.';
    if (sc.overflow > 0) line += ' ' + sc.overflow + ' more on Now.';
    $('[data-phone-line]').textContent = line;
    phoneStage.setScene(sc, false);
  }

  function renderPlan(id) {
    var m = find(id) || find('m-search');
    planId = m.id;
    var p = plans[m.id], sec = $('#s-plan');
    if (!p) {
      $('[data-plan-title]', sec).textContent = m.title;
      $('[data-plan-meta]', sec).textContent = projectOf(m.project).name + ' · ' + m.branch;
      $('[data-plan-why]', sec).textContent = 'No plan is recorded for this mission.';
      $('#plan-tasks').innerHTML = '';
      $('#plan-consequences').innerHTML = '';
      $('[data-plan-count]', sec).textContent = '';
      $('#plan-selected').textContent = '';
      return;
    }
    $('[data-plan-title]', sec).textContent = 'Review plan v' + p.version + ', ' + m.title;
    $('[data-plan-meta]', sec).textContent = projectOf(m.project).name + ' · ' + m.branch + ' · ' + stateLine(m);
    $('[data-plan-why]', sec).textContent = 'Why: ' + p.why;
    $('#plan-tasks').innerHTML = p.tasks.map(function (t) {
      var mine = comments.filter(function (c) { return c.mission === m.id && c.task === t.key; });
      return '<li><p><span class="tk">' + t.key + '</span>' + esc(t.text) + '</p>' +
        '<details><summary>Comment on ' + t.key + ' (' + mine.length + ')</summary>' +
        '<form class="task-comment" data-task="' + t.key + '">' +
        '<label for="c-' + t.key + '">Comment on ' + t.key + '</label>' +
        '<textarea id="c-' + t.key + '" name="body" rows="3" maxlength="2000"></textarea>' +
        '<button type="submit" class="btn">Save comment</button></form>' +
        (mine.length ? '<ul class="comments">' + mine.map(function (c) {
          return '<li><label><input type="checkbox" data-act="carry" data-id="' + c.id + '"' + (c.carry ? ' checked' : '') +
            '> Carry in request changes</label>' + esc(c.body) + '</li>';
        }).join('') + '</ul>' : '') +
        '</details></li>';
    }).join('');
    $('#plan-consequences').innerHTML =
      '<li><strong>Approve plan:</strong> ' + esc(p.approve) + '</li>' +
      '<li><strong>Request changes:</strong> ' + esc(p.request) + '</li>' +
      '<li><strong>Reject:</strong> ' + esc(p.reject) + '</li>' +
      '<li class="small">Consequence lines are fixture text. Core supplies the real ones.</li>';
    $('[data-plan-count]', sec).textContent = commentsFor(m.id).length + ' open comments. They do not block approve.';
    $('#plan-selected').textContent = 'Selected for request changes: ' + selectedComments().length + '.';
    $('#plan-note').value = planNote;
  }

  function confirmBox(title, text, ok) {
    $('#confirm-title').textContent = title;
    $('#confirm-text').textContent = text;
    pendingOk = ok;
    $('#confirm').showModal();
  }

  $('#confirm').addEventListener('close', function () {
    if (this.returnValue === 'ok' && pendingOk) say(pendingOk);
    pendingOk = '';
  });

  function decide(kind) {
    var m = find(planId), p = plans[m.id];
    var note = $('#plan-note').value.trim();
    var sel = selectedComments();
    if (kind === 'approve') {
      return confirmBox('Approve plan v' + p.version + '?',
        'Approve "' + m.title + '" on ' + m.branch + '. ' + p.approve + ' Open comments: ' + commentsFor(m.id).length + ', which do not block approve.',
        'Prototype: nothing was approved. This page records no decision.');
    }
    if (kind === 'reject') {
      return confirmBox('Reject this mission?', p.reject, 'Prototype: nothing was rejected.');
    }
    if (!note && !sel.length) return say('Request changes needs a note or a selected comment.');
    confirmBox('Request changes on plan v' + p.version + '?',
      'Your note: ' + (note || 'none') + '. Selected comments: ' +
      (sel.map(function (c) { return c.task + ' "' + c.body + '"'; }).join('; ') || 'none') + '. ' + p.request,
      'Prototype: request changes would carry your note and ' + sel.length + ' selected comment(s). Nothing was sent.');
  }

  function addMission(title, project, what) {
    var off = NEW_OFFSETS[counter % NEW_OFFSETS.length];
    counter++;
    missions.push({ id: 'm-new-' + counter, title: title, project: project, branch: 'not created', state: 'idle', stateText: 'Not started', phase: -1, dx: off[0], dy: off[1], what: what, latest: 'none recorded', task: 'none', exec: false });
  }

  function stop() {
    var now = Date.now();
    if (stopArmed && now - stopArmed < 3000) {
      stopArmed = 0;
      setStopLabel('Stop');
      say('Prototype: nothing was stopped. No work runs here.');
      return;
    }
    stopArmed = now;
    setStopLabel('Press Stop again');
    say('Press Stop again within 3 seconds. Prototype only.');
    setTimeout(function () {
      if (stopArmed && Date.now() - stopArmed >= 3000) { stopArmed = 0; setStopLabel('Stop'); }
    }, 3100);
  }
  function setStopLabel(t) { $$('.stop-btn').forEach(function (b) { b.textContent = t; }); }

  document.addEventListener('click', function (e) {
    if (e.target.id === 'tell-cancel') {
      $('#tell-text').value = '';
      $('#tell-error').textContent = '';
      return say('Draft cleared. Nothing was sent.');
    }
    if (e.target.id === 'now-overview') {
      nowStage.setFocus(null);
      e.target.hidden = true;
      return say('Whole space.');
    }
    var el = e.target.closest('[data-act]');
    if (!el) return;
    var act = el.getAttribute('data-act');
    if (act === 'close-sheet') closeSheet(false);
    else if (act === 'decide') decide(el.getAttribute('data-kind'));
    else if (act === 'stop') stop();
  });

  document.addEventListener('change', function (e) {
    if (e.target.getAttribute('data-act') !== 'carry') return;
    var id = e.target.getAttribute('data-id');
    comments.forEach(function (c) { if (c.id === id) c.carry = e.target.checked; });
    $('#plan-selected').textContent = 'Selected for request changes: ' + selectedComments().length + '.';
  });

  document.addEventListener('input', function (e) {
    if (e.target.id === 'plan-note') planNote = e.target.value;
  });

  document.addEventListener('keydown', function (e) {
    if (e.key !== 'Escape') return;
    if (sheetOpen) closeSheet(false);
    else if (nowStage.focus) { nowStage.setFocus(null); $('#now-overview').hidden = true; }
  });

  document.addEventListener('submit', function (e) {
    var f = e.target;
    if (f.className === 'task-comment') {
      e.preventDefault();
      var body = f.elements.body.value.trim();
      var task = f.getAttribute('data-task');
      if (!body) return say('Write a comment first.');
      comments.push({ id: 'c' + (++counter), mission: planId, task: task, body: body, carry: false });
      renderPlan(planId);
      $('#s-plan h1').focus();
      say('Comment saved on ' + task + '. It reaches the planner only inside a request-changes decision.');
    } else if (f.id === 'tell-form') {
      e.preventDefault();
      var text = $('#tell-text').value.trim();
      if (!text) {
        $('#tell-error').textContent = 'Write what Archeus should do first.';
        return $('#tell-text').focus();
      }
      $('#tell-error').textContent = '';
      addMission(text.split('\n')[0].slice(0, 48), 'archeus', text);
      $('#tell-text').value = '';
      location.hash = '#/now';
      say('Fake: a star was added to this page only. Nothing was sent or started.');
    } else if (f.id === 'mission-form') {
      e.preventDefault();
      var title = $('#m-title').value.trim();
      if (!title) {
        $('#m-error').textContent = 'Give the mission a title.';
        return $('#m-title').focus();
      }
      $('#m-error').textContent = '';
      var objective = $('#m-objective').value.trim() || 'No objective given.';
      var proj = $('#m-project').value === 'Notes' ? 'notes' : 'archeus';
      addMission(title.slice(0, 120), proj, objective);
      location.hash = '#/now';
      say('Fake: "' + title + '" was added as idle in ' + $('#m-project').value + '. Nothing was created in Core.');
    }
  });

  var SCREENS = {
    now: renderNow,
    mission: renderMission,
    shared: renderShared,
    phone: renderPhone,
    start: function () {},
    plan: renderPlan
  };

  function route() {
    var parts = (location.hash || '#/now').replace(/^#\/?/, '').split('/');
    var name = SCREENS[parts[0]] ? parts[0] : 'now';
    closeSheet(true);
    $$('main > section').forEach(function (s) { s.hidden = s.id !== 's-' + name; });
    $$('.places a').forEach(function (a) {
      if (a.getAttribute('data-nav') === name) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
    SCREENS[name](parts[1]);
    var h = $('#s-' + name + ' h1');
    if (h) h.focus({ preventScroll: true });
  }

  window.addEventListener('resize', function () {
    [nowStage, missionStage, sharedStage, phoneStage].forEach(function (s) { s.relayout(); });
  });
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) [nowStage, missionStage, sharedStage, phoneStage].forEach(function (s) { s.kick(); });
  });
  if (reduce.addEventListener) {
    reduce.addEventListener('change', function () {
      [nowStage, missionStage, sharedStage, phoneStage].forEach(function (s) { s.relayout(); s.kick(); });
    });
  }

  window.addEventListener('hashchange', route);
  route();

  if ('serviceWorker' in navigator && /^https?:$/.test(location.protocol)) {
    navigator.serviceWorker.register('sw.js');
  }
})();
