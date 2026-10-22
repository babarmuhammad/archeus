(function () {
  'use strict';

  /* ---------- Tokens and fixture data (fake) ---------- */

  var TAU = Math.PI * 2;
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
  var IVORY = '#EFE9DA';
  var INK = '#070A10';
  var STATE = {
    waiting: { word: 'Needs you', color: '#F2B544' },
    running: { word: 'Running', color: '#6FB1FF' },
    done: { word: 'Done', color: '#9AA5B8' },
    idle: { word: 'Idle', color: '#9AA5B8' },
    exec: { word: 'Execution', color: IVORY },
    connected: { word: 'Connected', color: '#6FD39A' },
    recent: { word: 'Recent', color: '#6FB1FF' },
    future: { word: 'Future contract', color: '#9AA5B8' }
  };
  var RANK = { waiting: 0, running: 1, idle: 2, done: 3 };
  var PHASES = ['Understand', 'Plan', 'Approve', 'Run', 'Verify', 'Review'];

  // offs: mission positions around the project centre, in stage pixels at full size.
  var projects = [
    { id: 'archeus', name: 'Archeus', hue: IVORY, note: 'Active. Your projects, in context.' },
    { id: 'notes', name: 'Notes', hue: IVORY, note: 'Research and capture evolving context.' },
    { id: 'ideas', name: 'Ideas', hue: IVORY, note: 'Early concepts.' }
  ];

  var missions = [
    { id: 'm-search', title: 'Search provenance', project: 'archeus', branch: 'feat/search', state: 'waiting', stateText: 'Review plan', phase: 2, glyph: 'search', what: 'Search recorded sources and show where each result came from.', latest: 'Plan v1 waiting for your decision.', task: 'Plan v1, 3 tasks, not started.', exec: false, related: [{ key: 'plan', title: 'Plan v1', sub: '3 tasks, not started', glyph: 'list', verb: 'proposes' }], log: ['Plan v1 recorded.', 'Waiting for your decision.'] },
    { id: 'm-date', title: 'Fix date test', project: 'archeus', branch: 'fix/date-test', state: 'running', stateText: 'Verifying', phase: 4, glyph: 'term', what: 'Run the date test suite and confirm the fix.', latest: 'Tool result received.', task: 'Run date suite on fix/date-test and collect the results.', exec: true, taskName: 'Run date suite', latestSub: 'Test run completed. Results captured.', steps: [['Set up test environment', 'done'], ['Run date suite', 'done'], ['Verify results', 'current'], ['Confirm fix', ''], ['Document outcome', ''], ['Close mission', '']], related: [{ key: 'suite', title: 'Date test suite', sub: 'Test definitions and inputs', glyph: 'doc', verb: 'uses' }, { key: 'results', title: 'Results', sub: 'Test execution outputs', glyph: 'chart', verb: 'produces' }, { key: 'verify', title: 'Verification', sub: 'Confirms behaviour', glyph: 'check', verb: 'verifies', from: 'results' }], log: ['Tool call received.', 'Tool result received.', 'Not passed tests.', 'Parsing results.', 'Recording outcome.', 'Proceeding to verification checks.'] },
    { id: 'm-done', title: 'Docs refresh', project: 'archeus', branch: 'docs/changelog', state: 'done', stateText: 'Done', phase: 6, glyph: 'check', what: 'Summarise the merged changes for the release.', latest: 'Review passed.', task: 'none', exec: false, related: [], log: ['Review passed.'] },
    { id: 'm-index', title: 'Offline capture', project: 'notes', branch: 'feat/index', state: 'idle', stateText: 'Captured', phase: -1, glyph: 'doc', what: 'Capture an offline copy of notes.', latest: 'none recorded', task: 'none', exec: false, related: [], log: ['No activity recorded.'] },
    { id: 'm-read', title: 'Export backup', project: 'notes', branch: 'docs/reading', state: 'idle', stateText: 'New', phase: -1, glyph: 'doc', what: 'Export the reading list as a file.', latest: 'Export completed.', task: 'none', exec: false, related: [], log: ['Export completed.'] },
  ];

  var plans = {
    'm-search': {
      version: 1,
      hash: '5e0a3c9f b1d7 4e21 a86c 90f2d3e7b41a',
      why: 'Plan approval required.',
      tasks: [
        { key: 't1', text: 'Read the recorded sources for the search index.' },
        { key: 't2', text: 'Attach a provenance link to each result.' },
        { key: 't3', text: 'Add a test that every result links to a source.' }
      ],
      approve: 'Approving starts 3 tasks on feat/search.',
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
  var pendingApply = null;
  var sheetOpen = null;
  var lastStar = null;
  var sharedTab = 'overview';
  var missionShown = 'm-date';
  var planStep = 'review';
  var planOpened = false;

  /* ---------- Small helpers ---------- */

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
    return w + ' needs you ·' + (isNarrow() ? '\n' : ' ') + r + ' verifying';
  }
  function selectedComments() { return comments.filter(function (c) { return c.mission === planId && c.carry; }); }
  function commentsFor(id) { return comments.filter(function (c) { return c.mission === id; }); }

  /* ---------- Geometry: polyhedra, projection, glyphs ---------- */

  function dist3(a, b) { return Math.hypot(a[0] - b[0], a[1] - b[1], a[2] - b[2]); }

  // Vertices are normalised; edges are the pairs at the minimum distance.
  function solid(pts) {
    var v = pts.map(function (p) { var l = Math.hypot(p[0], p[1], p[2]); return [p[0] / l, p[1] / l, p[2] / l]; });
    var min = Infinity, i, j, e = [];
    for (i = 0; i < v.length; i++) for (j = i + 1; j < v.length; j++) min = Math.min(min, dist3(v[i], v[j]));
    for (i = 0; i < v.length; i++) for (j = i + 1; j < v.length; j++) if (dist3(v[i], v[j]) < min * 1.01) e.push([i, j]);
    return { v: v, e: e, links: [] };
  }
  var PHI = (1 + Math.sqrt(5)) / 2;
  var ICO = (function () {
    var s = solid([[0, 1, PHI], [0, 1, -PHI], [0, -1, PHI], [0, -1, -PHI], [1, PHI, 0], [1, -PHI, 0], [-1, PHI, 0], [-1, -PHI, 0], [PHI, 0, 1], [PHI, 0, -1], [-PHI, 0, 1], [-PHI, 0, -1]]);
    // Inner mesh: each outer vertex joins its two nearest vertices of a half-size copy.
    s.links = s.v.map(function (p) {
      return s.v.map(function (q, j) { return { j: j, d: dist3(p, [q[0] * 0.5, q[1] * 0.5, q[2] * 0.5]) }; })
        .sort(function (a, b) { return a.d - b.d; }).slice(0, 2).map(function (o) { return o.j; });
    });
    return s;
  })();
  var OCT = solid([[1, 0, 0], [-1, 0, 0], [0, 1, 0], [0, -1, 0], [0, 0, 1], [0, 0, -1]]);
  var TET = solid([[1, 1, 1], [1, -1, -1], [-1, 1, -1], [-1, -1, 1]]);
  var CUBE = solid([[1, 1, 1], [1, 1, -1], [1, -1, 1], [1, -1, -1], [-1, 1, 1], [-1, 1, -1], [-1, -1, 1], [-1, -1, -1]]);

  function spin(p, ry, rx) {
    var cy = Math.cos(ry), sy = Math.sin(ry), cx = Math.cos(rx), sx = Math.sin(rx);
    var x = p[0] * cy + p[2] * sy, z = -p[0] * sy + p[2] * cy;
    var y = p[1] * cx - z * sx;
    z = p[1] * sx + z * cx;
    return [x, y, z];
  }
  function proj(p, cx, cy, R) {
    var f = 4 / (4 - p[2]);
    return { x: cx + p[0] * f * R, y: cy + p[1] * f * R, z: p[2] };
  }
  function convexHull(pts) {
    var P = pts.slice().sort(function (a, b) { return a.x - b.x || a.y - b.y; });
    if (P.length < 3) return P;
    function cross(o, a, b) { return (a.x - o.x) * (b.y - o.y) - (a.y - o.y) * (b.x - o.x); }
    var lo = [], up = [], i;
    P.forEach(function (p) {
      while (lo.length >= 2 && cross(lo[lo.length - 2], lo[lo.length - 1], p) <= 0) lo.pop();
      lo.push(p);
    });
    for (i = P.length - 1; i >= 0; i--) {
      var q = P[i];
      while (up.length >= 2 && cross(up[up.length - 2], up[up.length - 1], q) <= 0) up.pop();
      up.push(q);
    }
    return lo.slice(0, -1).concat(up.slice(0, -1));
  }
  function line(g, x1, y1, x2, y2) { g.beginPath(); g.moveTo(x1, y1); g.lineTo(x2, y2); g.stroke(); }
  function rgba(hex, a) {
    var n = parseInt(hex.slice(1), 16);
    return 'rgba(' + (n >> 16 & 255) + ',' + (n >> 8 & 255) + ',' + (n & 255) + ',' + a.toFixed(3) + ')';
  }

  var GLYPH = {
    doc: function (g) {
      g.beginPath(); g.rect(-0.42, -0.6, 0.84, 1.2); g.stroke();
      line(g, -0.24, -0.28, 0.24, -0.28); line(g, -0.24, 0, 0.24, 0); line(g, -0.24, 0.28, 0.06, 0.28);
    },
    search: function (g) {
      g.beginPath(); g.rect(-0.56, -0.6, 0.7, 0.96); g.stroke();
      g.beginPath(); g.arc(0.22, 0.2, 0.3, 0, TAU); g.stroke();
      line(g, 0.44, 0.42, 0.7, 0.68);
    },
    code: function (g) {
      line(g, -0.22, -0.42, -0.62, 0); line(g, -0.62, 0, -0.22, 0.42);
      line(g, 0.22, -0.42, 0.62, 0); line(g, 0.62, 0, 0.22, 0.42);
      line(g, 0.1, -0.42, -0.1, 0.42);
    },
    term: function (g) {
      g.beginPath(); g.rect(-0.66, -0.46, 1.32, 0.92); g.stroke();
      g.beginPath(); g.moveTo(-0.36, -0.16); g.lineTo(-0.14, 0.02); g.lineTo(-0.36, 0.2); g.stroke();
      line(g, 0, 0.2, 0.3, 0.2);
    },
    chart: function (g) {
      [[-0.46, 0.5], [-0.16, 0.9], [0.14, 0.66]].forEach(function (b) {
        g.beginPath(); g.rect(b[0], 0.42 - b[1], 0.24, b[1]); g.stroke();
      });
    },
    check: function (g) {
      g.beginPath(); g.arc(0, 0, 0.72, 0, TAU); g.stroke();
      g.beginPath(); g.moveTo(-0.34, 0.02); g.lineTo(-0.1, 0.26); g.lineTo(0.36, -0.28); g.stroke();
    },
    list: function (g) {
      [-0.4, 0, 0.4].forEach(function (y) {
        g.beginPath(); g.arc(-0.42, y, 0.08, 0, TAU); g.fill(); line(g, -0.24, y, 0.42, y);
      });
    },
    monitor: function (g) { g.beginPath(); g.rect(-0.6, -0.42, 1.2, 0.78); g.stroke(); line(g, 0, 0.36, 0, 0.56); },
    phone: function (g) { g.beginPath(); g.rect(-0.3, -0.6, 0.6, 1.2); g.stroke(); },
    cluster: function (g) {
      var pts = [[-0.5, -0.4], [0.5, -0.3], [0.45, 0.45], [-0.45, 0.45], [0, 0]];
      pts.forEach(function (p) { line(g, 0, 0, p[0], p[1]); });
      pts.forEach(function (p) { g.beginPath(); g.arc(p[0], p[1], 0.1, 0, TAU); g.fill(); });
    }
  };

  function glyph(g, name, x, y, s, col, a) {
    var f = GLYPH[name];
    if (!f) return;
    g.save();
    g.translate(x, y); g.scale(s, s);
    g.strokeStyle = col; g.fillStyle = col; g.globalAlpha = a;
    g.lineWidth = 1.3 / s; g.lineCap = 'round'; g.lineJoin = 'round';
    f(g);
    g.restore();
  }

  // One 3D style for every body: rotating wireframe, depth-faded edges, optional inner mesh, glyph inside.
  function drawSolid(g, sol, cx, cy, R, rot, col, o) {
    var P = sol.v.map(function (p) { return proj(spin(p, rot.y, rot.x), cx, cy, R); });
    var A = o.alpha == null ? 1 : o.alpha, i;
    g.save();
    g.strokeStyle = col; g.fillStyle = col; g.lineCap = 'round';
    if (o.wash) {
      var hull = convexHull(P);
      if (hull.length > 2) {
        g.globalAlpha = A * 0.07;
        g.beginPath();
        hull.forEach(function (q, k) { if (k) g.lineTo(q.x, q.y); else g.moveTo(q.x, q.y); });
        g.closePath(); g.fill();
      }
    }
    if (o.glow) { g.shadowColor = col; g.shadowBlur = 14; }
    g.setLineDash(o.dash || []);
    g.lineWidth = o.lw || 1.1;
    sol.e.forEach(function (ed) {
      var a = P[ed[0]], b = P[ed[1]];
      g.globalAlpha = A * (0.2 + 0.8 * (((a.z + b.z) / 2) + 1) / 2);
      line(g, a.x, a.y, b.x, b.y);
    });
    if (sol.links.length) {
      var Q = sol.v.map(function (p) { return proj(spin(p, rot.y, rot.x), cx, cy, R * 0.5); });
      g.shadowBlur = 0; g.lineWidth = 0.8;
      sol.e.forEach(function (ed) {
        var a = Q[ed[0]], b = Q[ed[1]];
        g.globalAlpha = A * 0.42 * (0.2 + 0.8 * (((a.z + b.z) / 2) + 1) / 2);
        line(g, a.x, a.y, b.x, b.y);
      });
      sol.links.forEach(function (ns, k) {
        ns.forEach(function (j) {
          var a = P[k], b = Q[j];
          g.globalAlpha = A * 0.3 * (0.2 + 0.8 * (((a.z + b.z) / 2) + 1) / 2);
          line(g, a.x, a.y, b.x, b.y);
        });
      });
      Q.forEach(function (q) {
        g.globalAlpha = A * 0.5 * (0.3 + 0.7 * (q.z + 1) / 2);
        g.beginPath(); g.arc(q.x, q.y, 1.4, 0, TAU); g.fill();
      });
    }
    g.setLineDash([]); g.shadowBlur = 0;
    for (i = 0; i < P.length; i++) {
      g.globalAlpha = A * (0.4 + 0.6 * (P[i].z + 1) / 2);
      if (o.glow) { g.shadowColor = col; g.shadowBlur = 8; }
      g.beginPath(); g.arc(P[i].x, P[i].y, o.dotR || 2.2, 0, TAU); g.fill();
      g.shadowBlur = 0;
    }
    if (o.glyph) glyph(g, o.glyph, cx, cy, R * 0.36, col, A * 0.95);
    g.restore();
  }

  function drawBadge(g, state, x, y, t, anim) {
    var s = 6;
    g.save();
    g.lineWidth = 1.5;
    if (state === 'waiting') {
      g.fillStyle = STATE.waiting.color; g.shadowColor = STATE.waiting.color; g.shadowBlur = 10;
      g.beginPath(); g.moveTo(x, y - s - 2); g.lineTo(x + s, y); g.lineTo(x, y + s + 2); g.lineTo(x - s, y); g.closePath(); g.fill();
    } else if (state === 'running') {
      var k = anim ? (t / 1400) % 1 : 0;
      g.strokeStyle = rgba('#6FB1FF', 0.5 * (1 - k));
      g.beginPath(); g.arc(x, y, 6 + 8 * k, 0, TAU); g.stroke();
      g.fillStyle = STATE.running.color; g.shadowColor = STATE.running.color; g.shadowBlur = 10;
      g.beginPath();
      g.moveTo(x, y - 7); g.quadraticCurveTo(x + 1.2, y - 1.2, x + 7, y); g.quadraticCurveTo(x + 1.2, y + 1.2, x, y + 7);
      g.quadraticCurveTo(x - 1.2, y + 1.2, x - 7, y); g.quadraticCurveTo(x - 1.2, y - 1.2, x, y - 7); g.fill();
    } else if (state === 'done') {
      g.fillStyle = STATE.done.color;
      g.beginPath(); g.arc(x, y, 7, 0, TAU); g.fill();
      g.strokeStyle = INK; g.lineWidth = 1.8;
      g.beginPath(); g.moveTo(x - 3.2, y); g.lineTo(x - 0.8, y + 2.6); g.lineTo(x + 3.4, y - 2.8); g.stroke();
    } else if (state === 'idle') {
      g.strokeStyle = STATE.idle.color;
      g.beginPath(); g.arc(x, y, 5.5, 0, TAU); g.stroke();
    }
    g.restore();
  }

  // Star: many fine threads of two lengths, ivory, crisp. Replaces the six long rays of round 3 to 9.
  // Desktop star (round 10c): a dense knot of fine ivory threads with a bright centre, as in the concept.
  function drawKnot(g, c, s) {
    var seed = 11, rnd = function () { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    var pts = [], i;
    for (i = 0; i < 46; i++) {
      var a = (i + rnd() * 0.6) * TAU / 46, r = (16 + rnd() * 70) * s;
      pts.push({ x: c.x + Math.cos(a) * r, y: c.y + Math.sin(a) * r, a: a });
    }
    g.save(); g.strokeStyle = IVORY; g.fillStyle = IVORY; g.lineCap = 'round';
    pts.forEach(function (p, j) {
      var q = pts[(j + 5) % pts.length];
      g.globalAlpha = j % 3 === 0 ? 0.75 : 0.42; g.lineWidth = j % 3 === 0 ? 0.8 : 0.55;
      line(g, p.x, p.y, q.x, q.y);
    });
    pts.forEach(function (p) {
      g.globalAlpha = 0.45 + 0.45 * rnd(); g.lineWidth = 0.6;
      line(g, c.x + Math.cos(p.a) * 3 * s, c.y + Math.sin(p.a) * 3 * s, p.x, p.y);
      g.globalAlpha = 0.9; g.beginPath(); g.arc(p.x, p.y, 1.1 * s, 0, TAU); g.fill();
    });
    var rg = g.createRadialGradient(c.x, c.y, 0, c.x, c.y, 16 * s);
    rg.addColorStop(0, 'rgba(255,248,230,0.9)'); rg.addColorStop(0.4, 'rgba(239,233,218,0.25)'); rg.addColorStop(1, 'rgba(239,233,218,0)');
    g.globalAlpha = 1; g.fillStyle = rg; g.beginPath(); g.arc(c.x, c.y, 16 * s, 0, TAU); g.fill();
    g.fillStyle = '#FFF8E6'; g.beginPath(); g.arc(c.x, c.y, 2.6 * s, 0, TAU); g.fill();
    g.restore();
  }

  function drawCore(g, c, t, hot, s, knot) {
    if (knot) { drawKnot(g, c, s); return; }
    g.save();
    g.strokeStyle = IVORY; g.fillStyle = IVORY; g.lineCap = 'round';
    for (var i = 0; i < 88; i++) {
      var a = i * TAU / 88 + (i % 4) * 0.011;
      var L = (i % 6 === 0 ? 92 : 34 + ((i * 37) % 47)) * s;
      g.globalAlpha = i % 6 === 0 ? 0.85 : 0.42;
      g.lineWidth = i % 6 === 0 ? 0.8 : 0.5;
      line(g, c.x + Math.cos(a) * 2 * s, c.y + Math.sin(a) * 2 * s, c.x + Math.cos(a) * L, c.y + Math.sin(a) * L);
    }
    g.globalAlpha = 0.55; g.lineWidth = 0.6;
    line(g, c.x, c.y - 130 * s, c.x, c.y + 130 * s);
    g.globalAlpha = 0.28;
    var rg = g.createRadialGradient(c.x, c.y, 0, c.x, c.y, 16 * s);
    rg.addColorStop(0, 'rgba(239,233,218,0.9)'); rg.addColorStop(1, 'rgba(239,233,218,0)');
    g.fillStyle = rg; g.beginPath(); g.arc(c.x, c.y, 16 * s, 0, TAU); g.fill();
    g.globalAlpha = 1;
    g.beginPath(); g.arc(c.x, c.y, 2.4 * s, 0, TAU); g.fill();
    g.restore();
  }

  // Mission marks: small glyphs. Amber diamond = owner obligation, blue star = live, grey = done or idle.
  function drawMark(g, x, y, state, r, lit) {
    g.save();
    g.lineWidth = 1.3; g.lineJoin = 'round';
    var col = STATE[state] ? STATE[state].color : IVORY;
    if (state === 'running') {
      g.fillStyle = col;
      g.beginPath();
      g.moveTo(x, y - r * 1.3); g.quadraticCurveTo(x + r * 0.16, y - r * 0.16, x + r * 1.1, y);
      g.quadraticCurveTo(x + r * 0.16, y + r * 0.16, x, y + r * 1.3);
      g.quadraticCurveTo(x - r * 0.16, y + r * 0.16, x - r * 1.1, y);
      g.quadraticCurveTo(x - r * 0.16, y - r * 0.16, x, y - r * 1.3);
      g.fill();
    } else if (state === 'waiting') {
      g.strokeStyle = col; g.fillStyle = 'rgba(242,181,68,0.22)';
      g.beginPath(); g.moveTo(x, y - r); g.lineTo(x + r * 0.8, y); g.lineTo(x, y + r); g.lineTo(x - r * 0.8, y); g.closePath();
      g.fill(); g.stroke();
    } else {
      g.strokeStyle = STATE.idle.color;
      g.beginPath(); g.moveTo(x, y - r * 0.8); g.lineTo(x + r * 0.64, y); g.lineTo(x, y + r * 0.8); g.lineTo(x - r * 0.64, y); g.closePath();
      g.stroke();
    }
    g.restore();
  }

  // Codex execution: a plain triangle with the code glyph inside.
  // Shared view: agents are triangles (wash, outline, inner triangle); devices are boxes with a glyph.
  function drawShape(g, n, q, gn) {
    var col = STATE[n.state] ? STATE[n.state].color : IVORY;
    g.save(); g.globalAlpha = gn; g.lineJoin = 'round';
    if (n.tri) {
      var R = n.r;
      g.beginPath(); g.moveTo(q.x, q.y - R); g.lineTo(q.x + R * 0.95, q.y + R * 0.7); g.lineTo(q.x - R * 0.95, q.y + R * 0.7); g.closePath();
      g.fillStyle = rgba(col, 0.14); g.fill();
      g.strokeStyle = col; g.lineWidth = 2; g.stroke();
      var r2 = R * 0.38;
      g.beginPath(); g.moveTo(q.x, q.y - r2 * 0.5); g.lineTo(q.x + r2, q.y + r2 * 0.6); g.lineTo(q.x - r2, q.y + r2 * 0.6); g.closePath();
      g.fillStyle = col; g.fill();
    } else {
      var w = n.bw, h = n.bh;
      g.beginPath();
      if (g.roundRect) g.roundRect(q.x - w / 2, q.y - h / 2, w, h, 10); else g.rect(q.x - w / 2, q.y - h / 2, w, h);
      g.fillStyle = 'rgba(14,19,28,0.92)'; g.fill();
      g.setLineDash(n.dash ? [4, 4] : []);
      g.strokeStyle = 'rgba(239,233,218,' + (n.dash ? 0.45 : 0.6) + ')'; g.lineWidth = 1.2; g.stroke();
      g.setLineDash([]);
      glyph(g, n.glyph, q.x, q.y, Math.min(w, h) * 0.4, IVORY, 0.9);
    }
    g.restore();
  }

  function drawTriangle(g, x, y, r, lit) {
    g.save();
    g.strokeStyle = IVORY; g.lineWidth = 1.1; g.globalAlpha = lit ? 0.9 : 0.6;
    g.beginPath(); g.moveTo(x, y - r); g.lineTo(x + r * 0.9, y + r * 0.62); g.lineTo(x - r * 0.9, y + r * 0.62); g.closePath(); g.stroke();
    glyph(g, 'code', x, y + r * 0.1, r * 0.42, IVORY, 0.85);
    g.restore();
  }

  // Desktop marks (round 10c): filled diamonds (waiting amber, done lilac), a sparkle for a new item, a blue
  // four-point star for live work.
  function drawDeskMark(g, x, y, n, r, lit) {
    g.save();
    var amber = n.state === 'waiting', blue = n.state === 'running', spark = n.detail === 'New';
    var col = amber || spark ? STATE.waiting.color : blue ? STATE.running.color : '#B9B3D1';
    g.fillStyle = col; g.shadowColor = col; g.shadowBlur = amber || blue || spark ? 12 : 0; g.globalAlpha = lit || amber || blue ? 1 : 0.85;
    g.beginPath();
    if (blue || spark) {
      var R = r * (blue ? 1.9 : 1.6), q = R * 0.2;
      g.moveTo(x, y - R); g.quadraticCurveTo(x + q, y - q, x + R, y); g.quadraticCurveTo(x + q, y + q, x, y + R);
      g.quadraticCurveTo(x - q, y + q, x - R, y); g.quadraticCurveTo(x - q, y - q, x, y - R);
    } else {
      var D = r * 1.3;
      g.moveTo(x, y - D); g.lineTo(x + D * 0.72, y); g.lineTo(x, y + D); g.lineTo(x - D * 0.72, y); g.closePath();
    }
    g.fill();
    g.restore();
  }

  // Desktop Codex execution: a blue triangle whose apex is the execution node and whose base corners are the
  // Verification and Results dots, with the code glyph inside.
  function drawDeskExec(g, a, b1, b2, lit) {
    g.save();
    g.strokeStyle = STATE.running.color; g.lineWidth = 1.2; g.globalAlpha = lit ? 0.85 : 0.5; g.lineJoin = 'round';
    var yb = b1.y - 13, l = { x: b1.x + 14, y: yb }, r = { x: b2.x - 14, y: yb };
    g.beginPath(); g.moveTo(a.x, a.y); g.lineTo(l.x, l.y); g.lineTo(r.x, r.y); g.closePath(); g.stroke();
    g.beginPath(); g.moveTo(l.x, l.y); g.lineTo(b1.x, b1.y); g.moveTo(r.x, r.y); g.lineTo(b2.x, b2.y); g.stroke();
    g.fillStyle = STATE.running.color; g.shadowColor = STATE.running.color; g.shadowBlur = 10; g.globalAlpha = 1;
    g.beginPath(); g.arc(a.x, a.y, 4.6, 0, TAU); g.fill();
    g.shadowBlur = 0;
    glyph(g, 'code', a.x, a.y + (b1.y - a.y) * 0.62, 9, IVORY, 0.95);
    g.restore();
  }

  /* ---------- Scenes: plain data, no drawing ---------- */

  function mk(w, h, core, k, narrow) {
    return {
      view: { x: 0, y: 0, w: w, h: h },
      core: core, k: k, compact: narrow,
      labelDirs: narrow ? ['column', 'column-reverse'] : null,
      projects: [], nodes: [], links: [], verbs: [], parent: {}, frame: null
    };
  }

  function nodeFor(m, x, y, r, parent, hit, extra) {
    var o = {
      id: m.id, kind: 'mission', state: m.state, x: x, y: y, r: r, glyph: m.glyph || 'doc',
      live: isLive(m), title: m.title, kicker: 'Mission', sub: m.branch, st: STATE[m.state].word,
      detail: m.stateText, parent: parent, hit: hit, solid: ICO, seed: (x * 0.013 + y * 0.007) % 1
    };
    Object.keys(extra || {}).forEach(function (k) { o[k] = extra[k]; });
    return o;
  }

  function execFor(m, x, y, r, k) {
    return {
      id: m.id + '-exec', kind: 'exec', state: 'exec', x: x, y: y, r: r, glyph: 'code', live: m.state === 'running',
      title: 'Codex', kicker: 'Execution', sub: m.state === 'running' ? 'Checks running' : 'Ready', st: '', parent: m.id,
      hit: false, solid: TET, seed: 0.3 + k * 0.1
    };
  }

  // The bottom CHAT_RESERVE pixels of the stage belong to the conversation, so the scene is laid out above them.
  var CHAT_RESERVE = 170;
  // Measured from the Codex concept images (desktop-1-now-v2.png 1296 x 729; phone-1-now-v2.png 804 x 1373).
  // Coordinates are in the reference pixels of each image, read from a labelled grid overlay. The Overview maps
  // the desktop box (x 150..1290, y 60..530) and the phone box (x 0..804, y 280..1110) onto the stage.
  var CONCEPT_LAYOUT = {
    desktop: {
      box: { x0: 150, x1: 1290, y0: 60, y1: 530, w: 1296, h: 729 },
      fill: 0.82,
      core: [640, 316],
      hulls: {
        archeus: [[197, 340], [265, 232], [480, 182], [657, 140], [918, 220], [1035, 390], [930, 512], [640, 458], [425, 478], [282, 445]],
        notes: [[935, 147], [1055, 85], [1128, 116], [1184, 185], [1165, 268], [1112, 305], [978, 298], [964, 236]],
        ideas: [[1101, 410], [1131, 369], [1207, 380], [1182, 440], [1131, 453]]
      },
      marks: {
        'm-search': [330, 298], 'm-done': [368, 408], 'm-date': [826, 344], 'm-index': [1034, 175], 'm-read': [1040, 230],
        exec: [871, 416], verif: [806, 488], results: [925, 488]
      }
    },
    phone: {
      box: { x0: 0, x1: 804, y0: 280, y1: 1110, w: 804, h: 1373 },
      fill: 0.94,
      core: [431, 697],
      hulls: {
        archeus: [[43, 683], [142, 545], [318, 450], [432, 458], [598, 595], [713, 665], [765, 763], [732, 832], [645, 884], [540, 997], [432, 962], [376, 1030], [270, 975], [97, 873]],
        amber: [[180, 606], [307, 634], [352, 738], [318, 845], [225, 891], [126, 836], [92, 715]],
        blue: [[635, 635], [714, 665], [765, 763], [732, 832], [645, 884], [552, 828], [532, 728]],
        notes: [[562, 398], [634, 340], [728, 368], [750, 447], [680, 518], [574, 476]],
        ideas: [[600, 970], [684, 935], [748, 988], [730, 1053], [636, 1080], [588, 1032]]
      },
      marks: {
        'm-search': [217, 700], 'm-date': [648, 737], exec: [648, 806]
      }
    }
  };
  // Map a reference point into the stage box (w x hh), aspect-preserving and centred inside the box.
  function layoutMap(layout, px, py, w, hh, scale) {
    var b = layout.box, s = scale || 1;
    var sx = (w * (layout.fill || 0.82)) / (b.x1 - b.x0), sy = hh / (b.y1 - b.y0);
    var k = Math.min(sx, sy) * s;
    var ox = (w - (b.x1 - b.x0) * k) / 2, oy = (hh - (b.y1 - b.y0) * k) / 2;
    return { x: ox + (px - b.x0) * k, y: oy + (py - b.y0) * k, k: k };
  }
  function layoutHull(layout, pts, w, hh, scale) {
    return pts.map(function (p) { var q = layoutMap(layout, p[0], p[1], w, hh, scale); return { x: q.x, y: q.y }; });
  }
  function layoutMark(layout, key, w, hh, scale) {
    var p = layout.marks[key];
    return layoutMap(layout, p[0], p[1], w, hh, scale);
  }
  function markNode(m, x, y, r, parent) {
    var n = nodeFor(m, x, y, r, parent, true);
    n.mark = true;
    return n;
  }
  // Desktop Overview (round 10c): the concept's constellation box (DESK_BOX, reference px) fills DESK_FILL of the
  // stage width, scaled uniformly and centred. The scene takes DESK_SCENE_H of the stage height at most.
  // Round 10d: the desktop Overview is a fixed 1296 x 729 frame (the concept's own size). Reference px are frame px.
  var DESK_W = 1296, DESK_H = 729;
  function nowScene(w, h) {
    var L = CONCEPT_LAYOUT.desktop;
    var k0 = Math.min(w / DESK_W, h / DESK_H);
    var ox = (w - DESK_W * k0) / 2, oy = (h - DESK_H * k0) / 2;
    var dm = function (p) { return { x: ox + p[0] * k0, y: oy + p[1] * k0 }; };
    var hullOf = function (pts) { return pts.map(dm); };
    var k = k0;
    var sc = mk(w, h, { x: 0, y: 0 }, k, false);
    var c0 = dm(L.core);
    sc.core = { x: c0.x, y: c0.y };
    sc.knot = true; sc.desk = true;
    sc.sats = [];
    var archeus = projectOf('archeus'), notes = projectOf('notes'), ideas = projectOf('ideas');
    sc.projects.push({ id: 'archeus', name: archeus.name, hue: IVORY, note: archeus.note, ring: hullOf(L.hulls.archeus), members: ['m-search', 'm-date', 'm-done'], count: 3, live: 2, active: true, desk: true });
    sc.projects.push({ id: 'notes', name: notes.name, hue: IVORY, note: notes.note, ring: hullOf(L.hulls.notes), members: ['m-index', 'm-read'], count: 2, live: 0, active: false, desk: true });
    sc.projects.push({ id: 'ideas', name: ideas.name, hue: IVORY, note: ideas.note, ring: hullOf(L.hulls.ideas), members: [], count: 0, live: 0, active: false, desk: true });
    var fixAt = function (x, y, d, v) { return { d: d, v: v, at: dm([x, y]) }; };
    sc.labelFix = {
      archeus: { hide: true },
      notes: fixAt(1172, 112, 'row', 'c'),
      ideas: fixAt(1208, 427, 'row', 'c'),
      'm-search': { d: 'row', v: 'c' }, 'm-date': { d: 'row', v: 'c' }, 'm-done': { d: 'row', v: 'c' },
      'm-index': { d: 'row', v: 'c' }, 'm-read': { d: 'row', v: 'd' },
      'm-date-exec': { d: 'row', v: 'd' }, verif: fixAt(820, 489, 'row', 'c'), results: fixAt(939, 489, 'row', 'c')
    };
    sc.parent.archeus = 'core'; sc.parent.notes = 'core'; sc.parent.ideas = 'core';
    sc.links.push({ a: 'core', b: 'archeus', col: IVORY, live: true, kind: 'project', hue: IVORY });
    sc.links.push({ a: 'core', b: 'notes', col: IVORY, live: false, kind: 'project', hue: IVORY });
    sc.links.push({ a: 'core', b: 'ideas', col: IVORY, live: false, kind: 'project', hue: IVORY, dash: true });
    var mSearch = find('m-search'), mDate = find('m-date'), mDone = find('m-done');
    var at = function (key) { return dm(L.marks[key]); };
    var nS = markNode(mSearch, at('m-search').x, at('m-search').y, 7 * k, 'archeus');
    var nD = markNode(mDate, at('m-date').x, at('m-date').y, 8 * k, 'archeus');
    var nDone = markNode(mDone, at('m-done').x, at('m-done').y, 6 * k, 'archeus');
    sc.nodes.push(nS, nD, nDone);
    sc.parent[mSearch.id] = 'archeus'; sc.parent[mDate.id] = 'archeus'; sc.parent[mDone.id] = 'archeus';
    sc.links.push({ a: 'core', b: mSearch.id, col: STATE.waiting.color, live: true, kind: 'mission', hue: IVORY, arrow: true });
    sc.links.push({ a: 'core', b: mDate.id, col: STATE.running.color, live: true, kind: 'mission', hue: IVORY, arrow: true });
    sc.links.push({ a: 'core', b: mDone.id, col: IVORY, live: false, kind: 'mission', hue: IVORY });
    var ex = execFor(mDate, at('exec').x, at('exec').y, 15 * k, 0); ex.mark = true;
    var nv = { id: 'verif', kind: 'record', state: 'idle', x: at('verif').x, y: at('verif').y, r: 9 * k, glyph: 'check', live: true, title: 'Verification', kicker: 'Record', sub: 'Confirms behaviour', st: '', parent: mDate.id, hit: false, solid: OCT, seed: 0.5, mark: true, dot: true };
    var nr = { id: 'results', kind: 'record', state: 'idle', x: at('results').x, y: at('results').y, r: 9 * k, glyph: 'chart', live: true, title: 'Results', kicker: 'Record', sub: 'Test execution outputs', st: '', parent: mDate.id, hit: false, solid: OCT, seed: 0.7, mark: true, dot: true };
    sc.nodes.push(ex, nv, nr);
    sc.parent[ex.id] = mDate.id; sc.parent[nv.id] = mDate.id; sc.parent[nr.id] = mDate.id;
    sc.links.push({ a: mDate.id, b: ex.id, col: '#6FB1FF', live: true, kind: 'exec', hue: IVORY, arrow: true });
    sc.links.push({ a: ex.id, b: nv.id, col: '#6FB1FF', live: true, kind: 'exec', hue: IVORY, arrow: true });
    sc.links.push({ a: ex.id, b: nr.id, col: '#6FB1FF', live: true, kind: 'exec', hue: IVORY, arrow: true });
    var mIdx = find('m-index'), mRead = find('m-read');
    var nO = markNode(mIdx, at('m-index').x, at('m-index').y, 6 * k, 'notes'), nE = markNode(mRead, at('m-read').x, at('m-read').y, 6 * k, 'notes');
    sc.nodes.push(nO, nE);
    sc.parent[mIdx.id] = 'notes'; sc.parent[mRead.id] = 'notes';
    sc.links.push({ a: 'core', b: mIdx.id, col: IVORY, live: false, kind: 'mission', hue: IVORY });
    sc.links.push({ a: 'core', b: mRead.id, col: IVORY, live: false, kind: 'mission', hue: IVORY });
    return sc;
  }

  function missionScene(m, w, h, small) {
    var p = projectOf(m.project);
    var k = Math.max(0.7, Math.min(w / 720, 1.1));
    var sc = mk(w, h, { x: w * 0.5, y: h * 0.12 }, k, false);
    var live = isLive(m);
    sc.projects.push({ id: p.id, name: p.name, hue: p.hue, x: w * 0.2, y: h * 0.4, shape: 'octa', members: small ? [m.id] : null, count: missions.filter(function (x) { return x.project === p.id; }).length, live: live ? 1 : 0, active: live });
    sc.parent[p.id] = 'core';
    sc.links.push({ a: 'core', b: p.id, col: p.hue, live: live, kind: 'project', hue: p.hue, verb: 'orchestrates' });
    var mx = w * 0.56, my = h * 0.5;
    sc.nodes.push(nodeFor(m, mx, my, (small ? 50 : 112) * k, p.id, false));
    sc.parent[m.id] = p.id;
    sc.links.push({ a: p.id, b: m.id, col: isLive(m) ? STATE[m.state].color : p.hue, live: live, kind: 'mission', hue: p.hue, verb: 'contains' });
    if (m.exec) {
      var ex = execFor(m, w * 0.24, h * 0.84, 34 * k, 0);
      sc.nodes.push(ex);
      sc.parent[ex.id] = m.id;
      sc.links.push({ a: m.id, b: ex.id, col: IVORY, live: ex.live, kind: 'exec', hue: IVORY, verb: 'executes' });
    }
    var slots = [[0.86, 0.2], [0.84, 0.66], [0.56, 0.93]];
    m.related.forEach(function (r, i) {
      var id = m.id + '-' + r.key, pos = slots[i] || [0.9, 0.9];
      var from = r.from ? m.id + '-' + r.from : m.id;
      sc.nodes.push({ id: id, kind: 'record', state: 'idle', x: w * pos[0], y: h * pos[1], r: 34 * k, glyph: r.glyph, live: false, title: r.title, kicker: 'Record', sub: r.sub, st: '', parent: from, hit: false, solid: OCT, seed: 0.5 + i * 0.17 });
      sc.parent[id] = from;
      sc.links.push({ a: from, b: id, col: 'rgba(239,233,218,0.5)', live: false, kind: 'record', hue: IVORY, verb: r.verb });
    });
    return sc;
  }

  // Phone composition from the measured table: the Archeus outline, the amber Search provenance hull inside it
  // (its Review action inside the hull), the blue Fix date test hull with the Codex triangle, the star between,
  // and two receded named hulls. Sub-hulls are unnamed outlines; the missions carry the labels.
  function phoneScene(w, h) {
    var L = CONCEPT_LAYOUT.phone;
    var k = Math.max(0.78, Math.min(w / 390, 1.05));
    var sc = mk(w, h, { x: w * 0.5, y: h * 0.42 }, k, true);
    var search = find('m-search'), date = find('m-date');
    var c = layoutMap(L, L.core[0], L.core[1], w, h);
    sc.core = { x: c.x, y: c.y };
    var at = function (key) { return layoutMark(L, key, w, h); };
    var archeus = projectOf('archeus');
    sc.projects.push({ id: 'archeus', name: archeus.name, hue: IVORY, note: archeus.note, ring: layoutHull(L, L.hulls.archeus, w, h), members: ['m-search', 'm-date'], count: 3, live: 2, active: true });
    sc.parent.archeus = 'core';
    sc.links.push({ a: 'core', b: 'archeus', col: IVORY, live: true, kind: 'project', hue: IVORY });
    sc.projects.push({ id: 'sub-search', sub: true, ring: layoutHull(L, L.hulls.amber, w, h), members: [], hue: IVORY });
    sc.projects.push({ id: 'sub-date', sub: true, ring: layoutHull(L, L.hulls.blue, w, h), members: [], hue: IVORY });
    var nS = markNode(search, at('m-search').x, at('m-search').y, 7 * k, 'sub-search');
    var nD = markNode(date, at('m-date').x, at('m-date').y, 7 * k, 'sub-date');
    sc.nodes.push(nS, nD);
    sc.parent[search.id] = 'sub-search'; sc.parent[date.id] = 'sub-date';
    sc.parent['sub-search'] = 'archeus'; sc.parent['sub-date'] = 'archeus';
    sc.links.push({ a: 'core', b: search.id, col: STATE.waiting.color, live: true, kind: 'mission', hue: IVORY, arrow: true });
    sc.links.push({ a: 'core', b: date.id, col: STATE.running.color, live: true, kind: 'mission', hue: IVORY, arrow: true });
    var ex = execFor(date, at('exec').x, at('exec').y, 13 * k, 0); ex.mark = true;
    sc.nodes.push(ex);
    sc.parent[ex.id] = date.id;
    sc.links.push({ a: date.id, b: ex.id, col: '#6FB1FF', live: true, kind: 'exec', hue: IVORY, arrow: true });
    sc.projects.push({ id: 'notes', name: projectOf('notes').name, hue: IVORY, note: '', ring: layoutHull(L, L.hulls.notes, w, h), members: [], count: 2, live: 0, active: false });
    sc.projects.push({ id: 'ideas', name: projectOf('ideas').name, hue: IVORY, note: '', ring: layoutHull(L, L.hulls.ideas, w, h), members: [], count: 0, live: 0, active: false });
    sc.parent.notes = 'core'; sc.parent.ideas = 'core';
    sc.links.push({ a: 'core', b: 'notes', col: IVORY, live: false, kind: 'project', hue: IVORY });
    sc.links.push({ a: 'core', b: 'ideas', col: IVORY, live: false, kind: 'project', hue: IVORY, dash: true });
    sc.sats = [];
    sc.overflow = missions.length - 2;
    return sc;
  }

  /* Phone Overview (under 640 px). The picture is the concept raster in clients/v2-prototype/art, made by
     tools/trace_concept.py with every live element removed. The live layer sits on the concept's measured anchors
     (window.ARCHEUS_LAYOUT) and fonts (window.ARCHEUS_TYPE, from tools/fit_type.py). Marks, labels, the Review button,
     the chip and the headline take their words and colours from the data model. Units: the concept's 804 x 1373 px. */
  var OV_HIT = {
    archeus: [[30, 440], [330, 430], [620, 560], [780, 650], [780, 900], [660, 1010], [520, 1040], [300, 1040], [60, 900], [20, 700]]
  };
  var OV_IV = '#F6EEE3', OV_AM = '#F9C259', OV_BL = '#68B9FC', OV_FILL = '#FDBD4D';
  var OV_NAMES = [
    { text: 'Archeus', x: 88, y: 486, centre: true },
    { text: 'Notes', x: 650, y: 326, centre: true },
    { text: 'Ideas', x: 684, y: 1118, centre: true }
  ];
  function ovBox(b) { return { x: b[0], y: b[1], w: b[2] - b[0], h: b[3] - b[1], cx: (b[0] + b[2]) / 2, cy: (b[1] + b[3]) / 2 }; }
  function ovPts(poly) { return poly.map(function (p) { return p[0] + ',' + p[1]; }).join(' '); }
  // One <text> per word when the concept's word positions are known (tools/fit_type.py), so each word sits on the
  // concept's ink; a sentence with a different number of words falls back to one line at the text's origin.
  function frameText(T, key, cls, text, centre) {
    var t = T[key], attrs = ' font-size="' + t.size + '" font-weight="' + t.weight + '" letter-spacing="' + t.ls + '"';
    if (centre === undefined && t.words) {
      var parts = text.split(' ');
      if (parts.length === t.words.length) {
        return parts.map(function (w, i) {
          return '<text class="' + cls + '" x="' + t.words[i][1] + '" y="' + t.y + '"' + attrs + '>' + esc(w) + '</text>';
        }).join('');
      }
    }
    var x = centre === undefined ? t.x : centre;
    return '<text class="' + cls + '" x="' + x + '" y="' + t.y + '"' + attrs + (centre === undefined ? '' : ' text-anchor="middle"') + '>' + esc(text) + '</text>';
  }
  function ovText(key, cls, text, centre) { return frameText(window.ARCHEUS_TYPE, key, cls, text, centre); }
  function ovStar(b, fill) {
    var cx = b.cx, cy = b.cy, r = b.w / 2, k = r * 0.1;
    return '<path d="M' + cx + ',' + (cy - r) + ' Q' + (cx + k) + ',' + (cy - k) + ' ' + (cx + r) + ',' + cy + ' Q' + (cx + k) + ',' + (cy + k) + ' ' + cx + ',' + (cy + r) +
      ' Q' + (cx - k) + ',' + (cy + k) + ' ' + (cx - r) + ',' + cy + ' Q' + (cx - k) + ',' + (cy - k) + ' ' + cx + ',' + (cy - r) + 'Z" fill="' + fill + '"/>';
  }
  function ovDiamond(b, stroke, w) {
    var i = w / 2;
    return '<polygon points="' + ovPts([[b.cx, b.y + i], [b.x + b.w - i, b.cy], [b.cx, b.y + b.h - i], [b.x + i, b.cy]]) + '" fill="none" stroke="' + stroke + '" stroke-width="' + w + '" stroke-linejoin="miter"/>';
  }
  function ovTriangle(b, fill) {
    return '<polygon points="' + ovPts([[b.x, b.y + b.h], [b.x + b.w, b.y + b.h], [b.cx, b.y]]) + '" fill="' + fill + '"/>';
  }

  // The header: wordmark, concept fixture, status line and the headline, anchored to the top of the screen.
  function headSvgFor(L, T) {
    var out = '<g class="ov-head-group" aria-hidden="true">';
    out += frameText(T, 'wordmark', 'ov-serif ov-wordmark', 'ARCHEUS');
    out += frameText(T, 'fixture', 'ov-sans ov-fixture', 'CONCEPT FIXTURE');
    var d = ovBox(L.text.status_dot.box);
    out += '<circle cx="' + d.cx + '" cy="' + d.cy + '" r="' + (d.w / 2) + '" fill="#49E973"/>';
    out += frameText(T, 'status_text', 'ov-sans ov-status', 'Not stopped · accepts new work');
    var lines = sentence().split('\n');
    out += frameText(T, 'headline_1', 'ov-serif ov-headline', lines[0]);
    if (lines[1]) out += frameText(T, 'headline_2', 'ov-serif ov-headline', lines[1]);
    out += '</g>';
    return out;
  }
  function headSvg() { return headSvgFor(window.ARCHEUS_LAYOUT, window.ARCHEUS_TYPE); }

  // The frame: the live marks, labels, the Review button, the chip, and the invisible hit areas.
  // Soft glows (round 10f): the blur and strength are the concept's, measured by tools/fit_glow.py; the art has the
  // same glow subtracted (tools/build_phone_art.py), so each glow is drawn once, here.
  var OV_GLOW_AMBER = '#F6BC4E', OV_GLOW_BLUE = '#6FB1FF';
  function ovGlowDefs() {
    return '<defs>' +
      '<filter id="ov-glow-amber" x="-80%" y="-80%" width="260%" height="260%" color-interpolation-filters="sRGB">' +
      '<feGaussianBlur stdDeviation="6"/><feComponentTransfer><feFuncA type="linear" slope="0.161"/></feComponentTransfer></filter>' +
      '<filter id="ov-glow-blue" x="-80%" y="-80%" width="260%" height="260%" color-interpolation-filters="sRGB">' +
      '<feGaussianBlur stdDeviation="4"/><feComponentTransfer><feFuncA type="linear" slope="0.196"/></feComponentTransfer></filter>' +
      '</defs>';
  }
  function overviewSvg() {
    var L = window.ARCHEUS_LAYOUT, out = ovGlowDefs();
    var amber = find('m-search'), blue = find('m-date');
    var ac = OV_FILL, bc = OV_BL;
    out += '<g class="ov-hit" data-act="open-list" role="button" tabindex="0" aria-label="Archeus: open the project list">' +
      '<polygon points="' + ovPts(OV_HIT.archeus) + '" fill="transparent"/></g>';

    // Mission marks and labels: amber for the owner's obligation, blue for live work.
    var dm = ovBox(L.marks.diamond), sm = ovBox(L.marks.blue_star), tr = ovBox(L.marks.codex_tri);
    out += '<polygon class="ov-glow" points="' + ovPts([[217, 680], [238, 699.5], [217, 719], [196, 699.5]]) + '" fill="' + OV_GLOW_AMBER + '" filter="url(#ov-glow-amber)"/>';
    out += ovDiamond(dm, OV_AM, 6);
    out += ovText('label_search', 'ov-serif ov-title', amber.title);
    out += ovText('label_review_plan', 'ov-sans ov-sub', amber.stateText);
    out += '<a class="ov-review" href="#/plan/m-search" aria-label="Review plan: ' + esc(amber.title) + '">' +
      '<rect class="ov-review-hit" x="' + (L.shapes.review[0] - 14) + '" y="' + (L.shapes.review[1] + (L.shapes.review[3] - L.shapes.review[1]) / 2 - 44) + '" width="' + (L.shapes.review[2] - L.shapes.review[0] + 28) + '" height="88" fill="transparent"/>' +
      '<rect x="' + L.shapes.review[0] + '" y="' + L.shapes.review[1] + '" width="' + (L.shapes.review[2] - L.shapes.review[0]) + '" height="' + (L.shapes.review[3] - L.shapes.review[1]) + '" rx="9" fill="' + ac + '"/>' +
      ovText('review_label', 'ov-sans ov-btn', 'Review', (L.shapes.review[0] + L.shapes.review[2]) / 2) + '</a>';
    out += '<g class="ov-mark" data-open="m-search" role="button" tabindex="0" aria-label="' + esc(amber.title) + '">' +
      '<circle cx="' + dm.cx + '" cy="' + dm.cy + '" r="' + 44 + '" fill="transparent"/></g>';

    out += '<g class="ov-glow" filter="url(#ov-glow-blue)">' + ovStar(sm, OV_GLOW_BLUE) + '</g>';
    out += ovStar(sm, bc);
    out += ovText('label_fix', 'ov-serif ov-title', blue.title);
    out += ovTriangle(tr, bc);
    out += ovText('label_codex', 'ov-sans ov-codex', blue.execText || 'Codex');
    out += '<g class="ov-mark" data-open="m-date" role="button" tabindex="0" aria-label="' + esc(blue.title) + '">' +
      '<circle cx="' + sm.cx + '" cy="' + sm.cy + '" r="44" fill="transparent"/></g>';

    ['m-index', 'm-read'].forEach(function (id) {
      var mm = find(id), b = ovBox(L.marks[id === 'm-index' ? 'notes_index' : 'notes_read']);
      out += '<g class="ov-mark" data-open="' + id + '" role="button" tabindex="0" aria-label="' + esc(mm.title) + '">' +
        '<circle cx="' + b.cx + '" cy="' + b.cy + '" r="44" fill="transparent"/>' +
        (id === 'm-index' ? ovDiamond(b, OV_IV, 3) : ovStar(b, OV_IV)) + '</g>';
    });

    // Project names: small grey labels beside their hulls, on empty concept space (no line within 14 units).
    out += OV_NAMES.map(function (n) {
      return '<text class="ov-sans ov-name" x="' + n.x + '" y="' + n.y + '" font-size="24"' + (n.centre ? ' text-anchor="middle"' : '') + '>' + esc(n.text) + '</text>';
    }).join('');

    var c = L.shapes.chip, cw = c[2] - c[0], cx0 = c[0];
    out += '<g class="ov-chip" data-act="open-list" role="button" tabindex="0" aria-label="' + (projects.length - 1) + ' more projects: open the list">' +
      '<rect x="' + cx0 + '" y="' + (c[1] + (c[3] - c[1]) / 2 - 44) + '" width="' + cw + '" height="88" fill="transparent"/>' +
      '<rect class="ov-pill" x="' + cx0 + '" y="' + c[1] + '" width="' + cw + '" height="' + (c[3] - c[1]) + '" rx="' + ((c[3] - c[1]) / 2) + '" fill="rgba(20,16,26,0.7)" stroke="rgba(239,233,218,0.35)" stroke-width="2"/>' +
      ovText('chip_text', 'ov-sans ov-chip-text', (projects.length - 1) + ' more projects', cx0 + cw / 2) + '</g>';
    return out;
  }

  // Sizes of the live controls come from the layout, so the art and the controls stay on the same units.
  function placeControls(frame) {
    var three = frame === 3, L = three ? window.PH3_LAYOUT : window.ARCHEUS_LAYOUT, T = three ? window.PH3_TYPE : window.ARCHEUS_TYPE;
    var bar = $('#chat-form'), stop = $('#s-now .stop-btn.chat-stop'), input = $('#chat-input');
    if (!bar || !stop || !input || !L || !ovMode()) return;
    var b = L.shapes.bar, s = L.shapes.stop, root = $('#s-now');
    if (!three) {
      root.style.setProperty('--pad', L.pad);
      $('#ov-art').setAttribute('viewBox', '0 ' + -L.pad + ' 804 ' + (1373 + 2 * L.pad));
      root.style.setProperty('--edge-top', 'rgb(' + L.edge.top.join(',') + ')');
      root.style.setProperty('--edge-bottom', 'rgb(' + L.edge.bottom.join(',') + ')');
    }
    bar.style.left = 'calc(var(--u) * ' + b[0] + ')';
    bar.style.width = 'calc(var(--u) * ' + (b[2] - b[0]) + ')';
    bar.style.height = 'calc(var(--u) * ' + (b[3] - b[1]) + ')';
    stop.style.left = 'calc(var(--u) * ' + (s[0] - b[0]) + ')';
    stop.style.width = 'calc(var(--u) * ' + (s[2] - s[0]) + ')';
    input.style.fontSize = 'calc(var(--u) * ' + T.bar_text.size + ')';
    stop.style.fontSize = 'calc(var(--u) * ' + T.stop_text.size + ')';
  }

  function buildOverview() {
    var svg = $('#ov-art'), head = $('#ov-head');
    if (!svg || !head || !window.ARCHEUS_LAYOUT || !window.ARCHEUS_TYPE) return;
    svg.innerHTML = overviewSvg();
    head.innerHTML = headSvg();
    placeControls(1);
  }

  function ovMode() { return window.matchMedia('(max-width: 639px)').matches; }

  /* ---------- Round 10f: the two phone sheets. Each frame is its concept raster with the live layer on top, in the
     concept's own units: phone-2 is the decision sheet (plan approval), phone-3 the chat sheet (Start card first). ---------- */
  function glowFilter(id, g) {
    return '<filter id="' + id + '" x="-80%" y="-80%" width="260%" height="260%" color-interpolation-filters="sRGB">' +
      '<feGaussianBlur stdDeviation="' + g.sigma + '"/><feComponentTransfer><feFuncA type="linear" slope="' + g.amp + '"/></feComponentTransfer></filter>';
  }
  function diamondPts(b) { return ovPts([[b.cx, b.y], [b.x + b.w, b.cy], [b.cx, b.y + b.h], [b.x, b.cy]]); }
  function glowBox(b) { return ovBox(b); }
  function ph2Svg() {
    var L = window.PH2_LAYOUT, T = window.PH2_TYPE, G = L.glows;
    var dm = ovBox(L.marks.diamond), sm = ovBox(L.marks.blue_star), tr = ovBox(L.marks.codex_tri), gd = ovBox(G.amber_diamond.box);
    var open = ovBox(L.shapes.open), out = '<defs>' + glowFilter('ph2-glow-amber', G.amber_diamond) + glowFilter('ph2-glow-blue', G.blue_star) + '</defs>';
    out += headSvgFor(L, T);
    out += '<polygon class="ov-glow" points="' + diamondPts(gd) + '" fill="' + OV_GLOW_AMBER + '" filter="url(#ph2-glow-amber)"/>';
    out += ovDiamond(dm, OV_AM, 5);
    out += '<g class="ov-glow" filter="url(#ph2-glow-blue)">' + ovStar(sm, OV_GLOW_BLUE) + '</g>' + ovStar(sm, OV_BL);
    out += ovTriangle(tr, OV_BL);
    out += frameText(T, 'label_search', 'ov-serif ov-title', 'Search provenance');
    out += frameText(T, 'label_review_plan', 'ov-sans ov-sub', 'Review plan');
    out += frameText(T, 'label_fix', 'ov-serif ov-title', 'Fix date test');
    out += frameText(T, 'label_verifying', 'ov-sans ov-sub', 'Verifying');
    out += frameText(T, 'label_codex', 'ov-sans ov-codex', 'Codex');
    out += '<rect class="ph-open-rect" x="' + open.x + '" y="' + open.y + '" width="' + open.w + '" height="' + open.h + '" rx="20"/>';
    out += frameText(T, 'title', 'ov-sans ph-title', 'Search provenance');
    out += frameText(T, 'what_label', 'ov-sans ph-label', 'What') + frameText(T, 'what_value', 'ov-sans ph-value', 'Review plan');
    out += frameText(T, 'why_label', 'ov-sans ph-label', 'Why') + frameText(T, 'why_value', 'ov-sans ph-value', 'Plan approval required.');
    out += frameText(T, 'core_label', 'ov-sans ph-label', 'Core consequence') + frameText(T, 'core_value', 'ov-sans ph-value', 'Read exact Core action before deciding.');
    out += frameText(T, 'open_text', 'ov-sans ph-open', 'Open decision', open.cx);
    out += frameText(T, 'bar_text', 'ov-sans ph-placeholder', 'Tell Archeus…');
    return out;
  }
  function ph3Svg() {
    var L = window.PH3_LAYOUT, T = window.PH3_TYPE, G = L.glows;
    var dm = ovBox(L.marks.diamond), sm = ovBox(L.marks.blue_star), nm = ovBox(L.marks.notes_star), gd = ovBox(G.amber_diamond.box);
    var out = '<defs>' + glowFilter('ph3-glow-amber', G.amber_diamond) + glowFilter('ph3-glow-blue', G.blue_star) + '</defs>';
    out += headSvgFor(L, T);
    out += '<polygon class="ov-glow" points="' + diamondPts(gd) + '" fill="' + OV_GLOW_AMBER + '" filter="url(#ph3-glow-amber)"/>';
    out += ovDiamond(dm, OV_AM, 5);
    out += '<g class="ov-glow" filter="url(#ph3-glow-blue)">' + ovStar(sm, OV_GLOW_BLUE) + '</g>' + ovStar(sm, OV_BL);
    out += ovStar(nm, OV_IV);
    [['m-search', dm], ['m-date', sm], ['m-read', nm]].forEach(function (pair) {
      out += '<circle class="ov-hit-mark" data-open="' + pair[0] + '" role="button" tabindex="0" aria-label="' + esc(find(pair[0]).title) +
        '" cx="' + pair[1].cx + '" cy="' + pair[1].cy + '" r="44" fill="transparent"/>';
    });
    return out;
  }
  // The frame the Overview shows: 1 is the Overview (phone-1), 3 is the chat sheet over the phone-3 concept.
  function setPhoneFrame(n) {
    var root = $('#s-now');
    if (!root || !window.PH3_LAYOUT) return;
    root.setAttribute('data-frame', n === 3 ? '3' : '1');
    if (n === 3) {
      $('#ph3-live').innerHTML = ph3Svg();
      $('#feed').classList.add('is-open');
    }
    placeControls(n === 3 ? 3 : 1);
  }
  function buildPhone2() {
    var svg = $('#ph2-live');
    if (!svg || !window.PH2_LAYOUT) return;
    svg.innerHTML = ph2Svg();
  }

  // Thin facet lines inside a hull: interior points joined to the nearest outline vertices, three opacity tiers
  // (far tier fainter). Deterministic per hull id, so a resize keeps the same structure.
  function facetsFor(R, id) {
    var seed = 0; for (var i = 0; i < id.length; i++) seed = (seed * 31 + id.charCodeAt(i)) % 2147483647;
    if (!seed) seed = 7;
    var rnd = function () { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    var minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
    R.forEach(function (v) { minx = Math.min(minx, v.x); maxx = Math.max(maxx, v.x); miny = Math.min(miny, v.y); maxy = Math.max(maxy, v.y); });
    var inside = function (x, y) {
      var c = false;
      for (var a = 0, b = R.length - 1; a < R.length; b = a++) {
        if ((R[a].y > y) !== (R[b].y > y) && x < (R[b].x - R[a].x) * (y - R[a].y) / (R[b].y - R[a].y) + R[a].x) c = !c;
      }
      return c;
    };
    var pts = [], guard = 0;
    while (pts.length < 10 && guard++ < 400) {
      var x = minx + rnd() * (maxx - minx), y = miny + rnd() * (maxy - miny);
      if (inside(x, y)) pts.push({ x: x, y: y });
    }
    var out = [];
    pts.forEach(function (q, i) {
      var tier = i % 3, a = tier === 0 ? 0.2 : tier === 1 ? 0.12 : 0.07, w = tier === 0 ? 0.8 : 0.55;
      R.map(function (v, j) { return { j: j, d: Math.hypot(v.x - q.x, v.y - q.y) }; })
        .sort(function (p1, p2) { return p1.d - p2.d; }).slice(0, 3)
        .forEach(function (o) { out.push({ x1: q.x, y1: q.y, x2: R[o.j].x, y2: R[o.j].y, a: a, w: w }); });
      pts.map(function (r, j) { return { j: j, d: Math.hypot(r.x - q.x, r.y - q.y) }; })
        .filter(function (o) { return o.j !== i; }).sort(function (p1, p2) { return p1.d - p2.d; }).slice(0, 2)
        .forEach(function (o) { out.push({ x1: q.x, y1: q.y, x2: pts[o.j].x, y2: pts[o.j].y, a: a * 0.8, w: 0.4 }); });
    });
    return out;
  }

  // Desktop hulls (round 10c): about 45 thin facet lines in three opacity tiers, no broad wedges.
  function deskFacetsFor(R, id) {
    var seed = 0; for (var i = 0; i < id.length; i++) seed = (seed * 31 + id.charCodeAt(i)) % 2147483647;
    if (!seed) seed = 7;
    var rnd = function () { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
    var minx = Infinity, miny = Infinity, maxx = -Infinity, maxy = -Infinity;
    R.forEach(function (v) { minx = Math.min(minx, v.x); maxx = Math.max(maxx, v.x); miny = Math.min(miny, v.y); maxy = Math.max(maxy, v.y); });
    var inside = function (x, y) {
      var c = false;
      for (var a = 0, b = R.length - 1; a < R.length; b = a++) {
        if ((R[a].y > y) !== (R[b].y > y) && x < (R[b].x - R[a].x) * (y - R[a].y) / (R[b].y - R[a].y) + R[a].x) c = !c;
      }
      return c;
    };
    var pts = [], guard = 0;
    while (pts.length < 22 && guard++ < 800) {
      var x = minx + rnd() * (maxx - minx), y = miny + rnd() * (maxy - miny);
      if (inside(x, y)) pts.push({ x: x, y: y });
    }
    var all = R.concat(pts), tiers = [{ a: 0.5, w: 0.8 }, { a: 0.3, w: 0.55 }, { a: 0.16, w: 0.4 }], out = [];
    pts.forEach(function (q, i) {
      var t = tiers[i % 3];
      all.map(function (v, j) { return { j: j, d: Math.hypot(v.x - q.x, v.y - q.y) }; })
        .filter(function (o) { return all[o.j] !== q; })
        .sort(function (p1, p2) { return p1.d - p2.d; }).slice(0, 3)
        .forEach(function (o) { out.push({ x1: q.x, y1: q.y, x2: all[o.j].x, y2: all[o.j].y, a: t.a, w: t.w }); });
    });
    return out;
  }

  /* ---------- The stage: one renderer for every screen ---------- */

  function makeStage(root, opts) {
    var onPick = opts && opts.onPick ? opts.onPick : null;
    var S = {
      root: root,
      fx: $('.fx', root), sky: $('.sky', root), world: $('.world', root), card: $('.card', root),
      ctx: null, w: 0, h: 0, dpr: 1,
      src: null, scene: null, cam: null, focus: null, hover: null, cardFor: null,
      items: {}, meta: {}, verbItems: [], born: {},
      last: 0, raf: 0
    };
    S.ctx = S.fx.getContext('2d');

    // A new object grows in over 800 ms from the moment it was created; reduced motion shows it at once.
    function grow(key, t) {
      var b = S.born[key];
      if (b === undefined || reduce.matches) return 1;
      var k = Math.min(1, Math.max(0, (t - b) / 800));
      return 1 - Math.pow(1 - k, 3);
    }
    function markBorn(key) { S.born[key] = performance.now(); }

    function resize() {
      var w = root.clientWidth, h = root.clientHeight;
      if (!w || !h || !S.fx.clientWidth) return false;
      S.w = w; S.h = h;
      S.dpr = Math.min(window.devicePixelRatio || 1, 2);
      S.fx.width = Math.round(w * S.dpr);
      S.fx.height = Math.round(h * S.dpr);
      S.sky.width = Math.round((w + 60) * S.dpr);
      S.sky.height = Math.round((h + 60) * S.dpr);
      paintSky();
      return true;
    }

    // Static backdrop: a starfield and a restrained ambient mesh, painted once per size.
    function paintSky() {
      var g = S.sky.getContext('2d');
      var W = S.sky.width / S.dpr, H = S.sky.height / S.dpr;
      g.setTransform(S.dpr, 0, 0, S.dpr, 0, 0);
      g.clearRect(0, 0, W, H);
      var seed = 7 + Math.round(W) * 3;
      var rnd = function () { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
      var pts = [], i, j;
      for (i = 0; i < 96; i++) pts.push({ x: rnd() * W, y: rnd() * H });
      g.lineWidth = 0.6;
      for (i = 0; i < pts.length; i++) {
        for (j = i + 1; j < pts.length; j++) {
          var d = Math.hypot(pts[i].x - pts[j].x, pts[i].y - pts[j].y);
          if (d < 150 && rnd() < 0.55) {
            g.strokeStyle = 'rgba(239,233,218,' + (0.09 * (1 - d / 150) + 0.02).toFixed(3) + ')';
            line(g, pts[i].x, pts[i].y, pts[j].x, pts[j].y);
          }
        }
      }
      pts.forEach(function (p) {
        g.fillStyle = 'rgba(239,233,218,0.3)';
        g.beginPath(); g.arc(p.x, p.y, 1.1, 0, TAU); g.fill();
      });
      for (i = 0; i < 220; i++) {
        var depth = rnd();
        g.fillStyle = 'rgba(239,233,218,' + (0.08 + depth * 0.42).toFixed(3) + ')';
        g.beginPath(); g.arc(rnd() * W, rnd() * H, 0.3 + depth * 0.9, 0, TAU); g.fill();
      }
    }

    function scene() {
      var sc = typeof S.src === 'function' ? S.src(S.w, S.h) : S.src;
      if (sc) sc.projects.forEach(function (p) {
        if (!p.ring) return;
        p.x = 0; p.y = 0;
        p.ring.forEach(function (v) { p.x += v.x; p.y += v.y; });
        p.x /= p.ring.length; p.y /= p.ring.length;
      });
      return sc;
    }

    function goal() {
      if (!S.scene || !S.w) return null;
      if (S.focus) return { x: S.focus.x, y: S.focus.y, s: S.focus.zoom };
      return { x: S.w / 2, y: S.h / 2, s: 1 };
    }

    function setFocus(f) { S.focus = f; kick(); }

    // Chain lit: live work, its ancestors, and whatever the pointer is on.
    function litSet() {
      var H = { core: true };
      var sc = S.scene;
      function chain(id) {
        var cur = id, guard = 0;
        while (cur && guard++ < 8) { H[cur] = true; cur = sc.parent[cur]; }
      }
      sc.nodes.forEach(function (n) { if (n.live) chain(n.id); });
      sc.projects.forEach(function (p) { if (p.active) chain(p.id); });
      if (S.hover) {
        chain(S.hover);
        sc.nodes.forEach(function (n) { if (n.parent === S.hover) chain(n.id); });
        sc.projects.forEach(function (p) { if (p.members && p.id === S.hover) p.members.forEach(chain); });
      }
      return H;
    }

    function hasLive() {
      return S.scene && (S.scene.nodes.some(function (n) { return n.live; }) || S.scene.projects.some(function (p) { return p.active; }));
    }

    // A project hull with a fixed outline: neutral facets (value steps, no colour), a receded inner outline, spokes.
    function ringHull(g, p, c, lit, gp) {
      var R0 = p.ring, C = { x: 0, y: 0 };
      R0.forEach(function (v) { C.x += v.x; C.y += v.y; });
      C.x /= R0.length; C.y /= R0.length;
      g.save(); g.globalAlpha = gp;
      if (p.desk) {
        g.beginPath(); R0.forEach(function (v, j) { if (j) g.lineTo(v.x, v.y); else g.moveTo(v.x, v.y); }); g.closePath();
        g.fillStyle = 'rgba(239,233,218,' + (lit ? 0.03 : 0.015) + ')'; g.fill();
      }
      (p.desk ? [] : R0).forEach(function (v, j) {
        var nv = R0[(j + 1) % R0.length];
        g.beginPath(); g.moveTo(C.x, C.y); g.lineTo(v.x, v.y); g.lineTo(nv.x, nv.y); g.closePath();
        g.fillStyle = 'rgba(239,233,218,' + ((lit ? 0.05 : 0.025) * [0.6, 1.35, 0.9, 1.45, 0.75, 1.1][j % 6]).toFixed(3) + ')';
        g.fill();
      });
      var inner = function (v) { return { x: C.x + (v.x - C.x) * 0.58, y: C.y + (v.y - C.y) * 0.58 }; };
      g.strokeStyle = 'rgba(239,233,218,' + (lit ? 0.14 : 0.07) + ')'; g.lineWidth = 0.6;
      R0.forEach(function (v) { var q = inner(v); line(g, v.x, v.y, q.x, q.y); });
      g.beginPath(); R0.forEach(function (v, j) { var q = inner(v); if (j) g.lineTo(q.x, q.y); else g.moveTo(q.x, q.y); }); g.closePath(); g.stroke();
      g.beginPath(); R0.forEach(function (v, j) { if (j) g.lineTo(v.x, v.y); else g.moveTo(v.x, v.y); }); g.closePath();
      g.strokeStyle = 'rgba(239,233,218,' + (lit ? 0.75 : 0.42) + ')'; g.lineWidth = 1; g.stroke();
      var F = p.desk ? (p._dfac || (p._dfac = deskFacetsFor(R0, p.id))) : (p._facets || (p._facets = facetsFor(R0, p.id)));
      F.forEach(function (f) {
        g.strokeStyle = 'rgba(239,233,218,' + (lit ? f.a : f.a * 0.55).toFixed(3) + ')'; g.lineWidth = f.w;
        line(g, f.x1, f.y1, f.x2, f.y2);
      });
      g.fillStyle = 'rgba(239,233,218,' + (lit ? 0.7 : 0.4) + ')';
      R0.forEach(function (v) { g.beginPath(); g.arc(v.x, v.y, 1.5, 0, TAU); g.fill(); });
      g.restore();
      var hr = 0, anc = R0[0], best = -Infinity, dx = C.x - c.x, dy = C.y - c.y, dl = Math.hypot(dx, dy) || 1;
      R0.forEach(function (v) {
        hr = Math.max(hr, Math.hypot(v.x - C.x, v.y - C.y));
        var pr = ((v.x - C.x) * dx + (v.y - C.y) * dy) / dl;
        if (pr > best) { best = pr; anc = v; }
      });
      var it = S.items[p.id];
      if (it) { it.cx = C.x; it.cy = C.y; it.hr = hr + 6; it.hullR = hr; it.r = 0; it.pt = { x: anc.x + (dx / dl) * 8, y: anc.y + (dy / dl) * 8 }; }
    }

    function draw(t) {
      if (!S.scene || !S.w || !S.cam) return;
      var sc = S.scene, g = S.ctx, w = S.w, h = S.h, cam = S.cam, s = cam.s;
      var anim = reduce.matches ? 0 : t;
      if (sc.desk) updateDeskMarks(sc);
      g.setTransform(S.dpr, 0, 0, S.dpr, 0, 0);
      g.clearRect(0, 0, w, h);

      function P0(x, y) { return { x: (x - cam.x) * s + w / 2, y: (y - cam.y) * s + h / 2 }; }
      var pos = { core: P0(sc.core.x, sc.core.y) };
      sc.nodes.forEach(function (n) { pos[n.id] = P0(n.x, n.y); });
      sc.projects.forEach(function (p) {
        if (p.members && p.members.length) {
          var cx = 0, cy = 0;
          p.members.forEach(function (id) { cx += pos[id].x; cy += pos[id].y; });
          pos[p.id] = { x: cx / p.members.length, y: cy / p.members.length };
        } else {
          pos[p.id] = P0(p.x, p.y);
        }
      });
      var H = litSet();
      var c = pos.core;

      S.sky.style.transform = 'translate3d(' + (-(cam.x - sc.core.x) * s * 0.04).toFixed(2) + 'px,' + (-(cam.y - sc.core.y) * s * 0.04).toFixed(2) + 'px,0)';

      // Faint orbit rings around Archeus.
      if (sc.frame) {
        var f = sc.frame, fc = P0(f.x, f.y);
        g.save(); g.strokeStyle = 'rgba(239,233,218,0.1)'; g.lineWidth = 1;
        g.beginPath();
        for (var k = 0; k < 8; k++) {
          var ang = k * TAU / 8 - TAU / 16;
          var fx = fc.x + Math.cos(ang) * f.r * s, fy = fc.y + Math.sin(ang) * f.r * s;
          if (k) g.lineTo(fx, fy); else g.moveTo(fx, fy);
        }
        g.closePath(); g.stroke(); g.restore();
      }

      // Project hulls: a faceted shell around each project's missions, with an inner mesh.
      sc.projects.forEach(function (p) {
        // Desktop: the art draws the hulls; ringHull still runs for the label anchor, with a no-op context.
        if (p.ring) { ringHull(sc.desk ? NO_DRAW : g, p, c, !!H[p.id], grow(p.id, anim)); return; }
        if (!p.members) return;
        var ring = [], gp = grow(p.id, anim);
        p.members.forEach(function (id) {
          var q = pos[id], halo = S.items[id] ? S.items[id].r * s + 46 * s : 60 * s;
          for (var j = 0; j < 8; j++) ring.push({ x: q.x + Math.cos(j * TAU / 8) * halo, y: q.y + Math.sin(j * TAU / 8) * halo });
        });
        if (!p.members.length) {
          var c0 = pos[p.id];
          for (var j0 = 0; j0 < 8; j0++) ring.push({ x: c0.x + Math.cos(j0 * TAU / 8) * 60 * s, y: c0.y + Math.sin(j0 * TAU / 8) * 60 * s });
        }
        var hull = convexHull(ring);
        if (hull.length < 3) return;
        var lit = !!H[p.id];
        var cc = pos[p.id];
        var hr = 0;
        hull.forEach(function (v) { hr = Math.max(hr, Math.hypot(v.x - cc.x, v.y - cc.y)); });
        var dx = cc.x - c.x, dy = cc.y - c.y, dl = Math.hypot(dx, dy) || 1;
        dx /= dl; dy /= dl;
        var anchor = hull.reduce(function (best, v) {
          return (v.x - cc.x) * dx + (v.y - cc.y) * dy > (best.x - cc.x) * dx + (best.y - cc.y) * dy ? v : best;
        }, hull[0]);
        var it = S.items[p.id];
        if (it) { it.cx = cc.x; it.cy = cc.y; it.hr = hr + 6; it.pt = { x: anchor.x + dx * 10, y: anchor.y + dy * 10 }; it.r = 0; it.hullR = hr; }
        g.save(); g.globalAlpha = gp;
        g.beginPath(); hull.forEach(function (v, j) { if (j) g.lineTo(v.x, v.y); else g.moveTo(v.x, v.y); }); g.closePath();
        var base = (sc.compact ? 0.075 : 0.05) * (lit ? 1 : 0.45);
        hull.forEach(function (v, j) {
          var nv = hull[(j + 1) % hull.length];
          g.beginPath(); g.moveTo(cc.x, cc.y); g.lineTo(v.x, v.y); g.lineTo(nv.x, nv.y); g.closePath();
          g.fillStyle = rgba(p.hue, base * [0.7, 1.25, 0.9, 1.35, 0.8, 1.1][j % 6]); g.fill();
        });
        g.beginPath(); hull.forEach(function (v, j) { if (j) g.lineTo(v.x, v.y); else g.moveTo(v.x, v.y); }); g.closePath();
        g.strokeStyle = rgba(p.hue, lit ? 0.6 : 0.24); g.lineWidth = 1; g.stroke();
        g.strokeStyle = rgba(p.hue, lit ? 0.22 : 0.08); g.lineWidth = 0.8;
        hull.forEach(function (v) { line(g, cc.x, cc.y, v.x, v.y); });
        p.members.forEach(function (id) {
          var q = pos[id];
          hull.slice().sort(function (a, b) { return Math.hypot(a.x - q.x, a.y - q.y) - Math.hypot(b.x - q.x, b.y - q.y); })
            .slice(0, 3).forEach(function (v) {
              g.strokeStyle = rgba(p.hue, lit ? 0.22 : 0.08);
              line(g, q.x, q.y, v.x, v.y);
            });
        });
        g.fillStyle = rgba(p.hue, lit ? 0.9 : 0.5);
        hull.forEach(function (v) { g.beginPath(); g.arc(v.x, v.y, lit ? 2.2 : 1.6, 0, TAU); g.fill(); });
        g.restore();
      });

      if (sc.poly) {
        g.save(); g.strokeStyle = 'rgba(239,233,218,0.14)'; g.lineWidth = 1;
        g.beginPath(); sc.poly.forEach(function (p, j) { if (j) g.lineTo(p.x, p.y); else g.moveTo(p.x, p.y); }); g.closePath(); g.stroke();
        g.strokeStyle = 'rgba(239,233,218,0.06)';
        sc.poly.forEach(function (p) { line(g, c.x, c.y, p.x, p.y); });
        g.fillStyle = 'rgba(239,233,218,0.45)';
        sc.poly.forEach(function (p) { g.beginPath(); g.arc(p.x, p.y, 1.8, 0, TAU); g.fill(); });
        g.restore();
      }

      // Links: the lit chain is bright and carries a travelling pulse when live; the rest recede.
      sc.links.forEach(function (l, idx) {
        if (sc.desk) return;
        var a = pos[l.a], b = pos[l.b];
        if (!a || !b) return;
        var gl = grow(l.a + '>' + l.b, anim);
        if (gl < 1) b = { x: a.x + (b.x - a.x) * gl, y: a.y + (b.y - a.y) * gl };
        var fresh = S.born[l.a + '>' + l.b] !== undefined && performance.now() - S.born[l.a + '>' + l.b] < 6000;
        var lit = !!(H[l.a] && H[l.b]) && !l.faint;
        g.save();
        if (lit) {
          g.strokeStyle = l.col; g.globalAlpha = 0.5; g.lineWidth = 1.1 * Math.min(1.2, s);
          if (l.live) { g.shadowColor = l.col; g.shadowBlur = 16; }
          line(g, a.x, a.y, b.x, b.y);
          g.shadowBlur = 0; g.globalAlpha = 0.95; g.lineWidth = 1.4;
          g.setLineDash(l.dash ? [2, 6] : fresh ? [3, 4] : []);
          line(g, a.x, a.y, b.x, b.y);
          g.setLineDash([]);
          if (l.arrow) {
            var ang = Math.atan2(b.y - a.y, b.x - a.x), ax = a.x + (b.x - a.x) * 0.62, ay = a.y + (b.y - a.y) * 0.62, ah = 6 * Math.min(1.2, s);
            g.fillStyle = l.col; g.globalAlpha = 0.95; g.shadowBlur = 0;
            g.beginPath(); g.moveTo(ax + Math.cos(ang) * ah, ay + Math.sin(ang) * ah);
            g.lineTo(ax + Math.cos(ang + 2.5) * ah * 0.7, ay + Math.sin(ang + 2.5) * ah * 0.7);
            g.lineTo(ax + Math.cos(ang - 2.5) * ah * 0.7, ay + Math.sin(ang - 2.5) * ah * 0.7); g.closePath(); g.fill();
          }
          if (l.live && !reduce.matches) {
            var u = ((t / 1800) + idx * 0.31) % 1;
            g.fillStyle = '#FFF6E0'; g.shadowColor = l.col; g.shadowBlur = 12; g.globalAlpha = 1;
            g.beginPath(); g.arc(a.x + (b.x - a.x) * u, a.y + (b.y - a.y) * u, 2.6, 0, TAU); g.fill();
          }
        } else {
          g.strokeStyle = 'rgba(239,233,218,' + (l.dash ? 0.08 : 0.12) + ')'; g.lineWidth = 0.7;
          if (l.dash || fresh) g.setLineDash(l.dash ? [3, 5] : [3, 4]);
          line(g, a.x, a.y, b.x, b.y);
        }
        g.restore();
      });

      (sc.sats || []).forEach(function (p, i) {
        var q = P0(p.x, p.y);
        drawSolid(g, TET, q.x, q.y, 12 * s, { y: 0.3 + i, x: 0.4 }, IVORY, { alpha: 0.32, dotR: 1.2, lw: 0.8 });
      });

      // Shape-only projects (the mission chain) are drawn as small octahedra.
      sc.projects.forEach(function (p) {
        if (p.members) return;
        var q = pos[p.id], lit = !!H[p.id];
        drawSolid(g, OCT, q.x, q.y, 34 * s, { y: 0.4, x: 0.5 }, p.hue, { alpha: lit ? 1 : 0.6, wash: true, glow: lit, glyph: 'cluster', dotR: 2 });
        var it = S.items[p.id];
        if (it) { it.cx = q.x; it.cy = q.y; it.hr = 40 * s; it.pt = q; it.r = 34 * s; }
      });

      if (!sc.desk) drawCore(g, c, anim, !!H.core, s, sc.knot);
      var it0 = S.items.core;
      if (it0) { it0.cx = c.x; it0.cy = c.y; it0.hr = 60 * s; it0.pt = c; it0.r = 60 * s; }

      // Figures: receding first, lit last. Overview marks are small glyphs; other screens keep their bodies.
      var order = sc.nodes.slice().sort(function (a, b) { return (H[a.id] ? 1 : 0) - (H[b.id] ? 1 : 0); });
      order.forEach(function (n) {
        var q = pos[n.id], lit = !!H[n.id], R = n.r * s;
        var gn = grow(n.id, anim);
        if (gn < 1) R *= 0.35 + 0.65 * gn;
        if (n.tri || n.box) {
          drawShape(g, n, q, gn);
          var its = S.items[n.id];
          if (its) { its.cx = q.x; its.cy = q.y; its.hr = R + 10; its.pt = q; its.r = R; its.par = n.parent; }
          return;
        }
        var col = STATE[n.state] ? STATE[n.state].color : IVORY;
        if (n.mark) {
          if (!sc.desk) { // Now frame: the mark is an SVG shape (buildDeskMarks), not a canvas glyph
          g.save(); g.globalAlpha = gn;
          if (n.kind === 'exec' && sc.desk) drawDeskExec(g, q, pos.verif, pos.results, lit);
          else if (n.kind === 'exec') drawTriangle(g, q.x, q.y, Math.max(12, R * 1.4), lit);
          else if (n.dot) { g.fillStyle = STATE.running.color; g.beginPath(); g.arc(q.x, q.y, sc.desk ? 5.2 : 4.2, 0, TAU); g.fill(); }
          else if (n.kind === 'mission' && sc.desk) drawDeskMark(g, q.x, q.y, n, Math.max(6, R), lit);
          else if (n.kind === 'mission') drawMark(g, q.x, q.y, n.state, Math.max(5, R), lit);
          else drawSolid(g, n.solid, q.x, q.y, Math.max(9, R), { y: n.seed * TAU, x: 0.42 }, IVORY, { alpha: 0.75 * gn, wash: false, glyph: n.glyph, dotR: 1.6, lw: 0.9 });
          g.restore();
          }
        } else {
          var rot = { y: n.seed * TAU + anim * (n.state === 'running' ? 0.00055 : 0.00022), x: 0.42 + 0.14 * Math.sin(anim * 0.00025 + n.seed * 7) };
          var alpha = (lit || n.live ? 1 : n.kind === 'device' || n.kind === 'record' ? 0.55 : 0.5) * gn;
          if (n.kind === 'mission' || n.kind === 'record') {
            drawSolid(g, n.solid, q.x, q.y, R, rot, col, { alpha: alpha, wash: true, glow: lit, glyph: n.glyph, inner: true, dotR: lit ? 2.6 : 2.1 });
          } else if (n.kind === 'exec' || n.kind === 'agent') {
            drawSolid(g, n.solid, q.x, q.y, R, rot, n.kind === 'exec' ? IVORY : col, { alpha: n.kind === 'exec' ? 0.9 : 1, wash: true, glow: lit, glyph: n.glyph, dotR: 2.4 });
          } else if (n.kind === 'device') {
            drawSolid(g, n.solid, q.x, q.y, R, rot, col, { alpha: 0.85, dash: n.dash ? [3, 3] : [], glyph: n.glyph, dotR: 1.8, lw: 1.2 });
          }
          if (n.kind === 'agent') {
            g.globalAlpha = gn;
            drawBadge(g, n.state, q.x - R * 0.9, q.y - R * 0.86, anim, !reduce.matches);
            g.globalAlpha = 1;
          }
        }
        var it = S.items[n.id];
        if (it) { it.cx = q.x; it.cy = q.y; it.hr = R + 10; it.pt = q; it.r = R; it.par = n.parent; }
      });

      placeLabels(pos, H);
      placeVerbs(pos);
      updateCard();
    }

    // A candidate is a side (row, row-reverse, column, column-reverse) and, for the row sides, a vertical hang (c, u, d).
    function boxFor(pt, off, L, cand) {
      var W = L.tw, Hh = L.th, x0, y0, v = cand.v;
      if (cand.d === 'row' || cand.d === 'row-reverse') {
        x0 = cand.d === 'row' ? pt.x + off : pt.x - off - W;
        y0 = v === 'c' ? pt.y - Hh / 2 : v === 'u' ? pt.y - Hh + 6 : pt.y - 6;
      } else if (cand.d === 'column') { x0 = pt.x - W / 2; y0 = pt.y + off; }
      else { x0 = pt.x - W / 2; y0 = pt.y - off - Hh; }
      return { x0: x0, y0: y0, x1: x0 + W, y1: y0 + Hh };
    }

    function candidatesFor(sc) {
      var out = [];
      ['row', 'row-reverse'].forEach(function (d) {
        ['c', 'u', 'd'].forEach(function (v) {
          out.push({ d: d, v: v, dx: d === 'row' ? 1 : -1, dy: v === 'u' ? -1 : v === 'd' ? 1 : 0 });
        });
      });
      out.push({ d: 'column', v: 'c', dx: 0, dy: 1 }, { d: 'column-reverse', v: 'c', dx: 0, dy: -1 });
      return out.filter(function (cd) { return !sc.labelDirs || sc.labelDirs.indexOf(cd.d) >= 0; });
    }

    // Label budget. Project names and Archeus always show. Far (whole space): missions show only when they need
    // you or are running, the rest are counted. Zoomed to a project: all of its missions show. Hover always shows.
    function labelQuiet(id, it) {
      var sc = S.scene;
      if (S.hover === id) return false;
      if (sc.compact) return it.kind === 'mission' && !sc.nodes.some(function (n) { return n.id === id && n.live; });
      if (it.kind !== 'mission' && it.kind !== 'exec') return false;
      if (S.focus || sc.nodes.length <= 12) return false;
      var n = sc.nodes.filter(function (x) { return x.id === id; })[0];
      return !(n && (n.state === 'waiting' || n.state === 'running' || (n.kind === 'exec' && n.live)));
    }

    function overlaps(a, b, pad) {
      return a.x0 < b.x1 + pad && a.x1 + pad > b.x0 && a.y0 < b.y1 + pad && a.y1 + pad > b.y0;
    }

    function circleHitsBox(cx, cy, r, b) {
      var nx = Math.min(Math.max(cx, b.x0), b.x1), ny = Math.min(Math.max(cy, b.y0), b.y1);
      return (nx - cx) * (nx - cx) + (ny - cy) * (ny - cy) < r * r;
    }

    // Label placement: four candidate sides, scored for clearance from other labels, figures and the core.
    function placeLabels(pos, H) {
      var sc = S.scene, s = S.cam.s, c = pos.core;
      var placed = [];
      var circles = [];
      Object.keys(S.items).forEach(function (id) {
        var it = S.items[id];
        if (id === 'core' || !it.pt || !it.lbl) return;
        if (it.r > 0) circles.push({ id: id, x: it.cx, y: it.cy, r: it.r + 6 });
      });
      var core = S.items.core;
      if (core && core.lbl) {
        var cdy = (sc.coreDy || (sc.desk ? 66 : 84)) * s;
        core.lbl.style.transform = 'translate(' + (c.x - core.tw / 2).toFixed(1) + 'px,' + (c.y + cdy).toFixed(1) + 'px)';
        placed.push({ x0: c.x - core.tw / 2, y0: c.y + cdy, x1: c.x + core.tw / 2, y1: c.y + cdy + core.th });
      }
      var order = sc.projects.map(function (p) { return p.id; });
      sc.nodes.slice().sort(function (a, b) {
        var ra = a.kind === 'mission' ? RANK[a.state] : 4, rb = b.kind === 'mission' ? RANK[b.state] : 4;
        return ra - rb;
      }).forEach(function (n) { order.push(n.id); });
      var dirs = candidatesFor(sc);

      // Each label leaves radially from its parent's centre: a mission from its project hull, a project from Archeus.
      var entries = [];
      order.forEach(function (id) {
        var it = S.items[id];
        if (!it || !it.lbl || !it.pt) return;
        if (it.at) {
          var ax = Math.min(Math.max(it.at.x, 6), S.w - it.tw - 6);
          var fb = { x0: ax, y0: it.at.y, x1: ax + it.tw, y1: it.at.y + it.th };
          entries.push({ id: id, it: it, box: fb, bw: it.tw, bh: it.th, cand: { d: 'row' }, dir: { x: 0, y: 0 }, fixed: true });
          placed.push(fb);
          return;
        }
        var fix = sc.labelFix && sc.labelFix[id];
        var pt = it.pt, off = it.r + 12;
        if (fix && fix.at) { pt = fix.at; off = 0; }
        var par = it.par && S.items[it.par] && S.items[it.par].cx !== undefined ? S.items[it.par] : null;
        var org = par ? { x: par.cx, y: par.cy } : c;
        var ox = pt.x - org.x, oy = pt.y - org.y, len = Math.hypot(ox, oy) || 1;
        ox /= len; oy /= len;
        var cands = fix && fix.d ? [{ d: fix.d, v: fix.v, dx: 1, dy: 0 }] : dirs.slice().sort(function (a, b) {
          var la = Math.hypot(a.dx, a.dy) || 1, lb = Math.hypot(b.dx, b.dy) || 1;
          return (b.dx * ox + b.dy * oy) / lb - (a.dx * ox + a.dy * oy) / la;
        });
        var best = null;
        for (var i = 0; i < cands.length; i++) {
          var bx = boxFor(pt, off, it, cands[i]);
          var cost = 0;
          if (bx.x0 < 8 || bx.y0 < 8 || bx.x1 > S.w - 8 || bx.y1 > S.h - 8) cost += 1000;
          if (circleHitsBox(c.x, c.y, 62 * s, bx)) cost += 1000;
          if (it.hullR && circleHitsBox(it.cx, it.cy, it.hullR, bx)) cost += 400;
          for (var k = 0; k < placed.length; k++) if (overlaps(bx, placed[k], 8)) cost += 500;
          circles.forEach(function (ci) { if (ci.id !== id && circleHitsBox(ci.x, ci.y, ci.r, bx)) cost += 300; });
          if (!best || cost < best.cost) best = { cost: cost, cand: cands[i], box: bx };
          if (cost === 0) break;
        }
        var box = best.box, bw = box.x1 - box.x0, bh = box.y1 - box.y0;
        var sx = Math.min(Math.max(box.x0, 8), S.w - bw - 8), sy = Math.min(Math.max(box.y0, 8), S.h - bh - 8);
        box = { x0: sx, y0: sy, x1: sx + bw, y1: sy + bh };
        placed.push(box);
        entries.push({ id: id, it: it, box: box, bw: bw, bh: bh, cand: best.cand, dir: { x: ox, y: oy }, fixed: !!fix });
      });
      // Relaxation: a label that still touches another moves outward along its radial, four passes at most.
      for (var pass = 0; pass < 10; pass++) {
        var moved = false;
        for (var a = 0; a < entries.length; a++) for (var b = a + 1; b < entries.length; b++) {
          if (!overlaps(entries[a].box, entries[b].box, 6) || entries[b].fixed) continue;
          var e = entries[b], nb = e.box;
          if (e.fixed) continue;
          var nx = Math.min(Math.max(nb.x0 + e.dir.x * 18, 8), S.w - e.bw - 8);
          var ny = Math.min(Math.max(nb.y0 + e.dir.y * 18, 8), S.h - e.bh - 8);
          e.box = { x0: nx, y0: ny, x1: nx + e.bw, y1: ny + e.bh };
          moved = true;
        }
        if (!moved) break;
      }
      var budget = S.root.querySelector('.budget'), hidden = 0;
      entries.forEach(function (e) {
        if (e.it.kind === 'mission' && labelQuiet(e.id, e.it)) hidden++;
        var quiet = labelQuiet(e.id, e.it) || !!(sc.labelFix && sc.labelFix[e.id] && sc.labelFix[e.id].hide);
        var fresh = S.born[e.id] !== undefined && performance.now() - S.born[e.id] < 6000;
        e.it.lbl.className = e.it.cls + ' d-' + e.cand.d + (quiet ? ' quiet' : '') + (fresh ? ' is-new' : '');
        e.it.lbl.style.transform = 'translate(' + e.box.x0.toFixed(1) + 'px,' + e.box.y0.toFixed(1) + 'px)';
      });
      if (budget) {
        budget.textContent = hidden ? '+' + hidden + ' more missions, zoom a project to see them' : '';
        budget.hidden = true;
      }
      // Hit targets follow the figures.
      Object.keys(S.items).forEach(function (id) {
        var it = S.items[id];
        if (!it.hit || !it.cx) return;
        var D = 2 * it.hr;
        it.hit.style.width = D.toFixed(1) + 'px';
        it.hit.style.height = D.toFixed(1) + 'px';
        it.hit.style.transform = 'translate(' + (it.cx - it.hr).toFixed(1) + 'px,' + (it.cy - it.hr).toFixed(1) + 'px)';
      });
    }

    function placeVerbs(pos) {
      S.verbItems.forEach(function (v) {
        var a = pos[v.a], b = pos[v.b];
        if (!a || !b) return;
        var dx = b.x - a.x, dy = b.y - a.y, dl = Math.hypot(dx, dy) || 1;
        var nx = -dy / dl, ny = dx / dl, side = v.side || 1;
        var mx = a.x + dx * 0.5 + nx * 16 * side, my = a.y + dy * 0.5 + ny * 16 * side;
        if (v.at) { mx = v.at.x; my = v.at.y; }
        v.el.style.transform = 'translate(' + (mx - v.el.offsetWidth / 2).toFixed(1) + 'px,' + (my - 10).toFixed(1) + 'px)';
      });
    }

    function updateCard() {
      var id = S.hover, meta = id && S.meta[id], it = id && S.items[id];
      if (!meta || !it || !it.cx) { S.card.hidden = true; S.cardFor = null; return; }
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
      var c = S.items.core;
      var cx = c ? c.cx : S.w / 2, cy = c ? c.cy : S.h / 2;
      var ox = it.cx - cx, oy = it.cy - cy, len = Math.hypot(ox, oy) || 1;
      ox /= len; oy /= len;
      var dist = it.hr + 60 + Math.max(cw, ch) * 0.3;
      var left = Math.min(Math.max(it.cx + ox * dist - cw / 2, 8), S.w - cw - 8);
      var top = Math.min(Math.max(it.cy + oy * dist - ch / 2, 8), S.h - ch - 8);
      S.card.style.transform = 'translate(' + left.toFixed(1) + 'px,' + top.toFixed(1) + 'px)';
    }

    function addLabel(id, o) {
      var lbl = document.createElement('div');
      lbl.className = 'lbl ' + o.cls;
      lbl.dataset.lid = id;
      lbl.innerHTML = '<p class="k"></p><p class="t"></p><p class="s"></p>';
      lbl.querySelector('.k').textContent = o.kicker || '';
      lbl.querySelector('.t').textContent = o.title;
      var sub = lbl.querySelector('.s');
      if (o.sub) { sub.textContent = o.sub; if (o.subCls) sub.className = 's ' + o.subCls; } else sub.remove();
      if (!o.kicker) lbl.querySelector('.k').remove();
      if (o.action) {
        var a = document.createElement('a');
        a.className = 'btn review act'; a.href = o.action.href;
        a.textContent = o.action.text;
        a.setAttribute('aria-label', o.action.aria);
        lbl.appendChild(a);
      }
      S.world.appendChild(lbl);
      var it = S.items[id] || (S.items[id] = {});
      it.lbl = lbl; it.cls = o.cls; it.kind = o.kind;
      return it;
    }

    function addHit(id, o) {
      var hit = document.createElement('button');
      hit.type = 'button'; hit.className = 'hit';
      hit.setAttribute('aria-label', o.aria);
      hit.addEventListener('pointerenter', function () { setHover(id); });
      hit.addEventListener('pointerleave', function () { setHover(null); });
      hit.addEventListener('focus', function () { setHover(id); });
      hit.addEventListener('blur', function () { setHover(null); });
      hit.addEventListener('click', function () { if (onPick) onPick(id, o.kind); });
      S.world.appendChild(hit);
      S.items[id].hit = hit;
      S.meta[id] = o.meta;
    }

    function build() {
      var sc = S.scene;
      S.world.style.setProperty('--lk', Math.max(0.72, Math.min(1, sc.k)).toFixed(3));
      S.world.innerHTML = '';
      S.items = {}; S.meta = {}; S.verbItems = [];
      S.card.hidden = true; S.cardFor = null;
      S.items.core = addLabel('core', { cls: 'lbl core', kicker: '', title: 'Archeus', sub: 'Core connected', kind: 'core' });
      sc.projects.forEach(function (p) {
        if (p.sub) return;
        var live = p.members ? sc.nodes.filter(function (n) { return p.members.indexOf(n.id) >= 0 && n.live; }).length : p.live;
        var sub = sc.compact ? '' : (p.note || ((p.count || (p.members ? p.members.length : 0)) + ' missions, ' + live + ' live'));
        addLabel(p.id, { cls: 'lbl project', kicker: 'Project', title: p.name, sub: sub, kind: 'project' });
        if (p.members) addHit(p.id, { aria: p.name + ', ' + sub, kind: 'project', meta: { kicker: 'Project', title: p.name, lines: [sub] } });
        else S.items[p.id].hit = null;
      });
      sc.nodes.forEach(function (n) {
        var st = n.st, sub = n.detail || n.sub;
        var subCls = n.kind === 'mission' ? 'st-' + n.state : n.kind === 'device' ? { connected: 'st-done', recent: 'st-running', future: 'st-idle' }[n.state] || '' : n.kind === 'exec' && n.live ? 'st-running' : '';
        var action = n.kind === 'mission' && n.state === 'waiting' ? { href: '#/plan/' + n.id, text: sc.compact ? 'Review' : 'Review →', aria: 'Review plan for ' + n.title } : null;
        var line2 = n.labelSub || (n.kind === 'mission' ? n.detail : n.kind === 'exec' ? 'execution' : st ? st + (sub ? ' · ' + sub : '') : sub);
        var execPhone = sc.compact && n.kind === 'exec';
        addLabel(n.id, { cls: 'lbl ' + n.kind, kicker: n.kicker, title: execPhone ? 'Codex · execution' : n.title, sub: execPhone ? '' : line2, subCls: subCls, kind: n.kind, action: action });
        if (n.labelAt) S.items[n.id].at = n.labelAt;
        if (n.hit) {
          addHit(n.id, { aria: n.title + ', ' + st + (n.detail ? ', ' + n.detail : ''), kind: n.kind, meta: { kicker: n.kicker, title: n.title, lines: [st, sub].filter(Boolean) } });
        }
      });
      sc.links.forEach(function (l) {
        if (!l.verb) return;
        var lbl = document.createElement('div');
        lbl.className = 'lbl verb';
        lbl.textContent = l.verb;
        S.world.appendChild(lbl);
        S.verbItems.push({ el: lbl, a: l.a, b: l.b, side: S.verbItems.length % 2 ? -1 : 1, at: l.verbAt });
      });
      Object.keys(S.items).forEach(function (id) {
        var it = S.items[id];
        if (it.lbl) { it.tw = it.lbl.offsetWidth; it.th = it.lbl.offsetHeight; }
      });
      S.verbItems.forEach(function (v) { v.el.style.left = '0'; v.el.style.top = '0'; });
    }

    function setHover(id) {
      if (S.hover === id) return;
      S.hover = id;
      draw(reduce.matches ? 0 : S.last);
      kick();
    }

    function setScene(src) {
      S.src = src;
      S.focus = null;
      S.hover = null;
      if (!resize()) return;
      S.scene = scene();
      build();
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
      var moving = Math.abs(g.x - c.x) > 0.2 || Math.abs(g.y - c.y) > 0.2 || Math.abs(g.s - c.s) > 0.002;
      if (!moving) S.cam = g;
      return moving;
    }

    // The loop runs while anything moves; it stops when the tab is hidden.
    function frame(t) {
      S.raf = 0;
      if (document.hidden || !S.scene || !root.offsetWidth) return;
      var moving = stepCam(t);
      S.last = t;
      draw(reduce.matches ? 0 : t);
      if (moving || (!reduce.matches && (hasLive() || S.scene.nodes.length))) S.raf = requestAnimationFrame(frame);
    }

    function kick() {
      if (!S.raf && !document.hidden && S.scene) {
        S.last = performance.now();
        S.raf = requestAnimationFrame(frame);
      }
    }

    function relayout() {
      if (!S.src || !resize()) return;
      S.scene = scene();
      build();
      S.cam = goal();
      draw(0);
      kick();
    }

    root.addEventListener('pointerleave', function () { setHover(null); });

    S.setScene = setScene;
    S.setFocus = setFocus;
    S.markBorn = markBorn;
    S.setHover = setHover;
    S.relayout = relayout;
    S.kick = kick;
    return S;
  }

  /* ---------- Stages and screens ---------- */

  // Round 10d: the desktop Overview is a 1296 x 729 frame scaled uniformly to the window (see fitFrame).
  // Round 10e: the Now frame's marks are live SVG shapes over the art, coloured from the data model's state.
  var DESK_MARK_SHAPES = {
    'm-search': 'diamond', 'm-done': 'diamond', 'm-index': 'diamond', 'm-date': 'star', 'm-read': 'sparkle',
    'exec': 'triangle', 'verif': 'dot', 'results': 'dot'
  };
  function deskMarkPath(kind) {
    if (kind === 'diamond') return 'M0,-8 L8,0 L0,8 L-8,0 Z';
    if (kind === 'star') return 'M0,-14 Q2,-2 14,0 Q2,2 0,14 Q-2,2 -14,0 Q-2,-2 0,-14 Z';
    if (kind === 'sparkle') return 'M0,-12 Q1.5,-1.5 12,0 Q1.5,1.5 0,12 Q-1.5,1.5 -12,0 Q-1.5,-1.5 0,-12 Z';
    return '';
  }
  var DESK_MARK_COLOR = { 'm-search': '#F2B544', 'm-done': '#9AA5B8', 'm-index': '#9AA5B8', 'm-read': '#EFE9DA', 'm-date': '#6FB1FF', exec: '#6FB1FF', verif: '#6FB1FF', results: '#6FB1FF' };
  var deskMarkEls = null;
  function buildDeskMarks() {
    var host = $('#now-stage');
    if (!host) return;
    var NS = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(NS, 'svg');
    svg.setAttribute('class', 'desk-marks');
    svg.setAttribute('viewBox', '0 0 1296 729');
    svg.setAttribute('aria-hidden', 'true');
    svg.setAttribute('focusable', 'false');
    deskMarkEls = {};
    var L = CONCEPT_LAYOUT.desktop.marks;
    Object.keys(DESK_MARK_SHAPES).forEach(function (id) {
      var p = L[id === 'm-date' ? 'm-date' : id] || L[id];
      if (!p) return;
      var kind = DESK_MARK_SHAPES[id];
      var g = document.createElementNS(NS, 'g');
      g.setAttribute('transform', 'translate(' + p[0] + ' ' + p[1] + ')');
      g.setAttribute('data-mark', id);
      var glow = document.createElementNS(NS, 'circle');
      glow.setAttribute('class', 'mk-glow');
      glow.setAttribute('fill', DESK_MARK_COLOR[id] || STATE.running.color);
      glow.setAttribute('r', id === 'm-date' ? 11 : kind === 'dot' ? 7 : kind === 'triangle' ? 6 : 9);
      g.appendChild(glow);
      var shape = document.createElementNS(NS, kind === 'dot' ? 'circle' : kind === 'triangle' ? 'g' : 'path');
      if (kind === 'dot') shape.setAttribute('r', id === 'exec' ? 4.5 : 5.5);
      shape.setAttribute('fill', DESK_MARK_COLOR[id] || STATE.running.color);
      if (kind === 'diamond' || kind === 'star' || kind === 'sparkle') shape.setAttribute('d', deskMarkPath(kind));
      if (kind === 'triangle') {
        shape = document.createElementNS(NS, 'path');
        shape.setAttribute('d', 'M-8,29 L-14,36 L-8,43 M-1,43 L5,29 M8,29 L14,36 L8,43');
        shape.setAttribute('fill', 'none');
        shape.setAttribute('stroke-width', '1.7');
        shape.setAttribute('stroke-linecap', 'round');
        shape.setAttribute('stroke-linejoin', 'round');
        shape.setAttribute('stroke', STATE.running.color);
        g.appendChild(shape);
        var apex = document.createElementNS(NS, 'circle');
        apex.setAttribute('r', '4.5');
        apex.setAttribute('fill', '#6FB1FF');
        g.appendChild(apex);
      } else {
        g.appendChild(shape);
      }
      svg.appendChild(g);
      deskMarkEls[id] = { g: g, glow: glow, shape: shape, kind: kind };
    });
    // The blue link from Fix date test to the Codex apex: redrawn live, because the art's copy is cleared under the marks.
    var m0 = L['m-date'], m1 = L.exec, dx = m1[0] - m0[0], dy = m1[1] - m0[1], dl = Math.hypot(dx, dy);
    var ux = dx / dl, uy = dy / dl;
    var ln = document.createElementNS(NS, 'line');
    ln.setAttribute('class', 'mk-link');
    ln.setAttribute('x1', (m0[0] + ux * 17).toFixed(1)); ln.setAttribute('y1', (m0[1] + uy * 17).toFixed(1));
    ln.setAttribute('x2', (m1[0] - ux * 10).toFixed(1)); ln.setAttribute('y2', (m1[1] - uy * 10).toFixed(1));
    ln.setAttribute('stroke', DESK_MARK_COLOR['m-date']); ln.setAttribute('stroke-width', '1.4');
    ln.setAttribute('marker-end', 'url(#desk-arrow)');
    var defs = document.createElementNS(NS, 'defs');
    var mk = document.createElementNS(NS, 'marker');
    mk.setAttribute('id', 'desk-arrow'); mk.setAttribute('viewBox', '0 0 8 8'); mk.setAttribute('refX', '6'); mk.setAttribute('refY', '4');
    mk.setAttribute('markerWidth', '6'); mk.setAttribute('markerHeight', '6'); mk.setAttribute('orient', 'auto');
    var tip = document.createElementNS(NS, 'path'); tip.setAttribute('d', 'M0,0 L8,4 L0,8 Z'); tip.setAttribute('fill', DESK_MARK_COLOR['m-date']);
    mk.appendChild(tip); defs.appendChild(mk); svg.appendChild(defs); svg.appendChild(ln);
    // The Codex triangle's two sides from the apex to the Verification and Results dots, redrawn for the same reason.
    ['verif', 'results'].forEach(function (k) {
      var q = L[k], ex = m1[0], ey = m1[1], ddx = q[0] - ex, ddy = q[1] - ey, dd = Math.hypot(ddx, ddy);
      var sd = document.createElementNS(NS, 'line');
      sd.setAttribute('class', 'mk-link');
      sd.setAttribute('x1', (ex + ddx / dd * 9).toFixed(1)); sd.setAttribute('y1', (ey + ddy / dd * 9).toFixed(1));
      sd.setAttribute('x2', (q[0] - ddx / dd * 8).toFixed(1)); sd.setAttribute('y2', (q[1] - ddy / dd * 8).toFixed(1));
      sd.setAttribute('stroke', DESK_MARK_COLOR.exec); sd.setAttribute('stroke-width', '1.4');
      svg.appendChild(sd);
    });
    host.insertBefore(svg, host.querySelector('.world'));
    deskMarkEls.svg = svg;
  }
  // Colour from the node's state: amber needs the owner, blue is live, grey is done or idle, ivory is neutral.
  function updateDeskMarks(sc) {
    if (!deskMarkEls) return;
    if (deskMarkEls.exec) deskMarkEls.exec.shape.setAttribute('stroke', STATE.running.color);
    sc.nodes.forEach(function (n) {
      var e = deskMarkEls[n.id];
      if (!e) return;
      if (n.id === 'verif' || n.id === 'results') return;
      var st = STATE[n.state] || STATE.idle;
      var col = n.id === 'm-read' ? IVORY : st.color;
      if (n.id === 'm-read' && n.state === 'waiting') col = STATE.waiting.color;
      e.shape.setAttribute('fill', col);
      e.glow.setAttribute('fill', col);
      e.glow.setAttribute('opacity', n.live ? '0.3' : '0.14');
      if (e.kind === 'dot') e.shape.setAttribute('fill', col);
    });
  }
  buildDeskMarks();
  var NO_DRAW = new Proxy({}, { get: function () { return function () {}; }, set: function () { return true; } });
  // Round 10g: ?nocolor on the Now frame turns the live text and marks neutral (the art's own links stay raster).
  if (/[?&]nocolor/.test(location.search)) document.body.classList.add('nocolor');
  function fitFrame() {
    var mission = document.body.classList.contains('frame-mission'), shared = document.body.classList.contains('frame-shared');
    var w = 1296, h = 729;
    if (mission || shared) { w = mission ? 1244 : 1382; h = (mission ? 829 : 922) + 26; }
    var k = Math.min(window.innerWidth / w, window.innerHeight / h);
    document.documentElement.style.setProperty('--k', k.toFixed(4));
  }
  var nowStage = makeStage($('#now-stage'), {
    onPick: function (id, kind) {
      if (isNarrow()) { if (kind === 'mission') openDetail(id); else openList(); return; }
      if (kind === 'project') location.hash = '#/now/' + id;
      else location.hash = '#/mission/' + id;
    }
  });
  var phoneStage = makeStage($('#phone-stage'), {
    onPick: function (id) { openSheet(id); }
  });

  function zoomTo(id) {
    var p = nowStage.scene.projects.filter(function (x) { return x.id === id; })[0];
    if (!p) return;
    var cx = 0, cy = 0, n = 0;
    nowStage.scene.nodes.forEach(function (x) { if (p.members.indexOf(x.id) >= 0) { cx += x.x; cy += x.y; n++; } });
    nowStage.setFocus({ x: cx / n, y: cy / n, zoom: 1.9 });
    $('#now-overview').hidden = false;
    $$('#rail-projects a').forEach(function (a) { a.classList.toggle('on', a.getAttribute('data-proj') === id); });
    say('Zoomed into ' + p.name + '. Whole space returns you.');
  }

  function renderRail() {
    $('#rail-projects').innerHTML = projects.map(function (p) {
      var n = missions.filter(function (m) { return m.project === p.id; }).length;
      return '<li><a href="#/now/' + p.id + '" data-proj="' + p.id + '" style="--hue:' + p.hue + '">' +
        '<span class="pdot" aria-hidden="true"></span>' + esc(p.name) + '<span class="cnt">' + n + '</span></a></li>';
    }).join('');
    $('#sh-projects').innerHTML = projects.map(function (p) {
      return '<li><a href="#/now/' + p.id + '"' + (p.id === 'archeus' ? ' aria-current="page"' : '') + '>' + esc(p.name) + '</a></li>';
    }).join('');
    $$('#rail-projects a').forEach(function (a) {
      var id = a.getAttribute('data-proj');
      a.addEventListener('pointerenter', function () { if (!$('#s-now').hidden) nowStage.setHover(id); });
      a.addEventListener('pointerleave', function () { if (!$('#s-now').hidden) nowStage.setHover(null); });
      a.addEventListener('focus', function () { if (!$('#s-now').hidden) nowStage.setHover(id); });
      a.addEventListener('blur', function () { if (!$('#s-now').hidden) nowStage.setHover(null); });
    });
  }

  function renderNow(pid) {
    $('#s-now [data-sentence]').textContent = sentence();
    if (ovMode()) buildOverview(); else nowStage.setScene(nowScene);
    renderMoreChips();
    renderNeeds();
    $('#now-overview').hidden = true;
    $$('#rail-projects a').forEach(function (a) { a.classList.remove('on'); });
    $('#now-list').innerHTML = sorted(missions).map(function (m) {
      return '<li><a href="#/mission/' + m.id + '">' + esc(m.title) + '</a>' +
        '<span class="row-meta">' + esc(projectOf(m.project).name) + ' · ' + esc(m.branch) + '</span>' +
        '<span class="row-state st-' + m.state + '">' + esc(stateLine(m)) + '</span>' +
        (m.state === 'waiting' ? '<a class="btn review" href="#/plan/' + m.id + '">Review plan</a>' : '') + '</li>';
    }).join('');
    if (pid === 'chat') setTimeout(function () { $('#chat-input').focus({ preventScroll: true }); }, 0);
    else if (pid && projectOf(pid)) zoomTo(pid);
  }

  // Round 10c frames (Mission 03, Shared 06): the concept raster is the base art; the text sits at the solved layout
  // (layout-r10c.js), and marks and the phase stepper are drawn on top. One frame each, desktop only.
  var R10C = window.R10C_LAYOUT || {};
  function placeFrame(root, layout) {
    $$('[data-f]', root).forEach(function (el) {
      var L = layout[el.getAttribute('data-f')];
      if (!L) return;
      el.classList.add(L.f === 'sans' ? 'sans' : 'serif');
      el.style.left = (L.x + (L.dx || 0)) + 'px';
      el.style.top = (L.y + (L.dy || 0)) + 'px';
      el.style.fontSize = L.s + 'px';
      el.style.letterSpacing = L.t + 'px';
    });
  }
  function fset(id, text) { var el = $('#m-frame [data-f="' + id + '"]'); if (el) el.textContent = text; }

  // The mission frame is the concept's Fix date test chain, so the view always shows that mission.
  function renderMission(id) {
    var m = find('m-date'), sec = $('#s-mission'), p = projectOf(m.project);
    missionShown = m.id;
    $('#m-note').textContent = id && id !== 'm-date' ? 'The mission frame shows Fix date test, the concept fixture.' : '';
    $('#m-replay').href = '#/replay/' + m.id;
    fset('crumb_ar', p.name);
    fset('crumb_fx', m.title);
    $('#m-frame [data-m-title]').textContent = m.title;
    fset('mis_title', m.title);
    fset('mis_proj', 'Project: ' + p.name);
    fset('mis_branch', 'Branch: ' + m.branch);
    fset('f_proj_v', p.name);
    fset('f_branch_v', m.branch);
    var st = $('#m-frame [data-f="f_status_v"]');
    st.textContent = m.state === 'running' ? 'In progress' : stateLine(m);
    st.style.color = STATE[m.state].color;
    phases(m);
    renderMissionPanel();
  }

  // Six phases: a label each (the stepper line and marks are drawn in #m-stepper).
  function phases(m) {
    var ol = $('#m-phases');
    ol.innerHTML = PHASES.map(function (name, i) {
      var cls = '';
      if (m.phase === 6 || i < m.phase) cls = 'done';
      else if (i === m.phase) cls = m.state === 'waiting' ? 'wait' : 'current';
      var word = cls === 'done' ? 'done' : cls === 'wait' ? 'waiting for you' : cls === 'current' ? 'current' : 'not reached';
      return '<li class="' + cls + '" data-f="ph_' + (i + 1) + '">' + name + '<span class="sr-only">, ' + word + '</span></li>';
    }).join('');
    placeFrame(ol, R10C.mission);
    var xs = [837, 911.5, 981, 1050.5, 1119.5, 1195], y = 231.5, ph = m.phase === 6 ? 6 : m.phase, out = '';
    for (var i = 0; i < 5; i++) {
      var seg = i + 1 <= ph ? STATE.connected.color : i === ph ? STATE.running.color : STATE.done.color;
      out += '<line x1="' + xs[i] + '" y1="' + y + '" x2="' + xs[i + 1] + '" y2="' + y + '" stroke="' + seg + '" stroke-width="1.6" opacity="' + (i + 1 <= ph ? 0.7 : 0.35) + '"/>';
    }
    xs.forEach(function (x, i) {
      if (i < ph) {
        out += '<circle cx="' + x + '" cy="' + y + '" r="8" fill="' + STATE.connected.color + '"/>' +
          '<path d="M' + (x - 3.6) + ' ' + y + ' L' + (x - 1) + ' ' + (y + 2.6) + ' L' + (x + 3.8) + ' ' + (y - 3) + '" fill="none" stroke="#0E131C" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>';
      } else if (i === ph && ph < 6) {
        var col = m.state === 'waiting' ? STATE.waiting.color : STATE.running.color;
        out += '<circle cx="' + x + '" cy="' + y + '" r="9" fill="none" stroke="' + col + '" stroke-width="2"/>' +
          '<circle cx="' + x + '" cy="' + y + '" r="4.5" fill="' + col + '"/>';
      } else {
        out += '<circle cx="' + x + '" cy="' + y + '" r="7.5" fill="none" stroke="' + STATE.done.color + '" stroke-width="1.4"/>';
      }
    });
    $('#m-stepper').innerHTML = out;
  }

  function renderMissionPanel() {
    var m = find(missionShown), sec = $('#s-mission'), p = plans[m.id];
    fset('p_name', m.phase < 0 ? 'Not started' : m.phase === 6 ? 'Complete' : PHASES[m.phase]);
    fset('a_name', m.exec ? 'Codex · execution' : 'No agent recorded');
    fset('a_sub', m.exec ? 'Runs checks, collects evidence, reports results.' : 'Nothing is running for this mission.');
    fset('t_name', m.taskName || m.task);
    var parts = m.taskName ? m.task.split(' and ') : [];
    fset('t_s1', parts[0] || '');
    fset('t_s2', parts[1] ? 'and ' + parts[1] : '');
    fset('r_name', m.latest);
    fset('r_sub', m.latestSub || '');
    var log = $('#m-log');
    log.innerHTML = m.log.map(function (l, i) {
      return '<li' + (/Not passed/.test(l) ? ' class="bad"' : '') + ' data-f="l_' + (i + 1) + '">' + esc(l) + '</li>';
    }).join('');
    placeFrame(log, R10C.mission);
    var steps = m.steps || (p ? p.tasks.map(function (t) { return [t.text, '']; }) : []);
    var stepsEl = $('#m-steps');
    stepsEl.innerHTML = steps.map(function (s, i) {
      return '<li class="' + s[1] + '" data-f="s_' + (i + 1) + '">' + esc(s[0]) + '</li>';
    }).join('');
    placeFrame(stepsEl, R10C.mission);
    var plan = $('#m-plan', sec);
    plan.hidden = !p;
    plan.href = '#/plan/' + m.id;
  }

  /* ---------- Replay (round 10c replay): as-of inspection, static, no motion ---------- */
  // Desktop: the concept's own frame, 1440 x 810 master px, scaled uniformly by --k (body.frame-replay). The base
  // art (art/replay-base.webp, tools/art_replay.py) is the concept with every live item removed, so the star, the
  // links, the polyhedra and their glyphs are raster. Live here: labels, the mission node (state colour), rows,
  // chips, markers, buttons and the rail. Phone: a crop of the same art above the rows (no concept exists).
  var RP_MASTER = { w: 1440, h: 810 };
  var RP_GRAPH = { x0: 236, y0: 40, w: 464, h: 730 };
  // Label ink top-left in master px (concept measurement, tools/textfit_replay.py).
  var RP_LABEL = {
    core: [446, 170], orchestrates: [497, 241], fix: [436, 352], verifying: [447, 379],
    executes: [372, 428], verifies: [550, 428], produces: [460, 590], codex: [312, 579],
    execution: [303, 601], verification: [584, 591], results: [459, 736]
  };
  // Row geometry (master px): card top and height; ink tops of time, title, sub, chip and the marker centre.
  var RP_ROWS_GEOM = [
    { top: 158, h: 77, time: 188, title: 176, sub: 206, chip: 169, mark: 194, chipX: 1303, chipW: 88 },
    { top: 244, h: 77, time: 275, title: 264, sub: 293, chip: 256, mark: 281, chipX: 1303, chipW: 88 },
    { top: 330, h: 77, time: 361, title: 349, sub: 379, chip: 343, mark: 368, chipX: 1303, chipW: 88 },
    { top: 417, h: 79, time: 449, title: 438, sub: 466, chip: 430, mark: 455, chipX: 1299, chipW: 92 },
    { top: 505, h: 81, time: 537, title: 526, sub: 555, chip: 519, mark: 543, chipX: 1299, chipW: 92 },
    { top: 601, h: 108, title: 620, chip: 614, mark: 637, chipX: 1303, chipW: 88 }
  ];
  var REPLAY = {
    'm-date': [
      { time: '09:00', title: 'Task initiated', sub: 'Scope, authority and starting state captured', badge: 'Intended', tone: 'intended', mark: 'dot' },
      { time: '09:12', title: 'Files changed', sub: 'Changes and resulting artifacts linked to the task', badge: 'Recorded', tone: 'recorded', mark: 'dot' },
      { time: '09:18', title: 'Tests passed', sub: 'Validation evidence recorded', badge: 'Verified', tone: 'verified', mark: 'check' },
      { time: '09:24', title: 'External response lost', sub: 'Side effect classified as uncertain', badge: 'Uncertain', tone: 'uncertain', mark: 'diamond' },
      { time: '09:25', title: 'Workflow suspended', sub: 'No unsafe retry. Operator reconciliation required.', badge: 'Needs you', tone: 'needs-you', mark: 'diamond' }
    ]
  };
  var replayId = 'm-date';

  // Stage map: desktop is master px; phone maps the graph crop (RP_GRAPH) into the stage width.
  function rpMap() {
    if (!isNarrow()) return { s: 1, ox: 0, oy: 0, px: 0 };
    var W = $('#replay-stage').clientWidth || 360;
    var s = Math.min(W / RP_GRAPH.w, 420 / RP_GRAPH.h);
    return { s: s, ox: RP_GRAPH.x0, oy: RP_GRAPH.y0, px: (W - RP_GRAPH.w * s) / 2 };
  }
  function rpPos(g, x, y) { return [g.px + (x - g.ox) * g.s, (y - g.oy) * g.s]; }
  function rpCss(p) { return 'left:' + p[0].toFixed(1) + 'px;top:' + p[1].toFixed(1) + 'px'; }

  function renderReplayStage(m) {
    var root = $('#replay-stage'), L = $('#rc-labels');
    var g = rpMap(), st = STATE[m.state] || STATE.idle;
    var art = root.querySelector('.rc-art');
    if (isNarrow()) {
      if (!art) { art = document.createElement('div'); art.className = 'rc-art'; root.insertBefore(art, root.firstChild); }
      art.style.width = (RP_MASTER.w * g.s) + 'px';
      art.style.height = (RP_MASTER.h * g.s) + 'px';
      art.style.left = (g.px - RP_GRAPH.x0 * g.s) + 'px';
      art.style.top = (-RP_GRAPH.y0 * g.s) + 'px';
      root.style.height = (RP_GRAPH.h * g.s) + 'px';
    } else {
      if (art) art.remove();
      root.style.height = '';
    }
    var vb = isNarrow() ? [RP_GRAPH.x0, RP_GRAPH.y0, RP_GRAPH.w, RP_GRAPH.h].join(' ') : '0 0 1440 810';
    var svg = '<svg class="rc-svg" viewBox="' + vb + '" aria-hidden="true">' +
      '<circle class="rc-node" cx="488" cy="328" r="12.5" style="fill:' + st.color + '"/></svg>';
    var old = root.querySelector('.rc-svg');
    if (old) old.remove();
    root.insertAdjacentHTML('afterbegin', svg);
    // Hit areas are at least 44 CSS px: in master px on the desktop frame (44 / --k), in stage px on the phone.
    var kk = isNarrow() ? 1 : (parseFloat(document.documentElement.style.getPropertyValue('--k')) || 1);
    var hs = isNarrow() ? 44 : 44 / kk;
    var hit = function (c, w, h, href, label) {
      return '<a class="rc-hit" href="' + href + '" aria-label="' + label + '" style="left:' + (c[0] - w / 2).toFixed(1) + 'px;top:' + (c[1] - h / 2).toFixed(1) + 'px;width:' + w.toFixed(1) + 'px;height:' + h.toFixed(1) + 'px"></a>';
    };
    var mp = rpPos(g, 488, 328), fp = rpPos(g, RP_LABEL.fix[0] + 50, RP_LABEL.fix[1] + 9);
    var lab = hit(mp, hs, hs, '#/mission/' + m.id, esc(m.title) + ': open the mission');
    lab += hit(fp, hs * 3, hs, '#/mission/' + m.id, esc(m.title) + ': open the mission');
    var put = function (k, html, cls) { return '<p class="rc-l rk-' + k + ' ' + (cls || '') + '" style="' + rpCss(rpPos(g, RP_LABEL[k][0], RP_LABEL[k][1])) + '">' + html + '</p>'; };
    lab += put('core', 'Archeus', 'rc-core');
    lab += put('fix', esc(m.title), 'rc-mission-name');
    lab += put('verifying', '<span class="rc-state" style="color:' + st.color + '">' + esc(m.stateText) + '</span>', 'rc-mission-state');
    lab += put('orchestrates', 'orchestrates', 'rc-verb');
    if (m.id === 'm-date') {
      lab += put('executes', 'executes', 'rc-verb') + put('verifies', 'verifies', 'rc-verb') + put('produces', 'produces', 'rc-verb');
      lab += put('codex', 'Codex', 'rc-name') + put('execution', 'execution', 'rc-sub');
      lab += put('verification', 'Verification', 'rc-name') + put('results', 'Results', 'rc-name');
    }
    L.innerHTML = lab;
    root.setAttribute('aria-label', 'Constellation for ' + m.title + ': Archeus, the mission' + (m.id === 'm-date' ? ', Codex execution, Verification and Results' : ''));
  }

  function rowHtml(r, g) {
    return '<li class="rp-row rs-' + r.mark + ' tone-' + r.tone + '" style="--top:' + g.top + 'px;--h:' + g.h + 'px">' +
      '<span class="rp-mark" aria-hidden="true" style="--y:' + g.mark + 'px"></span>' +
      '<span class="rp-time" style="--y:' + g.time + 'px">' + r.time + '</span>' +
      '<span class="rp-body"><span class="rp-title" style="--y:' + g.title + 'px">' + esc(r.title) + '</span><span class="rp-sub" style="--y:' + g.sub + 'px">' + esc(r.sub) + '</span></span>' +
      '<span class="rp-badge" style="--y:' + g.chip + 'px;--x:' + g.chipX + 'px;--w:' + g.chipW + 'px">' + esc(r.badge) + '</span></li>';
  }

  function renderReplay(id) {
    var m = find(id) || find('m-date'), rows = REPLAY[m.id] || [];
    replayId = m.id;
    $('#rp-title').textContent = 'Replay · ' + m.title;
    var list = rows.map(function (r, i) { return rowHtml(r, RP_ROWS_GEOM[i]); });
    if (!rows.length) list.push('<li class="rp-row rp-empty" style="--top:158px;--h:77px"><span class="rp-sub" style="--y:176px">No replay is recorded for this mission in the prototype. Sample data exists for Fix date test only.</span></li>');
    var rc = RP_ROWS_GEOM[RP_ROWS_GEOM.length - 1];
    list.push('<li class="rp-row rp-reconcile" style="--top:' + rc.top + 'px;--h:' + rc.h + 'px">' +
      '<span class="rp-mark" aria-hidden="true" style="--y:' + rc.mark + 'px"></span>' +
      '<span class="rp-body"><span class="rp-title" style="--y:' + rc.title + 'px">Reconcile</span>' +
      '<span class="rp-actions"><button type="button" class="btn primary" data-act="reconcile">Reconcile</button><a class="btn" href="#/mission/' + m.id + '">Open evidence</a></span></span>' +
      '<span class="rp-badge" style="--y:' + rc.chip + 'px;--x:' + rc.chipX + 'px;--w:' + rc.chipW + 'px">Operator</span></li>');
    $('#rp-rows').innerHTML = list.join('');
    fitReplayFrame();
    renderReplayStage(m);
  }

  // The frame class and scale follow the active screen: desktop Replay is one fixed 1440 x 810 frame plus a footer strip.
  function fitReplayFrame() {
    var on = !isNarrow() && !$('#s-replay').hidden;
    document.body.classList.toggle('frame-replay', on);
    if (!on) return;
    var k = Math.min(window.innerWidth / RP_MASTER.w, window.innerHeight / (RP_MASTER.h + 26));
    document.documentElement.style.setProperty('--k', k.toFixed(4));
  }
  window.addEventListener('resize', function () {
    if (!$('#s-replay').hidden) { fitReplayFrame(); renderReplayStage(find(replayId)); }
  });

  function renderShared() {
    renderSharedPanel();
  }

  function renderSharedPanel() {
    $$('[data-stab]').forEach(function (b) { b.setAttribute('aria-selected', String(b.getAttribute('data-stab') === sharedTab)); });
    var box = $('#s-panel');
    $('#sh-kv').classList.toggle('off', sharedTab !== 'overview');
    box.hidden = sharedTab === 'overview';
    if (sharedTab === 'content') {
      box.innerHTML = '<ul class="rowlist"><li><span>Project files</span><span>12 items</span></li><li><span>Notes</span><span>34 items</span></li><li><span>Agent logs</span><span>28 items</span></li><li><span>Build outputs</span><span>18 items</span></li><li><span>Related content</span><span>156 items</span></li></ul><p class="small">Fixture counts. The same records, device permissions apply.</p>';
    } else if (sharedTab === 'relations') {
      box.innerHTML = '<ul class="rowlist">' + projects.map(function (p) {
        var n = missions.filter(function (m) { return m.project === p.id; }).length;
        return '<li><span>' + esc(p.name) + '</span><span>orchestrated, ' + n + ' missions</span></li>';
      }).join('') + '</ul><p class="small">Relations are fixture text. Core supplies the real ones.</p>';
    }
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
      '<p><span class="lbl-line">What</span><br>' + esc(m.what) + '</p>' +
      '<p><span class="lbl-line">Why</span><br>' + esc(why) + '</p>' +
      '<p><span class="lbl-line">Core (fixture text)</span><br>' + esc(consequence) + '</p>' +
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
    var line = waiting.length ? 'Waiting for you: ' + waiting.map(function (m) { return m.title; }).join(', ') + '.' : 'Nothing waiting for you.';
    var sc = null;
    phoneStage.setScene(function (w, h) { sc = phoneScene(w, h); return sc; });
    if (sc && sc.overflow > 0) line += ' ' + sc.overflow + ' more on Overview.';
    $('[data-phone-line]').textContent = line;
  }

  function renderPlan(id) {
    var m = find(id) || find('m-search');
    if (planId !== m.id) planOpened = false;
    planId = m.id;
    var p = plans[m.id], sec = $('#s-plan');
    var sheetOn = ovMode() && !planOpened && m.id === 'm-search' && !!plans[m.id];
    sec.classList.toggle('sheet-on', sheetOn);
    if (sheetOn) buildPhone2();
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
    $('[data-plan-why]', sec).textContent = 'Why: ' + p.why + ' Action ' + p.hash.slice(0, 9) + ' · plan v' + p.version + ' (fixture).';
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
            '> Carry in request changes</label> ' + esc(c.body) + '</li>';
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
    renderPlanStep(m, p);
  }

  // Decision, step 2 of 2: a confirm screen with the action hash and plan version; the box it opens is the explicit confirm.
  function renderPlanStep(m, p) {
    var review = $('#plan-review'), conf = $('#plan-confirm');
    review.hidden = planStep === 'confirm';
    conf.hidden = planStep !== 'confirm';
    $('#s-plan > header.head').hidden = planStep === 'confirm';
    if (planStep !== 'confirm') { conf.innerHTML = ''; return; }
    conf.innerHTML = '<p class="kicker">Confirm approval · step 2 of 2</p>' +
      '<h1 tabindex="-1" data-plan-confirm-title>Approve plan v' + p.version + '?</h1>' +
      '<dl class="kv decision-facts"><dt>Mission</dt><dd>' + esc(m.title) + '</dd>' +
      '<dt>Project</dt><dd>' + esc(projectOf(m.project).name) + ' · ' + esc(m.branch) + '</dd>' +
      '<dt>Plan version</dt><dd>v' + p.version + ' (fixture)</dd>' +
      '<dt>Action hash</dt><dd class="hash">' + esc(p.hash) + '</dd></dl>' +
      '<p class="small">' + esc(p.approve) + ' Nothing is approved until you confirm in the box that opens next. Cancel is the default.</p>' +
      '<div class="row"><button type="button" class="btn primary" data-act="decide" data-kind="approve-confirm">Approve plan v' + p.version + '…</button>' +
      '<button type="button" class="btn" data-act="plan-back">Back to decision</button></div>';
    conf.querySelector('h1').focus({ preventScroll: true });
  }

  function confirmBox(title, text, ok, apply) {
    $('#confirm-title').textContent = title;
    $('#confirm-text').textContent = text;
    pendingOk = ok;
    pendingApply = apply || null;
    $('#confirm').showModal();
  }

  $('#confirm').addEventListener('close', function () {
    var apply = pendingApply;
    pendingApply = null;
    if (this.returnValue === 'ok') {
      if (apply) apply();
      if (pendingOk) say(pendingOk);
    }
    pendingOk = '';
  });

  function decide(kind) {
    var m = find(planId), p = plans[m.id];
    var note = $('#plan-note').value.trim();
    var sel = selectedComments();
    if (kind === 'approve') { planStep = 'confirm'; return renderPlan(planId); }
    if (kind === 'approve-confirm') {
      return confirmBox('Approve plan v' + p.version + '?',
        'Approve plan v' + p.version + ' (action ' + p.hash.slice(0, 9) + ') for "' + m.title + '" on ' + m.branch + '. ' + p.approve + ' Open comments: ' + commentsFor(m.id).length + ', which do not block approve.',
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

  /* ---------- Chat bar: scripted and simulated. No model call, nothing sent to Core. ---------- */

  var thread = $('#msgs');
  var PROMPTS = [
    'Start a project called Atlas',
    'Add a mission "Draft the brief" to Atlas',
    'Add an idea "Offline capture" to Atlas',
    'Make a plan for the brief',
    'Run the notes index',
    'Change the daily spend limit to 20 EUR',
    'What is a replay?'
  ];

  // On the phone, a Start card from the last few messages stays in view; otherwise the thread follows the newest line.
  function scrollThread() {
    var t = $('.feed'), kids = thread.children, cards = thread.querySelectorAll('.msg-card');
    if (isNarrow() && cards.length) {
      var card = cards[cards.length - 1];
      if (Array.prototype.indexOf.call(kids, card) >= kids.length - 3) {
        t.scrollTop += card.getBoundingClientRect().top - t.getBoundingClientRect().top - 8;
        return;
      }
    }
    t.scrollTop = t.scrollHeight;
  }
  function addMsg(kind, html) {
    var li = document.createElement('li');
    li.className = 'msg msg-' + kind;
    li.setAttribute('data-who', kind === 'you' ? 'You' : 'Archeus');
    li.innerHTML = html;
    thread.appendChild(li);
    scrollThread();
    return li;
  }
  function lead(text) { return addMsg('arch', '<p>' + esc(text) + '</p>'); }
  function receipts(list) {
    return '<p class="receipts">' + list.map(function (r) { return '<a class="receipt" href="' + r.href + '">' + esc(r.label) + '</a>'; }).join('') + '</p>';
  }
  function quoted(text, fallback) {
    var m = text.match(/["“”‘’']([^"“”‘’']{2,80})["“”‘’']/);
    return m ? m[1].trim() : fallback;
  }
  function slug(s) { return s.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 24); }

  // Each change to the constellation goes through here: data first, then one relayout; new objects grow in.
  function refreshNow() { nowStage.relayout(); buildOverview(); renderRail(); renderMoreChips(); renderNeeds(); }

  function createAtlas() {
    projects.push({ id: 'atlas', name: 'Atlas', hue: '#D9C7A0', at: [0.46, 0.36], offs: [[30, -110], [-40, 110], [96, 70]] });
    nowStage.markBorn('atlas');
    nowStage.markBorn('core>atlas');
    refreshNow();
  }

  function newMission(title, idea) {
    counter++;
    var m = { id: 'm-new-' + counter, title: title, project: 'atlas', branch: 'feat/' + slug(title), state: 'idle', stateText: idea ? 'Idea' : 'Not started', phase: -1, glyph: idea ? 'list' : 'doc', what: title + '.', latest: 'none recorded', task: 'none', exec: false, related: [], log: ['Created from the chat (simulated).'] };
    missions.push(m);
    nowStage.markBorn('atlas>' + m.id);
    nowStage.markBorn(m.id);
    refreshNow();
    return m;
  }

  function makePlan(m) {
    plans[m.id] = {
      version: 1,
      hash: 'c2f8 1a6e 4b9e 8f15 6a0c d4e7',
      why: 'Plan approval required.',
      tasks: [
        { key: 't1', text: 'Read the brief and list the open questions.' },
        { key: 't2', text: 'Draft the outline and keep the sources linked.' },
        { key: 't3', text: 'Check the outline against the success criteria.' }
      ],
      approve: 'Approving starts the run of 3 tasks on ' + m.branch + '.',
      request: 'Sends the mission back to the planner with your note and the selected comments. Approval of v1 ends.',
      reject: 'Cancels the mission. A decided approval cannot be changed. No undo.'
    };
    m.state = 'waiting'; m.stateText = 'Plan ready · review'; m.phase = 2;
    m.latest = 'Plan v1 recorded, 3 tasks.';
    m.log.push('Plan v1 recorded, waiting for your decision.');
    refreshNow();
  }

  // A proposed effect: shown as a card, never run until the owner confirms the card.
  function proposal(title, effect, done, apply) {
    var li = addMsg('card', '<p class="card-k">Proposed · not run</p><p class="card-t">' + esc(title) + '</p><p class="small">' + esc(effect) + '</p>' +
      '<div class="row"><button type="button" class="btn primary" data-card="approve">Approve…</button><button type="button" class="btn" data-card="dismiss">Dismiss</button></div>');
    li.querySelector('[data-card="approve"]').addEventListener('click', function () {
      confirmBox(title + '?', effect + ' Explicit approval only. Cancel is the default.', done, function () {
        apply();
        li.innerHTML = '<p class="card-k">Approved · simulated</p><p class="card-t">' + esc(title) + '</p><p class="small">' + esc(done) + '</p>';
      });
    });
    li.querySelector('[data-card="dismiss"]').addEventListener('click', function () {
      li.innerHTML = '<p class="card-k">Dismissed · nothing done</p><p class="card-t">' + esc(title) + '</p>';
    });
  }

  // A chat-created mission waits for the owner: Start (plans it for review) or Keep as mission.
  function startCard(m) {
    var li = addMsg('card', '<div class="card-body"><p class="card-t">Start and plan ' + esc(m.title) + '?</p>' +
      '<div class="row"><button type="button" class="btn" data-card="start">Start</button><button type="button" class="btn" data-card="keep">Keep as mission</button></div></div>');
    li.querySelector('[data-card="start"]').addEventListener('click', function () {
      makePlan(m);
      li.innerHTML = '<p class="card-k">Started · simulated</p><p class="card-t">' + esc(m.title) + '</p><p class="small">Plan v1 is ready for your review. Nothing ran.</p>';
    });
    li.querySelector('[data-card="keep"]').addEventListener('click', function () {
      li.innerHTML = '<p class="card-k">Kept as mission</p><p class="card-t">' + esc(m.title) + '</p><p class="small">Not started.</p>';
    });
  }

  // Not about a project: its own thread, never project memory unless the owner promotes it.
  function general(body) {
    addMsg('gen', '<p class="gen-k"><span class="gen-tag">General</span> not project memory</p><p>' + esc(body) + '</p>' +
      '<label class="promote"><span>Promote to project memory</span><input type="checkbox" data-promote aria-describedby="promote-note"></label>' +
      '<span class="sr-only" id="promote-note">Off: this answer stays in the general thread.</span>');
  }

  function reply(text) {
    var t = text.toLowerCase();
    var question = /^(what|why|how|who|when|where|which|is|are|does|do|can)\b/.test(t) && !/\b(create|add|start|make|run|change|set|plan|send|spend)\b/.test(t);
    if (question) return /replay|recover|reconcil|checkpoint/.test(t) ? general('A replay shows what an agent intended, what you authorized, what was durably recorded, what may have taken effect, and where state is uncertain. Recovery restores a checkpoint and never claims that every external effect can be undone.') : general('This is not about a project, so it stays in the general thread. The prototype answers with fixed text. A real build answers through the official CLI on your chosen account. Nothing here reaches project memory unless you promote it.');
    if (/\b(spend|budget|limit|setting|settings|hook|hooks|account|accounts|token|tokens|billing)\b/.test(t)) {
      lead('That changes a setting, so I have proposed it. Nothing changes until you approve.');
      return proposal('Change the daily spend limit to 20 EUR', 'Core records a new limit for every project. This change spends nothing by itself. The prototype reads no tokens. Design rule: Archeus never touches tokens (V1 code conflict open, see design doc round 4).', 'Recorded as approved (simulated). No setting changed in this prototype.', function () {});
    }
    if (/\b(run|index|rerun|re-run)\b/.test(t)) {
      var idx = find('m-index');
      if (idx.state === 'running') return lead('Index notes is already running. Nothing was started.');
      lead('Running work has an effect, so I have proposed it. Design rule: it starts only after you approve (V1 today starts mission work without a card, see round 4).');
      return proposal('Run Index notes', 'Runs the indexer on the notes folder. Uses model time on your configured account through the official CLI.', 'Index notes is running (simulated).', function () {
        idx.state = 'running'; idx.stateText = 'Indexing'; idx.phase = 3;
        idx.latest = 'Started after your approval (simulated).';
        idx.log.push('Started from the chat after your approval (simulated).');
        refreshNow();
      });
    }
    if (/\bplan\b/.test(t)) {
      var target = missions.filter(function (m) { return m.project === 'atlas' && m.id.indexOf('m-new-') === 0 && !plans[m.id] && m.glyph !== 'list'; }).pop();
      if (!target) return lead('No mission in Atlas is waiting for a plan. Add a mission first. Nothing was planned.');
      makePlan(target);
      return addMsg('arch', '<p>Plan v1 for "' + esc(target.title) + '" has 3 steps (simulated). It waits for your review. Nothing starts until you approve.</p>' + receipts([{ label: 'Review plan v1', href: '#/plan/' + target.id }]));
    }
    if (/\bidea\b/.test(t)) {
      if (!projectOf('atlas')) return lead('Create project Atlas first. Nothing was added.');
      var idea = newMission(quoted(text, 'Offline capture'), true);
      return addMsg('arch', '<p>Recorded the idea "' + esc(idea.title) + '" in Atlas. It is an idle figure until you make it a mission.</p>' + receipts([{ label: 'Idea: ' + idea.title, href: '#/mission/' + idea.id }]));
    }
    if (/\bmission\b/.test(t)) {
      if (!projectOf('atlas')) return lead('Create project Atlas first. Nothing was added.');
      var mis = newMission(quoted(text, 'Draft the brief'), false);
      addMsg('arch', '<p>Mission created in Atlas (simulated). Start it when you like.</p>' + receipts([{ label: 'Mission: ' + mis.title, href: '#/mission/' + mis.id }]));
      return startCard(mis);
    }
    if (/\b(atlas|project)\b/.test(t)) {
      if (projectOf('atlas')) return lead('Atlas already exists. Ask for a mission or an idea in it.');
      createAtlas();
      return addMsg('arch', '<p>Created project Atlas (simulated, V1 has no chat path for projects). Its star is in the constellation, with no missions yet.</p>' + receipts([{ label: 'Project Atlas', href: '#/now/atlas' }]));
    }
    general('This does not change a project, so it stays in the general thread. The prototype answers with fixed text for a few questions. A real build answers through the official CLI on your chosen account.');
  }

  function ask(text) {
    var clean = text.trim().slice(0, 300);
    if (!clean) return;
    addMsg('you', '<p>' + esc(clean) + '</p>');
    var typing = addMsg('typing', '<p>Archeus is composing. Simulated, no model call.</p>');
    setTimeout(function () { typing.remove(); reply(clean); }, 650);
  }

  $('#chat-prompts').innerHTML = PROMPTS.map(function (p) {
    return '<button type="button" class="prompt" data-prompt="' + esc(p) + '">' + esc(p) + '</button>';
  }).join('');
  addMsg('you', '<p>Open a mission in Notes: <br>Export backup</p>');
  addMsg('arch', '<p>Mission created in Notes. <br>Start it when you like.</p>');
  startCard(find('m-read'));
  addMsg('you', '<p>What does exit code 137 mean?</p>');
  general('The process was killed, usually out of memory (128 + signal 9).');
  // The phone-3 fixture (exit code 137 and its General answer) is not on the desktop concept: the desktop frame hides it.
  Array.prototype.slice.call(thread.children).slice(3).forEach(function (el) { el.classList.add('phone-fixture'); });

  document.addEventListener('submit', function (e) {
    if (e.target.id === 'ph2-chat') {
      e.preventDefault();
      var typed = $('#ph2-input').value.trim();
      if (!typed) return say('Write something first.');
      $('#ph2-input').value = '';
      location.hash = '#/now';
      ask(typed);
      return setPhoneFrame(3);
    }
    if (e.target.id !== 'chat-form') return;
    e.preventDefault();
    var input = $('#chat-input');
    var text = input.value.trim();
    if (!text) return say('Write something first.');
    input.value = '';
    ask(text);
  });

  document.addEventListener('click', function (e) {
    var p = e.target.closest('[data-prompt]');
    if (p) ask(p.getAttribute('data-prompt'));
  });

  document.addEventListener('change', function (e) {
    if (!e.target.hasAttribute('data-promote')) return;
    var on = e.target.checked;
    say(on ? 'Promoted to Harbor memory (simulated). Nothing was saved to Core.' : 'Promotion withdrawn. Nothing was saved.');
  });

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
    if (e.target.id === 'now-overview') {
      nowStage.setFocus(null);
      e.target.hidden = true;
      $$('#rail-projects a').forEach(function (a) { a.classList.remove('on'); });
      location.hash = '#/now';
      return say('Whole space.');
    }
    var stab = e.target.closest('[data-stab]');
    if (stab) { sharedTab = stab.getAttribute('data-stab'); return renderSharedPanel(); }
    var el = e.target.closest('[data-act]');
    if (!el) return;
    var act = el.getAttribute('data-act');
    if (act === 'close-sheet') closeSheet(false);
    else if (act === 'decide') decide(el.getAttribute('data-kind'));
    else if (act === 'plan-back') { planStep = 'review'; renderPlan(planId); }
    else if (act === 'stop') stop();
    else if (act === 'reconcile') confirmBox('Reconcile ' + find(replayId).title + '?', 'You record what you saw on the remote: did the push take effect? Core would store your answer with this replay. Nothing is pushed, retried or reversed here.', 'Prototype: nothing was reconciled. The suspension stays.');
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
    }
  });

  /* ---------- Phone: one calm Overview. Detail, lists and the conversation open as sheets. ---------- */

  function isNarrow() { return window.matchMedia('(max-width: 880px)').matches; }

  function sheetFor(html) {
    var box = $('#now-sheet');
    box.innerHTML = html;
    box.hidden = false;
    var h = box.querySelector('h2');
    if (h) h.focus({ preventScroll: true });
  }

  function closeNowSheet() { $('#now-sheet').hidden = true; $('#now-sheet').innerHTML = ''; }

  // Phone decision sheet (medium): Back, What, Why, Core consequence, one full-width Open decision.
  function openDetail(id) {
    var m = find(id);
    if (!m) return;
    var waiting = m.state === 'waiting', p = plans[m.id];
    sheetFor(
      '<button type="button" class="sheet-back" data-act="now-sheet-close">‹ Back</button>' +
      '<h2 id="now-sheet-h" tabindex="-1">' + esc(m.title) + '</h2>' +
      '<div class="sheet-line"><span class="lbl-line">What</span>' + esc(waiting ? 'Review plan' : m.what) + '</div>' +
      '<div class="sheet-line"><span class="lbl-line">Why</span>' + esc(waiting && p ? p.why : 'Status: ' + stateLine(m) + '.') + '</div>' +
      '<div class="sheet-line"><span class="lbl-line">Core consequence</span>' + esc(waiting && p ? p.approve : 'Core records this run. This prototype changes nothing.') + '</div>' +
      '<div class="sheet-actions">' +
      '<a class="btn decision" href="' + (waiting ? '#/plan/' : '#/mission/') + m.id + '">' + (waiting ? 'Open decision' : 'Open mission') + '</a></div>');
  }

  function openList() {
    // Every project is listed by name, with its missions under it (needs-you first).
    var rows = projects.map(function (p) {
      var items = sorted(missions.filter(function (m) { return m.project === p.id; })).map(function (m) {
        return '<li><button type="button" class="list-row" data-open="' + esc(m.id) + '"><span class="st-' + m.state + '">' + esc(STATE[m.state].word) + '</span> ' +
          esc(m.title) + '</button></li>';
      }).join('');
      return '<li class="list-group"><p class="kicker"><span class="pdot" style="--hue:' + p.hue + '"></span>' + esc(p.name) + '</p><ul>' + items + '</ul></li>';
    }).join('');
    sheetFor('<p class="kicker">All work</p><h2 id="now-sheet-h" tabindex="-1">' + projects.length + ' projects, ' + missions.length + ' missions</h2>' +
      '<ul class="rowlist-sheet list-groups">' + rows + '</ul>' +
      '<div class="sheet-actions"><button type="button" class="btn" data-act="now-sheet-close">Close</button></div>');
  }

  // The phone's first obligation: one Needs-you card, opened by one tap.
  function renderNeeds() {
    var box = $('#needs-card'), w = missions.filter(function (m) { return m.state === 'waiting'; })[0];
    if (!w || !isNarrow()) { box.hidden = true; return; }
    box.hidden = false;
    box.setAttribute('data-open', w.id);
    box.innerHTML = '<span class="needs-k">Needs you</span><span class="needs-t">' + esc(w.title) + '</span><span class="needs-r">Review</span>';
  }

  // Count chips replace the labels the phone scene does not show.
  function renderMoreChips() {
    var box = $('#more-chips');
    // The phone Overview draws its own chip inside the scene (overviewSvg). Past five projects, the farthest share one named list chip.
    if (!isNarrow() || ovMode()) { box.innerHTML = ''; return; }
    var rest = projects.length > 5 ? projects.slice(4) : [];
    var html = rest.length ? '<button type="button" class="chip-btn" data-act="open-list">' + esc(rest.map(function (p) { return p.name; }).join(', ')) + '</button>' : '';
    html += '<button type="button" class="chip-btn" data-act="open-list">All work · ' + missions.length + '</button>';
    box.innerHTML = html;
  }

  document.addEventListener('click', function (e) {
    var open = e.target.closest('[data-open]');
    if (open) { closeNowSheet(); return openDetail(open.getAttribute('data-open')); }
    var act = e.target.closest('[data-act]');
    if (!act) return;
    var name = act.getAttribute('data-act');
    if (name === 'menu') {
      var on = !document.body.classList.contains('menu-open');
      document.body.classList.toggle('menu-open', on);
      act.setAttribute('aria-expanded', String(on));
    } else if (name === 'open-list') openList();
    else if (name === 'now-sheet-close') closeNowSheet();
    else if (name === 'feed-close') { $('#feed').classList.remove('is-open'); setPhoneFrame(1); }
    else if (name === 'open-decision') { planOpened = true; renderPlan(planId); }
  });

  // Typing in the bar opens the conversation as a sheet on the phone.
  // Opening the conversation on the phone shows the newest Start card first, with the replies below it.
  function openFeed() {
    var feed = $('#feed');
    feed.classList.add('is-open');
    if (isNarrow()) setPhoneFrame(3);
    var cards = thread.querySelectorAll('.msg-card');
    if (!cards.length) return;
    var card = cards[cards.length - 1];
    feed.scrollTop += card.getBoundingClientRect().top - feed.getBoundingClientRect().top - 8;
  }
  document.addEventListener('focusin', function (e) {
    if (e.target.id === 'chat-input' && isNarrow()) openFeed();
  });
  document.addEventListener('submit', function (e) {
    if (e.target.id === 'chat-form' && isNarrow()) $('#feed').classList.add('is-open');
  });
  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && !$('#now-sheet').hidden) closeNowSheet();
    if ((e.key === 'Enter' || e.key === ' ') && e.target.closest && e.target.closest('#ov-art [role=button]')) {
      e.preventDefault();
      e.target.closest('#ov-art [role=button]').dispatchEvent(new MouseEvent('click', { bubbles: true }));
    }
  });

  /* ---------- Terminal: the same fixture records as a text screen. Simulated. ---------- */

  // Round 10c terminal, measured on the concepts. The overview master is terminal-1-overview-v2.png (1600 x 900);
  // mission and decision use term-mission.webp (862 x 626) and term-decision.webp (862 x 506). Each screen is one
  // SVG in design px: Roboto Mono (vendored, OFL) at measured baselines and pitches (tools/term_layout.py), box and
  // connector strokes, and the background sampled from the concept. Text and marks are live; nothing is a raster.
  var term = { screen: 'overview', sel: 0, mid: 'm-search', cols: 120, plain: false, help: false, input: null, filter: '', step: null };
  var GLYPH_T = { waiting: '◇', running: '*', done: '+', idle: 'o' };
  var STATE_CLS = { waiting: 'amber', running: 'blue', done: 'green', idle: 'dim' };
  var OVER = { W: 1600, H: 900, size: 21.67, cell: 13 };
  var PAGE = { W: 862, H: 626, size: 19.9, cell: 11.93, ox: 31, oy: 41.5, pitch: 30.1 };
  var STACK = { W: 1118, H: 900, size: 21.67, cell: 13, ox: 38, oy: 70, pitch: 33 };
  var DECISION_H = 506, PAGE_H = 626;
  term.color = !/[?&]nocolor/.test(location.search);

  // Overview text runs: text, colour, origin x, baseline y, pitch (design px per character).
  var CONCEPT_TERM = {
    head: [['ARCHEUS', 'ivory', 39, 70, 13.5], ['Not stopped · accepts new work', 'ivory', 213, 70, 13.62], ['CONCEPT FIXTURE', 'dim', 1371, 70, 12.79]],
    title: [['Archeus', 'ivory', 524, 266, 13.17]],
    mission: { search: [569, 329, 12.62], review: [586, 393, 12.6], fix: [893, 329, 12.58], verifying: [898, 393, 12.75], codex: [943, 459, 12.25], verification: [885, 528, 12.55], results: [918, 596, 12.17], more: [521, 627, 12.5] },
    notes: [['Notes', 'ivory', 1273, 329, 12.25], ['2 missions', 'dim', 1281, 364, 12.56]],
    ideas: [['Ideas', 'ivory', 1273, 497, 12]],
    root: [['ARCHEUS', 'ivory', 753, 172, 13.67]],
    footer: [['Why:', 'amber', 41, 699, 13], ['[Enter] Open decision', 'dim', 45, 734, 13.1]],
    keys: [['j/k select', 43, 13.33], ['Enter open', 226, 12.67], ['b Back', 403, 12.8], ['p Replay', 529, 13], ['t Tell', 680, 12.6], ['r Review', 809, 12.71], ['s Stop', 961, 12.6]]
  };
  // Boxes: outer rectangle from measured stroke centres. Corners are chamfers, each one detached from the edges by
  // the measured gap (the concept draws them that way).
  var BOX_MAIN = { L: 486.9, T: 235.5, R: 1105.6, B: 651.0 };
  var BOX_NOTES = { L: 1240.0, T: 296.8, R: 1521.4, B: 413.8 };
  var BOX_IDEAS = { L: 1240.0, T: 465.5, R: 1521.4, B: 580.7 };

  // A scene in design px. Text takes the baseline; the pitch is the advance per character (default: the cell).
  function Scene(m) {
    var items = [], rows = [], cell = m.cell;
    var s = {
      W: m.W, H: m.H, items: items, rows: rows,
      text: function (x, y, str, cls, pitch) {
        if (!str) return;
        var ls = pitch && Math.abs(pitch - cell) > 0.01 ? ' letter-spacing="' + (pitch - cell).toFixed(2) + '"' : '';
        items.push('<text x="' + x.toFixed(2) + '" y="' + y.toFixed(2) + '"' + ls + (term.color && cls ? ' class="' + cls + '"' : '') + '>' + esc(str) + '</text>');
      },
      line: function (x1, y1, x2, y2, cls, w, dash) {
        items.push('<line class="ln ' + (term.color && cls ? cls : '') + '" x1="' + x1 + '" y1="' + y1 + '" x2="' + x2 + '" y2="' + y2 + '" stroke-width="' + (w || 1.5) + '"' + (dash ? ' stroke-dasharray="' + dash + '"' : '') + '/>');
      },
      poly: function (pts, cls, w) { items.push('<polygon class="ln ' + (term.color && cls ? cls : '') + '" points="' + pts + '" stroke-width="' + (w || 1.5) + '"/>'); },
      rect: function (x, y, w, h, cls) { items.push('<rect class="' + (cls || '') + '" x="' + x + '" y="' + y + '" width="' + w + '" height="' + h + '"/>'); },
      dot: function (cx, cy, r, cls) { items.push('<circle class="' + (term.color && cls ? cls : '') + '" cx="' + cx + '" cy="' + cy + '" r="' + r + '"/>'); },
      // A cell-grid helper: put(col, row) puts text on the grid; the row is also kept as plain text for screen readers.
      put: function (col, row, str, cls) {
        s.text(m.ox + col * cell, m.oy + row * m.pitch, str, cls);
        rows[row] = rows[row] || {};
        rows[row][col] = str;
      },
      svg: function () {
        return '<svg class="term-svg' + (m.kind ? ' ' + m.kind : '') + '" xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + m.W + ' ' + m.H + '" width="' + m.W + '" height="' + m.H + '" aria-hidden="true" focusable="false" style="font-size:' + m.size + 'px">' +
          '<defs><linearGradient id="term-bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#17111D"/><stop offset="1" stop-color="#18121E"/></linearGradient></defs>' +
          '<rect class="ground" x="0" y="0" width="' + m.W + '" height="' + m.H + '" fill="url(#term-bg)"/>' + items.join('') + '</svg>';
      }
    };
    return s;
  }

  // Chamfered box: one diagonal per corner (dx across, dy down), edges inset from the corners, verticals from the
  // title line down to the bottom gap. Numbers are the concept's, measured on terminal-1-overview-v2.png.
  function chamferBox(s, b, cls) {
    var dx = 13.2, dy = 19.2, vy0 = b.T + 29, vy1 = b.B - 25.5, ex = dx + 4;
    var w = 1.7;
    s.line(b.L - 0.4, b.T + dy, b.L + dx, b.T + 0.2, cls, w);
    s.line(b.R + 0.4, b.T + dy, b.R - dx, b.T + 0.2, cls, w);
    s.line(b.L - 0.4, b.B - dy, b.L + dx, b.B, cls, w);
    s.line(b.R + 0.4, b.B - dy, b.R - dx, b.B, cls, w);
    s.line(b.L + ex, b.T, b.R - ex, b.T, cls, w);
    s.line(b.L + ex, b.B, b.R - ex, b.B, cls, w);
    s.line(b.L, vy0, b.L, vy1, cls, w);
    s.line(b.R, vy0, b.R, vy1, cls, w);
  }

  // Asterisk glyph as three strokes through the centre (six spokes), sized to the concept's ink box.
  function starMark(s, cx, cy, cls, half) {
    var h = half || 8, d = h * 0.5, e = h * 0.87;
    s.line(cx, cy - h, cx, cy + h, cls, 2.9);
    s.line(cx - e, cy - d, cx + e, cy + d, cls, 2.9);
    s.line(cx - e, cy + d, cx + e, cy - d, cls, 2.9);
  }

  function termOrder() {
    var out = [];
    projects.forEach(function (p) { missions.forEach(function (m) { if (m.project === p.id) out.push(m); }); });
    return out.filter(function (m) { return !term.filter || (m.title + ' ' + projectOf(m.project).name).toLowerCase().indexOf(term.filter.toLowerCase()) >= 0; });
  }
  function selected() { var o = termOrder(); return o[Math.min(term.sel, o.length - 1)] || missions[0]; }
  function tword(m) { return STATE[m.state].word; }
  // Plain-line mode: labelled lines, no boxes, for screen readers and copy.
  function plainOverview() {
    var L = ['ARCHEUS  Core connected; not stopped; accepts new work.', 'Counts: ' + count('waiting') + ' needs you, ' + count('running') + ' verifying, 0 queued.'];
    var sel = selected();
    projects.forEach(function (p) {
      var ms = missions.filter(function (m) { return m.project === p.id; });
      L.push('PROJECT ' + p.name + ': ' + ms.length + ' missions.');
      ms.forEach(function (m) {
        L.push('  MISSION ' + (m === sel ? '[selected] ' : '') + m.title + '. State: ' + tword(m) + '. Detail: ' + m.stateText + '.');
      });
    });
    L.push('Selected: ' + sel.title + '. Enter opens it. Why: ' + (plans[sel.id] ? plans[sel.id].why : 'nothing waiting.'));
    return L;
  }

  // The 120 x 40 overview at the concept's size: every run is placed at its measured origin, baseline and pitch.
  function overview120() {
    var s = Scene({ W: OVER.W, H: OVER.H, size: OVER.size, cell: OVER.cell, ox: 0, oy: 0, pitch: 0 });
    var arch = projects[0], sel = selected();
    var inArch = missions.filter(function (m) { return m.project === arch.id; });
    var fa = inArch.filter(function (m) { return m.state === 'waiting'; })[0];
    var fb = inArch.filter(function (m) { return m.state === 'running'; })[0];
    var rest = inArch.length - [fa, fb].filter(Boolean).length;
    var nw = count('waiting'), nr = count('running');
    s.rect(25, 826.5, 1550, 40.5, 'strip');
    s.line(29, 39.4, 1570, 39.4, 'rule', 1.6);
    CONCEPT_TERM.head.forEach(function (r) { s.text(r[2], r[3], r[0], r[1], r[4]); });
    s.dot(187, 62.7, 6.3, 'green');
    s.text(40, 102, nw + ' needs you', 'amber', 13.6);
    s.text(210, 102, '·', 'dim', 13);
    s.text(238, 102, nr + ' verifying', 'blue', 13.5);

    chamferBox(s, BOX_MAIN, 'ln');
    s.text(524, 266, arch.name, 'ivory', 13.17);
    s.line(636, 259.3, 1073, 259.3, '', 1.6);
    s.line(812.6, 301, 812.6, 625, 'div', 1.5);
    if (fa) {
      if (sel === fa) s.rect(516, 310, 302, 27, 'select');
      s.poly('533.5,309.5 543.5,321.5 533.5,333.5 523.5,321.5', 'amber', 1.6);
      s.text(569, 329, fa.title, 'amber', 12.62);
      s.line(632.5, 339, 632.5, 369, 'amber', 1.5);
      s.text(586, 393, fa.stateText, 'amber', 12.6);
    }
    if (fb) {
      if (sel === fb) s.rect(884, 310, 186, 27, 'select');
      starMark(s, 858.5, 321, 'blue', 8.5);
      s.text(893, 329, fb.title, 'blue', 12.58);
      s.line(954.5, 339, 954.5, 369, 'ln', 1.5);
      s.text(898, 393, 'Verifying', 'blue', 12.75);
      s.line(954.5, 402, 954.5, 431, 'ln', 1.5);
      s.poly('905.5,458.5 920.5,458.5 913,441.5', '', 1.6);
      s.text(943, 459, 'Codex', 'ivory', 12.25);
      s.line(954.5, 469, 954.5, 501, 'ln', 1.5);
      s.text(885, 528, 'Verification', 'blue', 12.55);
      s.line(954.5, 538, 954.5, 568, 'ln', 1.5);
      s.text(918, 596, 'Results', 'blue', 12.17);
    }
    if (rest > 0) s.text(521, 627, '+' + rest + ' more', 'dim', 12.5);

    chamferBox(s, BOX_NOTES, 'ln');
    s.text(1273, 329, projects[1].name, 'ivory', 12.25);
    s.line(1355, 321.8, 1501, 321.8, '', 1.6);
    var nn = missions.filter(function (m) { return m.project === projects[1].id; }).length;
    if (nn) s.text(1281, 364, nn + ' missions', 'dim', 12.56);
    chamferBox(s, BOX_IDEAS, 'ln');
    s.text(1273, 497, projects[2].name, 'ivory', 12);
    s.line(1355, 489, 1501, 489, '', 1.6);

    // Connectors: fine dashed diagonals with a short tick at the far end.
    s.line(1115, 265.5, 1210.5, 353.8, 'link', 1.3, '5.5 3.5');
    s.line(1211, 354.5, 1224, 354.5, 'link', 1.3);
    s.line(1114, 427.5, 1210.5, 518, 'link', 1.3, '5.5 3.5');
    s.line(1211, 521.5, 1223, 521.5, 'link', 1.3);

    starMark(s, 799.5, 129.5, '', 8);
    CONCEPT_TERM.root.forEach(function (r) { s.text(r[2], r[3], r[0], r[1], r[4]); });
    s.line(747.5, 183, 731, 201.5, '', 2.2); s.line(729, 204, 715, 220, '', 2.2);
    s.line(851.75, 183, 867.5, 201.25, '', 2.2); s.line(870, 204, 883.75, 220.5, '', 2.2);

    CONCEPT_TERM.footer.forEach(function (r) { s.text(r[2], r[3], r[0], r[1], r[4]); });
    var why = fa && plans[fa.id] ? plans[fa.id].why : 'nothing waiting.';
    s.text(111, 699, why, 'ivory', 13.23);
    CONCEPT_TERM.keys.forEach(function (k, i) { s.text(k[1], 804, k[0], 'ivory', k[2]); });
    s.text(42, 855, term.input ? term.input.mode + ' ' + term.input.text + '_' : '> Tell Archeus...', term.input ? 'ivory' : 'dim', 13);
    return s;
  }

  // The 80 x 24 stack keeps its single-column layout (no concept). Grid rows, boxes drawn as strokes.
  function overview80() {
    var s = Scene(STACK), sel = selected();
    s.put(0, 0, 'ARCHEUS', 'ivory'); s.put(8, 0, '  Not stopped · accepts new work', 'ivory');
    s.put(0, 1, count('waiting') + ' needs you · ' + count('running') + ' verifying', 'ivory');
    var y = 2;
    projects.forEach(function (p, pi) {
      var ms = missions.filter(function (m) { return m.project === p.id; });
      if (pi > 0) { s.put(0, y, p.name + ' · ' + ms.length + ' missions', 'dim'); y += 2; return; }
      var top = STACK.oy + y * STACK.pitch + 12, bot = top + (ms.length + 1) * STACK.pitch;
      s.line(STACK.ox, top, STACK.W - 40, top, '', 1.2);
      s.line(STACK.ox, bot, STACK.W - 40, bot, '', 1.2);
      s.line(STACK.ox, top, STACK.ox, bot, '', 1.2);
      s.line(STACK.W - 40, top, STACK.W - 40, bot, '', 1.2);
      s.text(STACK.ox, STACK.oy + y * STACK.pitch, p.name, 'ivory');
      ms.forEach(function (m, i) {
        s.put(2, y + 1 + i, (sel === m ? '> ' : '  ') + GLYPH_T[m.state] + ' ' + m.title, STATE_CLS[m.state]);
      });
      y += ms.length + 2;
    });
    var fa = missions.filter(function (m) { return m.state === 'waiting'; })[0];
    s.put(0, y, 'Why:', 'amber');
    s.put(5, y, ' ' + (fa && plans[fa.id] ? plans[fa.id].why : 'nothing waiting.'));
    return s;
  }

  // Mission (term-mission.webp): header, the selected mission, its chain, the three view rows and the key row.
  function termMissionScene() {
    var m = find(term.mid) || find('m-date'), p = projectOf(m.project), s = Scene(PAGE);
    s.put(0, 0, 'ARCHEUS', 'bold'); s.put(8, 0, '  Core connected | Not stopped - accepts new work');
    s.put(0, 1, 'Overview / ' + p.name + ' / ' + m.title); s.put(51, 1, 'CONCEPT FIXTURE');
    var head = '* ARCHEUS - member - ' + p.name + ' - member - ';
    s.put(0, 3, head, 'bold');
    s.put(head.length, 3, 'o ' + m.title, 'bold');
    if (m.exec) {
      s.text(PAGE.ox + 45.5 * PAGE.cell, PAGE.oy + 4 * PAGE.pitch, '\\', 'soft');
      s.text(586, PAGE.oy + 5 * PAGE.pitch, '^ Codex - execution', 'soft');
    }
    s.put(0, 7, m.title + '   ' + m.branch);
    s.put(0, 8, m.stateText + (m.exec ? ' | 1 live execution' : ''), 'soft');
    s.put(0, 9, 'Understand / Plan / Approve / Run / [Verify] / Review');
    s.put(0, 11, 'Latest record: ' + m.latest);
    s.put(0, 12, 'Task: ' + (m.task === 'none' ? 'not recorded' : m.task));
    s.put(0, 14, '> Activity'); s.put(0, 15, '  Plan'); s.put(0, 16, '  Why / recorded relations');
    s.put(0, 18, 'Enter inspect  b Back  / find  g places  t Tell  s Stop  ? help', 'dim');
    return s;
  }

  // Decision (term-decision.webp): amber for the obligation, ivory for the plan, red for the Stop line.
  function termDecisionScene() {
    var m = find(term.mid) || find('m-search'), p = plans[m.id];
    var s = Scene({ W: PAGE.W, H: DECISION_H, size: PAGE.size, cell: PAGE.cell, ox: PAGE.ox, oy: PAGE.oy, pitch: PAGE.pitch, kind: 'decision' });
    s.put(0, 0, 'ARCHEUS', 'bold'); s.put(8, 0, '  Core connected | Not stopped - accepts new work');
    s.put(0, 1, 'Overview / ' + projectOf(m.project).name + ' / ' + m.title, 'amber'); s.put(51, 1, 'CONCEPT FIXTURE', 'amber');
    if (!p) { s.put(0, 3, 'No plan is recorded for ' + m.title + '.'); s.put(0, 15, 'b back  ? help', 'dim'); return s; }
    s.put(0, 3, '* ARCHEUS', 'amber'); s.put(14, 3, 'o ' + m.title, 'amber'); s.text(455, PAGE.oy + 3 * PAGE.pitch, '! NEEDS YOU', 'amber');
    s.put(0, 5, 'Review plan v' + p.version + ' | ' + m.branch);
    s.put(0, 6, 'What: ' + m.what);
    s.put(0, 7, 'Why: ' + p.why);
    s.put(0, 8, 'Consequence: use the exact consequence recorded by Core.');
    s.put(0, 9, 'A decided approval cannot be changed. No Undo is available.');
    if (term.step === 'approve') {
      s.put(0, 11, 'Approve selected. Confirm only after reading current plan.', 'amber');
      s.put(0, 12, 'Confirm this decision? Type y to confirm; any other key cancels.', 'amber');
    }
    s.put(0, 14, 's Stop remains available outside the confirmation input', 'red');
    s.put(0, 15, term.step ? 'y confirm   any other key cancels' : 'a approve  c changes  x reject  b back  ? help', 'dim');
    return s;
  }

  function termReplayScene() {
    var m = find(term.mid) || find('m-date'), rows = REPLAY[m.id] || [];
    var s = Scene(PAGE), n = 3;
    s.put(0, 0, 'ARCHEUS', 'bold'); s.put(8, 0, '  Core connected | Not stopped - accepts new work');
    s.put(0, 1, 'Overview / ' + projectOf(m.project).name + ' / Replay ' + m.title + ' (sample data)');
    rows.forEach(function (r, i) {
      var hot = r.tone === 'uncertain' || r.tone === 'needs-you' ? 'amber' : r.tone === 'verified' ? 'green' : '';
      s.put(0, n, (r.mark === 'check' ? '+' : r.mark === 'diamond' ? '◇' : '*') + ' ' + r.time, hot || 'dim');
      s.put(10, n, '[' + r.badge + ']', hot);
      s.put(20, n, r.title);
      s.put(20, n + 1, r.sub, 'dim');
      n += 3;
    });
    s.put(0, n, '[Operator] Reconcile  --:--', 'dim');
    s.put(0, n + 1, 'Record what happened on the remote. Nothing is pushed here.', 'dim');
    s.put(0, n + 2, 'Not every external effect can be reversed.', 'dim');
    s.put(0, 18, 'b back  t tell  s stop  ? help', 'dim');
    return s;
  }

  function termHelpScene() {
    var s = Scene(PAGE);
    s.put(0, 0, 'ARCHEUS', 'bold'); s.put(8, 0, '  Core connected | Not stopped - accepts new work');
    s.put(0, 1, 'HELP  keys');
    var keys = ['j / k or arrows   select a mission', 'Enter               open the mission (or decision)', 'r                   review plan (decision)', 'p                   replay', 'm                   mission', 't                   tell (not sent)',
      's                   stop (double press, nothing stops)', 'b or Esc            back', '/                   filter by name', ':                   jump to project, mission or replay', 'L                   plain-line mode on and off', '?                   this help'];
    keys.forEach(function (k, i) { s.put(3, 3 + i, k); });
    s.put(0, 18, '? close help', 'dim');
    return s;
  }

  // Plain-line mode and the screen-reader text: the same content as text lines.
  function srText(s) {
    return s.rows.map(function (r) {
      var out = '';
      Object.keys(r || {}).map(Number).sort(function (a, b) { return a - b; }).forEach(function (c) { while (out.length < c) out += ' '; out += r[c]; });
      return out;
    }).join('\n');
  }

  function renderTerm() {
    var pre = $('#term'), sim = $('#term-sim'), w = term.cols, s = null, text = '';
    pre.setAttribute('data-cols', String(w));
    var simLine = term.step ? 'Confirm this decision? Type y to confirm; any other key cancels.' : 'SIMULATED: fake data, nothing sent to Core. ' + (term.filter ? 'Filter: ' + term.filter + '.' : '');
    if (term.plain && term.screen === 'overview' && !term.help) {
      pre.className = 'term plain';
      text = plainOverview().join('\n');
      pre.textContent = text;
    } else {
      if (term.help) s = termHelpScene();
      else if (term.screen === 'mission') s = termMissionScene();
      else if (term.screen === 'decision') s = termDecisionScene();
      else if (term.screen === 'replay') s = termReplayScene();
      else s = w >= 100 ? overview120() : overview80();
      pre.className = 'term';
      pre.innerHTML = s.svg() + '<span class="sr-only">' + esc(srText(s)) + '</span>';
      fitTerm(pre);
    }
    if (sim) sim.textContent = simLine;
    $$('[data-tsize]').forEach(function (b) { b.setAttribute('aria-pressed', String(Number(b.getAttribute('data-tsize')) === w)); });
  }

  // The SVG keeps its design size and scales to the wrapper (0.75 to 1.25). Text, strokes and gaps scale together.
  function fitTerm(pre) {
    var wrap = pre.parentNode, svg = pre.querySelector('svg');
    if (!svg) return;
    var W = Number(svg.getAttribute('width')), H = Number(svg.getAttribute('height'));
    var k = Math.min(1.25, Math.max(0.75, wrap.clientWidth / W));
    svg.style.width = (W * k) + 'px';
    svg.style.height = (H * k) + 'px';
  }

  function renderTerminal() { renderTerm(); $('#term').focus({ preventScroll: true }); }


  function runCommand(text) {
    var q = text.trim().toLowerCase();
    if (!q) return 'Nothing to run.';
    var p = projects.filter(function (x) { return x.name.toLowerCase() === q; })[0];
    if (p) {
      var first = missions.filter(function (m) { return m.project === p.id; })[0];
      if (first) { term.sel = termOrder().indexOf(first); term.screen = 'overview'; }
      return 'Jumped to project ' + p.name + '.';
    }
    var m = missions.filter(function (x) { return x.title.toLowerCase().indexOf(q) >= 0 || x.id === q; })[0];
    if (m) { term.mid = m.id; term.screen = 'mission'; return 'Opened ' + m.title + '.'; }
    if (q === 'replay') { term.screen = 'replay'; return 'Replay opened.'; }
    return 'No project or mission named ' + text.trim() + '.';
  }

  function termKey(e) {
    if (!$('#s-terminal') || $('#s-terminal').hidden || e.target.id === 'term-tell') return;
    var k = e.key, order = termOrder();
    if (term.input) {
      e.preventDefault();
      if (k === 'Escape') { term.input = null; }
      else if (k === 'Enter') { var out = term.input.mode === ':' ? runCommand(term.input.text) : (term.filter = term.input.text.trim(), term.sel = 0, 'Filter set.'); term.input = null; $('#term-status').textContent = out; }
      else if (k === 'Backspace') { term.input.text = term.input.text.slice(0, -1); }
      else if (k.length === 1) { term.input.text += k; }
      return renderTerm();
    }
    if (term.step) {
      e.preventDefault();
      if (k === 'y') { term.step = null; say('Prototype: nothing was approved. This page records no decision.'); }
      else { term.step = null; say('Approval cancelled. Nothing was decided.'); }
      return renderTerm();
    }
    if (term.help) { if (k === '?' || k === 'Escape') { term.help = false; e.preventDefault(); renderTerm(); } return; }
    if (k === '?') { term.help = true; }
    else if (k === ':') { term.input = { mode: ':', text: '' }; }
    else if (k === '/') { term.input = { mode: '/', text: '' }; }
    else if (k === 'L') { term.plain = !term.plain; }
    else if (k === 'C') { term.color = !term.color; }
    else if (k === 'j' || k === 'ArrowDown') term.sel = Math.min(order.length - 1, term.sel + 1);
    else if (k === 'k' || k === 'ArrowUp') term.sel = Math.max(0, term.sel - 1);
    else if (k === 'Enter' && term.screen === 'overview' && selected()) { term.mid = selected().id; term.screen = 'mission'; }
    else if (k === 'r') { term.mid = selected().id; term.screen = 'decision'; }
    else if (k === 'a' && term.screen === 'decision') { term.step = 'approve'; }
    else if (k === 'p') { term.mid = selected().id; term.screen = 'replay'; }
    else if (k === 'm') term.screen = 'mission';
    else if (k === 'Escape' || k === 'b') { term.screen = 'overview'; if (k === 'Escape') term.filter = ''; }
    else if (k === 's') { stop(); }
    else if (k === 't') { e.preventDefault(); $('#term-tell').focus(); return; }
    else return;
    e.preventDefault();
    renderTerm();
  }

  document.addEventListener('keydown', termKey);
  document.addEventListener('click', function (e) {
    var b = e.target.closest('[data-tsize]');
    if (b) { term.cols = Number(b.getAttribute('data-tsize')); term.rows = term.cols === 120 ? 40 : 24; renderTerm(); }
  });
  $('#term-tell').addEventListener('keydown', function (e) {
    if (e.key !== 'Enter') return;
    e.preventDefault();
    var v = this.value.trim();
    this.value = '';
    $('#term-status').textContent = v ? 'Simulated: "' + v.slice(0, 60) + '" was not sent to Core.' : 'Tell line is empty.';
    this.blur(); $('#term').focus({ preventScroll: true });
  });

  var SCREENS = {
    now: renderNow,
    mission: function (id) { renderMission(id); },
    replay: renderReplay,
    terminal: renderTerminal,
    shared: renderShared,
    phone: renderPhone,
    plan: function (id) { planStep = 'review'; renderPlan(id); }
  };

  function route() {
    var parts = (location.hash || '#/now').replace(/^#\/?/, '').split('/');
    var name = SCREENS[parts[0]] && !(parts[0] === 'phone' && isNarrow()) ? parts[0] : 'now';
    document.body.classList.remove('menu-open');
    document.body.classList.toggle('frame-now', name === 'now' && !isNarrow());
    document.body.classList.toggle('frame-mission', name === 'mission');
    document.body.classList.toggle('frame-shared', name === 'shared');
    fitFrame();
    closeSheet(true);
    $$('main > section').forEach(function (s) { s.hidden = s.id !== 's-' + name; });
    $$('.places a').forEach(function (a) {
      if (a.getAttribute('data-nav') === name) a.setAttribute('aria-current', 'page');
      else a.removeAttribute('aria-current');
    });
    SCREENS[name](parts[1]);
    fitReplayFrame();
    var h = $('#s-' + name + ' h1');
    if (h) h.focus({ preventScroll: true });
  }

  renderRail();
  buildOverview();
  placeFrame($('#m-frame'), R10C.mission);
  placeFrame($('#sh-frame'), R10C.shared);

  window.addEventListener('resize', function () {
    fitFrame();
    [nowStage, phoneStage].forEach(function (s) { s.relayout(); });
  });
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden) [nowStage, phoneStage].forEach(function (s) { s.kick(); });
  });
  if (reduce.addEventListener) {
    reduce.addEventListener('change', function () {
      [nowStage, phoneStage].forEach(function (s) { s.relayout(); s.kick(); });
    });
  }

  window.addEventListener('hashchange', route);
  route();

  if ('serviceWorker' in navigator && /^https?:$/.test(location.protocol)) {
    navigator.serviceWorker.register('sw.js');
  }
})();
