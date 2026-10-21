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
    { id: 'm-date', title: 'Fix date test', project: 'archeus', branch: 'fix/date-test', state: 'running', stateText: 'Verifying', phase: 4, glyph: 'term', what: 'Run the date test suite and confirm the fix.', latest: 'Tool result received.', task: 'Run date suite on fix/date-test and collect the results.', exec: true, related: [{ key: 'suite', title: 'Date test suite', sub: 'Test definitions and inputs', glyph: 'doc', verb: 'uses' }, { key: 'results', title: 'Results', sub: 'Test execution outputs', glyph: 'chart', verb: 'produces' }, { key: 'verify', title: 'Verification', sub: 'Confirms behaviour', glyph: 'check', verb: 'verifies', from: 'results' }], log: ['Tool call received.', 'Tool result received.', 'Not passed tests.', 'Parsing results.', 'Proceeding to verification checks.'] },
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
  var pendingApply = null;
  var sheetOpen = null;
  var lastStar = null;
  var missionTab = 'overview';
  var sharedTab = 'overview';
  var missionShown = 'm-date';
  var planStep = 'review';

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
  function drawCore(g, c, t, hot, s) {
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
  function drawTriangle(g, x, y, r, lit) {
    g.save();
    g.strokeStyle = IVORY; g.lineWidth = 1.1; g.globalAlpha = lit ? 0.9 : 0.6;
    g.beginPath(); g.moveTo(x, y - r); g.lineTo(x + r * 0.9, y + r * 0.62); g.lineTo(x - r * 0.9, y + r * 0.62); g.closePath(); g.stroke();
    glyph(g, 'code', x, y + r * 0.1, r * 0.42, IVORY, 0.85);
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
        exec: [871, 428], verif: [806, 488], results: [925, 488]
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
  function nowScene(w, h) {
    if (w < 640) return phoneScene(w, h);
    var L = CONCEPT_LAYOUT.desktop;
    var hh = h - Math.min(280, Math.round(h * 0.36));
    var k = Math.max(0.6, Math.min(w / 1296, hh / 560, 1.1));
    var sc = mk(w, h, { x: w * 0.5, y: hh * 0.45 }, k, false);
    var c = layoutMap(L, L.core[0], L.core[1], w, hh);
    sc.core = { x: c.x, y: c.y };
    sc.sats = [];
    var archeus = projectOf('archeus'), notes = projectOf('notes'), ideas = projectOf('ideas');
    sc.projects.push({ id: 'archeus', name: archeus.name, hue: IVORY, note: archeus.note, ring: layoutHull(L, L.hulls.archeus, w, hh), members: ['m-search', 'm-date', 'm-done'], count: 3, live: 2, active: true });
    sc.projects.push({ id: 'notes', name: notes.name, hue: IVORY, note: notes.note, ring: layoutHull(L, L.hulls.notes, w, hh), members: ['m-index', 'm-read'], count: 2, live: 0, active: false });
    sc.projects.push({ id: 'ideas', name: ideas.name, hue: IVORY, note: ideas.note, ring: layoutHull(L, L.hulls.ideas, w, hh), members: [], count: 0, live: 0, active: false });
    sc.parent.archeus = 'core'; sc.parent.notes = 'core'; sc.parent.ideas = 'core';
    sc.links.push({ a: 'core', b: 'archeus', col: IVORY, live: true, kind: 'project', hue: IVORY });
    sc.links.push({ a: 'core', b: 'notes', col: IVORY, live: false, kind: 'project', hue: IVORY });
    sc.links.push({ a: 'core', b: 'ideas', col: IVORY, live: false, kind: 'project', hue: IVORY, dash: true });
    var mSearch = find('m-search'), mDate = find('m-date'), mDone = find('m-done');
    var at = function (key) { var q = layoutMark(L, key, w, hh); return q; };
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

  function sharedScene(w, h) {
    var k = Math.max(0.7, Math.min(w / 720, h / 600, 1.1));
    var sc = mk(w, h, { x: w * 0.5, y: h * 0.42 }, k, false);
    sc.frame = { x: w * 0.5, y: h * 0.42, r: Math.min(w, h) * 0.46 };
    var nodes = [
      { id: 'planner', kind: 'agent', state: 'waiting', x: w * 0.2, y: h * 0.2, r: 40 * k, glyph: 'list', title: 'Planner', kicker: 'Agent', sub: 'Search provenance', st: 'Needs you', live: true, hit: false, solid: TET, verb: 'plans' },
      { id: 'codex', kind: 'agent', state: 'running', x: w * 0.8, y: h * 0.2, r: 40 * k, glyph: 'term', title: 'Codex', kicker: 'Agent', sub: 'Fix date test', st: 'Running', live: true, hit: false, solid: TET, verb: 'runs' },
      { id: 'desktop', kind: 'device', state: 'connected', x: w * 0.2, y: h * 0.74, r: 36 * k, glyph: 'monitor', title: 'This desktop', kicker: 'Device', sub: 'Connected', st: '', live: false, hit: false, solid: CUBE },
      { id: 'phone', kind: 'device', state: 'recent', x: w * 0.5, y: h * 0.86, r: 32 * k, glyph: 'phone', title: 'Paired phone', kicker: 'Device', sub: 'Recent', st: '', live: false, hit: false, solid: CUBE },
      { id: 'other', kind: 'device', state: 'future', x: w * 0.8, y: h * 0.74, r: 36 * k, glyph: '', title: 'Other people', kicker: 'Future contract', sub: 'Not yet available', st: '', live: false, hit: false, solid: CUBE, dash: true }
    ];
    nodes.forEach(function (n, i) {
      n.seed = 0.2 + i * 0.19;
      sc.nodes.push(n);
      sc.parent[n.id] = 'core';
      sc.links.push({ a: 'core', b: n.id, col: n.kind === 'agent' ? STATE[n.state].color : IVORY, live: n.live, kind: n.kind, hue: IVORY, verb: n.verb || '', dash: n.dash });
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
      R0.forEach(function (v, j) {
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
      if (!p._facets) p._facets = facetsFor(R0, p.id);
      p._facets.forEach(function (f) {
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
        if (p.ring) { ringHull(g, p, c, !!H[p.id], grow(p.id, anim)); return; }
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

      // Links: the lit chain is bright and carries a travelling pulse when live; the rest recede.
      sc.links.forEach(function (l, idx) {
        var a = pos[l.a], b = pos[l.b];
        if (!a || !b) return;
        var gl = grow(l.a + '>' + l.b, anim);
        if (gl < 1) b = { x: a.x + (b.x - a.x) * gl, y: a.y + (b.y - a.y) * gl };
        var fresh = S.born[l.a + '>' + l.b] !== undefined && performance.now() - S.born[l.a + '>' + l.b] < 6000;
        var lit = !!(H[l.a] && H[l.b]);
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

      drawCore(g, c, anim, !!H.core, s);
      var it0 = S.items.core;
      if (it0) { it0.cx = c.x; it0.cy = c.y; it0.hr = 60 * s; it0.pt = c; it0.r = 60 * s; }

      // Figures: receding first, lit last. Overview marks are small glyphs; other screens keep their bodies.
      var order = sc.nodes.slice().sort(function (a, b) { return (H[a.id] ? 1 : 0) - (H[b.id] ? 1 : 0); });
      order.forEach(function (n) {
        var q = pos[n.id], lit = !!H[n.id], R = n.r * s;
        var gn = grow(n.id, anim);
        if (gn < 1) R *= 0.35 + 0.65 * gn;
        var col = STATE[n.state] ? STATE[n.state].color : IVORY;
        if (n.mark) {
          g.save(); g.globalAlpha = gn;
          if (n.kind === 'exec') drawTriangle(g, q.x, q.y, Math.max(12, R * 1.4), lit);
          else if (n.dot) { g.fillStyle = STATE.running.color; g.beginPath(); g.arc(q.x, q.y, 4.2, 0, TAU); g.fill(); }
          else if (n.kind === 'mission') drawMark(g, q.x, q.y, n.state, Math.max(5, R), lit);
          else drawSolid(g, n.solid, q.x, q.y, Math.max(9, R), { y: n.seed * TAU, x: 0.42 }, IVORY, { alpha: 0.75 * gn, wash: false, glyph: n.glyph, dotR: 1.6, lw: 0.9 });
          g.restore();
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
        core.lbl.style.transform = 'translate(' + (c.x - core.tw / 2).toFixed(1) + 'px,' + (c.y + 84 * s).toFixed(1) + 'px)';
        placed.push({ x0: c.x - core.tw / 2, y0: c.y + 84 * s, x1: c.x + core.tw / 2, y1: c.y + 84 * s + core.th });
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
        var pt = it.pt, off = it.r + 12;
        var par = it.par && S.items[it.par] && S.items[it.par].cx !== undefined ? S.items[it.par] : null;
        var org = par ? { x: par.cx, y: par.cy } : c;
        var ox = pt.x - org.x, oy = pt.y - org.y, len = Math.hypot(ox, oy) || 1;
        ox /= len; oy /= len;
        var cands = dirs.slice().sort(function (a, b) {
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
        entries.push({ id: id, it: it, box: box, bw: bw, bh: bh, cand: best.cand, dir: { x: ox, y: oy } });
      });
      // Relaxation: a label that still touches another moves outward along its radial, four passes at most.
      for (var pass = 0; pass < 10; pass++) {
        var moved = false;
        for (var a = 0; a < entries.length; a++) for (var b = a + 1; b < entries.length; b++) {
          if (!overlaps(entries[a].box, entries[b].box, 6)) continue;
          var e = entries[b], nb = e.box;
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
        var quiet = labelQuiet(e.id, e.it);
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
        var subCls = n.kind === 'mission' ? 'st-' + n.state : n.kind === 'device' ? { connected: 'st-done', recent: 'st-running', future: 'st-idle' }[n.state] || '' : '';
        var action = n.kind === 'mission' && n.state === 'waiting' ? { href: '#/plan/' + n.id, text: sc.compact ? 'Review' : 'Review →', aria: 'Review plan for ' + n.title } : null;
        var line2 = n.kind === 'mission' ? n.detail : n.kind === 'exec' ? 'execution' : st ? st + (sub ? ' · ' + sub : '') : sub;
        var execPhone = sc.compact && n.kind === 'exec';
        addLabel(n.id, { cls: 'lbl ' + n.kind, kicker: n.kicker, title: execPhone ? 'Codex · execution' : n.title, sub: execPhone ? '' : line2, subCls: subCls, kind: n.kind, action: action });
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
        S.verbItems.push({ el: lbl, a: l.a, b: l.b, side: S.verbItems.length % 2 ? -1 : 1 });
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

  var nowStage = makeStage($('#now-stage'), {
    onPick: function (id, kind) {
      if (isNarrow()) { if (kind === 'mission') openDetail(id); else openList(); return; }
      if (kind === 'project') location.hash = '#/now/' + id;
      else location.hash = '#/mission/' + id;
    }
  });
  var missionStage = makeStage($('#mission-stage'), {
    onPick: function (id, kind) { if (kind === 'project') location.hash = '#/now/' + id; }
  });
  var sharedStage = makeStage($('#shared-stage'));
  var replayStage = makeStage($('#replay-stage'));
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
    nowStage.setScene(nowScene);
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

  function renderMission(id) {
    var m = find(id) || find(missionShown);
    missionShown = m.id;
    var sec = $('#s-mission'), p = projectOf(m.project);
    $('[data-m-project]', sec).textContent = p.name;
    $('[data-m-project2]', sec).textContent = p.name;
    $('[data-m-crumb]', sec).textContent = m.title;
    $('[data-m-title]', sec).textContent = m.title;
    $('[data-m-branch]', sec).textContent = m.branch;
    $('#m-replay').href = '#/replay/' + m.id;
    var st = $('[data-m-state]', sec);
    st.textContent = stateLine(m);
    st.className = 'state-line st-' + m.state;
    missionStage.setScene(function (w, h) { return missionScene(m, w, h); });
    $('#m-phases').innerHTML = phaseBar(m);
    renderMissionPanel();
  }

  function phaseBar(m) {
    return PHASES.map(function (name, i) {
      var cls = '';
      if (m.phase === 6 || i < m.phase) cls = 'done';
      else if (i === m.phase) cls = m.state === 'waiting' ? 'wait' : 'current';
      var word = cls === 'done' ? 'done' : cls === 'wait' ? 'waiting for you' : cls === 'current' ? 'current' : 'not reached';
      return '<li class="' + cls + '">' + name + '<span class="sr-only">, ' + word + '</span></li>';
    }).join('');
  }

  function renderMissionPanel() {
    var m = find(missionShown), box = $('#m-panel');
    var p = plans[m.id];
    $$('[data-mtab]').forEach(function (b) { b.setAttribute('aria-selected', String(b.getAttribute('data-mtab') === missionTab)); });
    if (missionTab === 'activity') {
      box.innerHTML = '<p class="kicker">Activity log</p><ul class="log">' +
        m.log.map(function (l) { return '<li' + (/Not passed/.test(l) ? ' class="bad"' : '') + '>' + esc(l) + '</li>'; }).join('') + '</ul>';
    } else if (missionTab === 'plan') {
      box.innerHTML = p
        ? '<p class="kicker">Plan v' + p.version + '</p><ul class="log">' + p.tasks.map(function (t) { return '<li>' + esc(t.key) + ' · ' + esc(t.text) + '</li>'; }).join('') + '</ul><div class="row"><a class="btn" href="#/plan/' + m.id + '">Open plan</a></div>'
        : '<p class="small">No plan recorded for this mission.</p>';
    } else {
      var ph = m.phase < 0 ? 'Not started' : m.phase === 6 ? 'Complete' : PHASES[m.phase];
      box.innerHTML =
        '<p class="kicker">Current phase</p><p class="big">' + esc(ph) + '</p>' +
        '<p class="small">' + esc(m.what) + '</p>' +
        '<div class="item"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3 21 19H3z"/></svg><div><p>' + (m.exec ? 'Codex, execution' : 'No agent recorded') + '</p><p class="sub">' + (m.exec ? 'Runs checks, collects evidence, reports results.' : 'Nothing is running for this mission.') + '</p></div></div>' +
        '<div class="item"><svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="2"/><path d="M7 9l3 3-3 3M12 15h5"/></svg><div><p>Current task</p><p class="sub">' + esc(m.task) + '</p></div></div>' +
        '<div class="item"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M6 3h9l3 3v15H6z"/></svg><div><p>Latest record</p><p class="sub">' + esc(m.latest) + '</p></div></div>';
    }
  }

  // Sample data (simulated): the 09:00 to 09:25 example from the strategy report.
  var REPLAY = {
    'm-date': [
      { time: '09:00', title: 'Task initiated', sub: 'Scope, authority and starting state captured', badge: 'Intended', tone: 'intended', mark: 'dot' },
      { time: '09:12', title: 'Files changed', sub: 'Changes and resulting artifacts linked to the task', badge: 'Recorded', tone: 'recorded', mark: 'dot' },
      { time: '09:18', title: 'Tests passed', sub: 'Validation evidence recorded', badge: 'Verified', tone: 'verified', mark: 'check' },
      { time: '09:24', title: 'External response lost', sub: 'Side effect classified as uncertain. It may have taken effect.', badge: 'Uncertain', tone: 'uncertain', mark: 'diamond' },
      { time: '09:25', title: 'Workflow suspended', sub: 'Suspended. No unsafe retry; operator reconciliation required.', badge: 'Needs you', tone: 'needs-you', mark: 'diamond' }
    ]
  };
  var replayId = 'm-date';

  function renderReplay(id) {
    var m = find(id) || find('m-date'), rows = REPLAY[m.id] || [], p = projectOf(m.project);
    replayId = m.id;
    var sec = $('#s-replay');
    $('[data-rp-project]', sec).textContent = p.name;
    $('[data-rp-crumb]', sec).textContent = m.title;
    $('[data-rp-title]', sec).textContent = 'Replay · ' + m.title;
    replayStage.setScene(function (w, h) { return missionScene(m, w, h, true); });
    var list = rows.map(function (r) {
      return '<li class="rp-row rs-' + r.mark + '"><span class="rp-time">' + r.time + '</span><span class="rp-mark" aria-hidden="true"></span>' +
        '<span class="rp-body"><span class="rp-title">' + esc(r.title) + '</span><span class="rp-sub">' + esc(r.sub) + '</span></span>' +
        '<span class="rp-badge tone-' + r.tone + '">' + esc(r.badge) + '</span></li>';
    });
    if (!rows.length) list.push('<li class="rp-row"><span class="rp-sub">No replay is recorded for this mission in the prototype. Sample data exists for Fix date test only.</span></li>');
    list.push('<li class="rp-row rp-reconcile"><span class="rp-time"></span><span class="rp-mark" aria-hidden="true"></span>' +
      '<span class="rp-body"><span class="rp-title">Reconcile</span><span class="rp-sub">Record what happened on the remote. Nothing is pushed or retried here.</span>' +
      '<span class="rp-actions"><button type="button" class="btn primary" data-act="reconcile">Reconcile</button><a class="btn" href="#/mission/' + m.id + '">Open evidence</a></span></span>' +
      '<span class="rp-badge tone-operator">Operator</span></li>');
    $('#rp-rows').innerHTML = list.join('');
  }

  function renderShared() {
    $('#s-shared [data-sentence]').textContent = sentence();
    sharedStage.setScene(sharedScene);
    renderSharedPanel();
  }

  function renderSharedPanel() {
    $$('[data-stab]').forEach(function (b) { b.setAttribute('aria-selected', String(b.getAttribute('data-stab') === sharedTab)); });
    var box = $('#s-panel');
    if (sharedTab === 'content') {
      box.innerHTML = '<ul class="rowlist"><li><span>Project files</span><span>12 items</span></li><li><span>Notes</span><span>34 items</span></li><li><span>Agent logs</span><span>28 items</span></li><li><span>Build outputs</span><span>18 items</span></li><li><span>Related content</span><span>156 items</span></li></ul><p class="small">Fixture counts. The same records, device permissions apply.</p>';
    } else if (sharedTab === 'relations') {
      box.innerHTML = '<ul class="rowlist">' + projects.map(function (p) {
        var n = missions.filter(function (m) { return m.project === p.id; }).length;
        return '<li><span><span class="pdot" style="--hue:' + p.hue + '"></span>' + esc(p.name) + '</span><span>orchestrated, ' + n + ' missions</span></li>';
      }).join('') + '</ul><p class="small">Relations are fixture text. Core supplies the real ones.</p>';
    } else {
      box.innerHTML = '<dl class="kv"><dt>Type</dt><dd>Core system</dd><dt>Status</dt><dd>Verified</dd><dt>Updated</dt><dd>Today, 10:24</dd><dt>Items</dt><dd>248</dd><dt>Agents</dt><dd>2 active</dd><dt>Linked projects</dt><dd>3</dd></dl>' +
        '<p class="kicker ev-head">Evidence</p><ul class="rowlist ev-rows"><li><span>Project files</span><span>12 items</span></li><li><span>Notes</span><span>34 items</span></li><li><span>Agent logs</span><span>28 items</span></li><li><span>Build outputs</span><span>18 items</span></li><li><span>Related content</span><span>156 items</span></li></ul><p class="small">Same records, device permissions apply.</p>';
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
  function refreshNow() { nowStage.relayout(); renderRail(); renderMoreChips(); renderNeeds(); }

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
    var li = addMsg('card', '<p class="card-t">Start and plan ' + esc(m.title) + '?</p>' +
      '<div class="row"><button type="button" class="btn" data-card="start">Start</button><button type="button" class="btn" data-card="keep">Keep as mission</button></div>');
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
      '<label class="promote"><input type="checkbox" data-promote> <span>Promote to project memory (off)</span></label>');
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
  addMsg('you', '<p>Open a mission in Notes: Export backup</p>');
  addMsg('arch', '<p>Mission created in Notes. Start it when you like.</p>');
  startCard(find('m-read'));

  document.addEventListener('submit', function (e) {
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
    var on = e.target.checked, label = e.target.parentNode.querySelector('span');
    label.textContent = on ? 'Promote to project memory (on)' : 'Promote to project memory (off)';
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
    var tab = e.target.closest('[data-mtab]');
    if (tab) { missionTab = tab.getAttribute('data-mtab'); return renderMissionPanel(); }
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

  function openDetail(id) {
    var m = find(id);
    if (!m) return;
    var waiting = m.state === 'waiting', p = plans[m.id];
    sheetFor(
      '<p class="sheet-state st-' + m.state + '">' + esc(stateLine(m)) + '</p>' +
      '<h2 id="now-sheet-h" tabindex="-1">' + esc(m.title) + '</h2>' +
      '<p class="sheet-line sheet-proj"><span class="lbl-line">Project</span> ' + esc(projectOf(m.project).name) + ' · ' + esc(m.branch) + '</p>' +
      '<p class="sheet-line"><span class="lbl-line">What</span> ' + esc(m.what) + '</p>' +
      (waiting && p ? '<p class="sheet-line"><span class="lbl-line">Why</span> ' + esc(p.why) + '</p>' +
        '<p class="sheet-line"><span class="lbl-line">Core (fixture text)</span> ' + esc(p.approve) + '</p>' : '') +
      '<div class="sheet-actions">' +
      '<a class="btn primary" href="' + (waiting ? '#/plan/' : '#/mission/') + m.id + '">' + (waiting ? 'Open decision' : 'Open mission') + '</a>' +
      '<button type="button" class="btn" data-act="now-sheet-close">Close</button></div>');
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
    if (!isNarrow()) { box.innerHTML = ''; return; }
    // Every project keeps its name on its hull. Past five projects, the farthest share one named list chip.
    if (isNarrow()) { box.innerHTML = '<button type="button" class="chip-btn" data-act="open-list">' + (projects.length - 1) + ' more projects</button>'; return; }
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
    else if (name === 'feed-close') $('#feed').classList.remove('is-open');
  });

  // Typing in the bar opens the conversation as a sheet on the phone.
  // Opening the conversation on the phone shows the newest Start card first, with the replies below it.
  function openFeed() {
    var feed = $('#feed');
    feed.classList.add('is-open');
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
  });

  /* ---------- Terminal: the same fixture records as a text screen. Simulated. ---------- */

  // Round 10c layout, measured on terminal-1-overview-v2.png (1600 x 900): a cell is 13 design px wide, a text
  // line sits 33 px below the last (two grid units of 16.5 px), and the grid has 50 units. Text lines use even
  // units; the overview also draws connectors and box edges on odd units.
  var term = { screen: 'overview', sel: 0, mid: 'm-search', cols: 120, rows: 40, plain: false, help: false, input: null, filter: '', step: null };
  var GLYPH_T = { waiting: '◇', running: '*', done: '+', idle: 'o' };
  var BOX = { tl: '┌', tr: '┐', bl: '└', br: '┘', h: '─', v: '│' };
  var STATE_CLS = { waiting: 'amber', running: 'blue', done: 'green', idle: 'dim' };
  var UNITS = 53, UNIT_PX = 16.5, CELL = 13;
  var KEY_U = 45, TELL_U = 48, STATUS_U = 50;
  term.color = !/[?&]nocolor/.test(location.search);

  // A character grid. Each cell holds a character and an optional colour class. The classes sit on the grid, so
  // NO_COLOR and ?nocolor drop them and the characters read the same.
  function Grid(w, h) {
    var rows = [], cls = [];
    for (var y = 0; y < h; y++) {
      rows.push(new Array(w + 1).join(' ').split(''));
      var c = []; for (var i = 0; i < w; i++) c.push('');
      cls.push(c);
    }
    var g = { strips: [] };
    g.put = function (x, y, s, c) {
      for (var i = 0; i < s.length; i++) {
        if (x + i >= 0 && x + i < w && y >= 0 && y < h) { rows[y][x + i] = s.charAt(i); cls[y][x + i] = c || ''; }
      }
    };
    g.rule = function (y, x0, x1, c) { if (x1 >= x0) g.put(x0, y, new Array(x1 - x0 + 2).join('─'), c); };
    g.vert = function (x, y0, y1, c) { for (var y = y0; y <= y1; y++) g.put(x, y, '│', c); };
    // Slashed-corner box: '/' above the top-left corner, '\' above the top-right, the title on the top edge,
    // '\' and '/' on the bottom edge.
    g.hull = function (x, top, right, bottom, title) {
      g.put(x, top - 1, '/'); g.put(right, top - 1, '\\');
      g.put(x, top, '│'); g.put(right, top, '│');
      var t = ' ' + title + ' ';
      g.put(x + 1, top, t);
      g.rule(top, x + 1 + t.length, right - 2);
      g.vert(x, top + 1, bottom - 1); g.vert(right, top + 1, bottom - 1);
      g.put(x, bottom, '\\'); g.rule(bottom, x + 1, right - 1); g.put(right, bottom, '/');
    };
    g.box = function (x, y, bw, bh, title) {
      var t = title ? ' ' + title + ' ' : '';
      g.put(x, y, BOX.tl + t + new Array(Math.max(0, bw - 2 - t.length) + 1).join(BOX.h) + BOX.tr);
      for (var i = 1; i < bh - 1; i++) { g.put(x, y + i, BOX.v); g.put(x + bw - 1, y + i, BOX.v); }
      g.put(x, y + bh - 1, BOX.bl + new Array(bw - 1).join(BOX.h) + BOX.br);
    };
    g.lines = function () {
      return rows.map(function (r, y) { return { text: r.join(''), cls: cls[y], strip: g.strips.indexOf(y) >= 0 }; });
    };
    return g;
  }

  function termOrder() {
    var out = [];
    projects.forEach(function (p) { missions.forEach(function (m) { if (m.project === p.id) out.push(m); }); });
    return out.filter(function (m) { return !term.filter || (m.title + ' ' + projectOf(m.project).name).toLowerCase().indexOf(term.filter.toLowerCase()) >= 0; });
  }
  function selected() { var o = termOrder(); return o[Math.min(term.sel, o.length - 1)] || missions[0]; }
  function tword(m) { return STATE[m.state].word; }
  function chainFor(m) {
    if (m.state === 'waiting') return [];
    return m.exec ? ['Verifying', 'Codex', 'Verification', 'Results'] : [];
  }
  // Text line n sits on unit 2n.
  function T(n) { return n * 2; }

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

  function header(g, w) {
    g.put(0, 0, 'ARCHEUS');
    g.put(11, 0, '●', 'green');
    g.put(13, 0, 'Not stopped · accepts new work');
    g.put(w - 'CONCEPT FIXTURE'.length - 1, 0, 'CONCEPT FIXTURE', 'dim');
  }

  function needsLine(g, y) {
    g.put(0, y, count('waiting') + ' ');
    g.put(2, y, 'needs you', 'amber');
    g.put(11, y, ' · ');
    g.put(14, y, count('running') + ' ');
    g.put(16, y, 'verifying', 'blue');
  }

  function overview120(g) {
    var arch = projects[0], sel = selected();
    var inArch = missions.filter(function (m) { return m.project === arch.id; });
    var fa = inArch.filter(function (m) { return m.state === 'waiting'; })[0];
    var fb = inArch.filter(function (m) { return m.state === 'running'; })[0];
    var rest = inArch.length - [fa, fb].filter(Boolean).length;
    header(g, 120);
    needsLine(g, T(1));
    g.put(60, T(2), '*');
    g.put(56, T(3), 'ARCHEUS');
    g.put(56, 8, '/'); g.put(63, 8, '\\');
    g.put(55, 9, '/'); g.put(64, 9, '\\');
    g.hull(35, 12, 82, 36, arch.name);
    g.vert(58, 14, 34);
    if (fa) {
      if (sel === fa) g.put(36, 16, '>');
      g.put(38, 16, '◇', 'amber'); g.put(41, 16, fa.title, 'amber');
      g.vert(45, 18, 18);
      g.put(42, 20, fa.stateText, 'amber');
    }
    if (fb) {
      if (sel === fb) g.put(60, 16, '>');
      g.put(62, 16, '*', 'blue'); g.put(65, 16, fb.title, 'blue');
      chainFor(fb).forEach(function (step, i) {
        var y = 20 + i * 4;
        g.vert(70, y - 2, y - 2);
        if (step === 'Codex') { g.put(67, y, 'Δ'); g.put(69, y, 'Codex'); return; }
        var cl = step === 'Verifying' || step === 'Verification' || step === 'Results' ? 'blue' : '';
        g.put(Math.round(69.5 - step.length / 2), y, step, cl);
      });
    }
    if (rest > 0) g.put(37, 34, '+' + rest + ' more', 'dim');
    g.hull(92, 16, 114, 22, projects[1].name);
    var nn = missions.filter(function (m) { return m.project === projects[1].id; }).length;
    if (nn) g.put(95, 18, nn + ' missions', 'dim');
    g.hull(92, 26, 114, 32, projects[2].name);
    // Dashed links from the hull edge to the two side boxes, ending in a short tick.
    [[84, 13], [86, 14], [88, 16], [90, 17]].forEach(function (p) { g.put(p[0], p[1], '\\', 'dim'); });
    g.put(91, 18, '─', 'dim');
    [[84, 22], [86, 24], [88, 26], [90, 28]].forEach(function (p) { g.put(p[0], p[1], '\\', 'dim'); });
    g.put(91, 29, '─', 'dim');
    g.put(0, 39, 'Why:', 'amber');
    g.put(5, 39, ' ' + (fa && plans[fa.id] ? plans[fa.id].why : 'nothing waiting.'));
    g.put(0, 41, '[Enter] Open decision', 'dim');
  }

  function overview80(g) {
    header(g, 80);
    needsLine(g, T(1));
    var sel = selected(), y = 2;
    projects.forEach(function (p, pi) {
      var ms = missions.filter(function (m) { return m.project === p.id; });
      if (pi > 0) { g.put(0, T(y), p.name + ' · ' + ms.length + ' missions', 'dim'); y += 2; return; }
      g.box(0, T(y), 80, 2 * (ms.length + 1), p.name);
      ms.forEach(function (m, i) {
        g.put(2, T(y + 1 + i), (sel === m ? '> ' : '  ') + GLYPH_T[m.state] + ' ' + m.title, STATE_CLS[m.state]);
      });
      y += ms.length + 2;
    });
    var fa = missions.filter(function (m) { return m.state === 'waiting'; })[0];
    g.put(0, T(y), 'Why:', 'amber');
    g.put(5, T(y), ' ' + (fa && plans[fa.id] ? plans[fa.id].why : 'nothing waiting.'));
  }

  function termFrame(g, keys) {
    g.put(0, KEY_U, keys);
    g.put(0, TELL_U, term.input ? (term.input.mode + ' ' + term.input.text + '_') : '> Tell Archeus...', term.input ? '' : 'dim');
    g.strips.push(TELL_U);
    g.put(0, STATUS_U, term.step ? 'Confirm this decision? Type y to confirm; any other key cancels.' : 'SIMULATED: fake data, nothing sent to Core. ' + (term.filter ? 'Filter: ' + term.filter + '.' : ''), 'dim');
    return g;
  }

  function termHelp(w) {
    var g = Grid(w, UNITS);
    header(g, w);
    g.put(0, T(1), 'HELP  keys');
    var keys = ['j / k or arrows   select a mission', 'Enter               open the mission (or decision)', 'r                   review plan (decision)', 'p                   replay', 'm                   mission', 't                   tell (not sent)',
      's                   stop (double press, nothing stops)', 'b or Esc            back', '/                   filter by name', ':                   jump to project, mission or replay', 'L                   plain-line mode on and off', '?                   this help'];
    keys.forEach(function (k, i) { g.put(3, T(3 + i), k); });
    return termFrame(g, '? close help');
  }

  function termMissionGrid(w) {
    var m = find(term.mid) || find('m-date'), g = Grid(w, UNITS), p = projectOf(m.project);
    header(g, w);
    g.put(0, T(1), 'Overview / ' + p.name + ' / ' + m.title);
    var head = '* ARCHEUS - member - ' + p.name + ' - member - ';
    g.put(0, T(3), head);
    g.put(head.length, T(3), 'o ' + m.title, 'blue');
    if (m.exec) {
      g.put(head.length + 2, T(4) + 1, '\\');
      g.put(head.length + 5, T(5), '^ Codex - execution', 'blue');
    }
    g.put(0, T(6), m.title + '   ' + m.branch);
    g.put(0, T(7), tword(m) + (m.exec ? ' · 1 live execution' : ''), STATE_CLS[m.state]);
    g.put(0, T(9), 'Understand / Plan / Approve / Run / [Verify] / Review');
    g.put(0, T(11), 'Latest record: ' + m.latest);
    g.put(0, T(12), 'Task: ' + (m.task === 'none' ? 'not recorded' : m.task));
    g.put(0, T(14), '> Activity');
    g.put(0, T(15), '  Plan');
    g.put(0, T(16), '  Why / recorded relations');
    var y = 18, plan = plans[m.id];
    g.put(0, T(y), 'Current phase  ' + (m.phase < 0 ? 'Not started' : m.phase === 6 ? 'Complete' : PHASES[m.phase]), 'dim'); y++;
    m.log.forEach(function (l) { if (T(y) < KEY_U - 1) { g.put(2, T(y), '- ' + l, 'dim'); y++; } });
    if (plan) {
      y++;
      g.put(0, T(y), 'Plan v' + plan.version + ', ' + plan.tasks.length + ' tasks'); y++;
      plan.tasks.forEach(function (t, i) { if (y < 22) { g.put(2, T(y), (i + 1) + '. ' + t.text); y++; } });
    }
    return termFrame(g, 'b back  p replay  r review  t tell  s stop  ? help  : jump  / filter');
  }

  function termDecisionGrid(w) {
    var m = find(term.mid) || find('m-search'), p = plans[m.id], g = Grid(w, UNITS);
    header(g, w);
    g.put(0, T(1), 'Overview / ' + projectOf(m.project).name + ' / ' + m.title);
    if (!p) { g.put(0, T(3), 'No plan is recorded for ' + m.title + '.'); return termFrame(g, 'b back  ? help'); }
    g.put(0, T(2), '*  ARCHEUS');
    g.put(12, T(2), 'o ' + m.title, 'amber');
    g.put(33, T(2), '! NEEDS YOU', 'amber');
    g.put(0, T(4), 'Review plan v' + p.version + ' | ' + m.branch);
    g.put(0, T(5), 'What: ' + m.what);
    g.put(0, T(6), 'Why:', 'amber'); g.put(5, T(6), ' ' + p.why);
    g.put(0, T(7), 'Consequence: use the exact consequence recorded by Core.');
    g.put(0, T(8), 'A decided approval cannot be changed. No Undo is available.');
    g.put(0, T(10), 'Tasks', 'dim');
    p.tasks.forEach(function (t, i) { g.put(2, T(11 + i), (i + 1) + '. ' + t.text); });
    g.put(0, T(15), '  a approve: ' + p.approve, 'dim');
    g.put(0, T(16), '  c request changes: ' + p.request, 'dim');
    g.put(0, T(17), '  x reject: ' + p.reject, 'dim');
    if (term.step === 'approve') {
      g.put(0, T(19), 'Approve selected. Confirm only after reading current plan.', 'amber');
      g.put(0, T(20), 'Confirm this decision? Type y to confirm; any other key cancels.', 'amber');
    }
    return termFrame(g, term.step ? 'y confirm   any other key cancels' : 'a approve  c changes  x reject  b back  ? help');
  }

  function termReplayGrid(w) {
    var m = find(term.mid) || find('m-date'), rows = REPLAY[m.id] || [], g = Grid(w, UNITS);
    header(g, w);
    g.put(0, T(1), 'Overview / ' + projectOf(m.project).name + ' / Replay ' + m.title + ' (sample data)');
    var n = 4;
    rows.forEach(function (r, i) {
      var y = T(n), hot = r.tone === 'uncertain' || r.tone === 'needs-you' ? 'amber' : r.tone === 'verified' ? 'green' : '';
      g.put(4, y, r.mark === 'check' ? '+' : r.mark === 'diamond' ? '◇' : '●', hot);
      g.put(8, y, r.time, 'dim');
      g.put(15, y, '[' + r.badge + ']', hot);
      g.put(28, y, r.title);
      g.put(28, y + 2, r.sub, 'dim');
      if (i < rows.length - 1) g.vert(4, y + 1, y + 5, 'dim');
      n += 3;
    });
    g.put(0, T(n), new Array(w - 1).join('┄'), 'dim');
    g.put(4, T(n + 1), '●', 'dim');
    g.put(8, T(n + 1), '--:--', 'dim');
    g.put(15, T(n + 1), '[Operator]', 'dim');
    g.put(28, T(n + 1), 'Reconcile');
    g.put(39, T(n + 1), 'Record what happened on the remote. Nothing is pushed here.', 'dim');
    g.put(0, T(n + 2), 'Not every external effect can be reversed.', 'dim');
    return termFrame(g, 'b back  t tell  s stop  ? help');
  }

  // Each run of equal colour classes becomes one span. NO_COLOR and ?nocolor drop the classes; the text stays.
  function gridHTML(lines) {
    return lines.map(function (ln) {
      var text = ln.strip ? ln.text : ln.text.replace(/\s+$/, ''), cls = ln.cls, html = '', i = 0;
      while (i < text.length) {
        var c = term.color ? cls[i] : '', j = i;
        while (j < text.length && (term.color ? cls[j] : '') === c) j++;
        var seg = esc(text.slice(i, j));
        html += c ? '<span class="' + c + '">' + seg + '</span>' : seg;
        i = j;
      }
      return ln.strip ? '<span class="bar">' + html + '</span>' : html;
    }).join('\n');
  }

  // Scales the design (38 px left margin, 13 px cells, 16.5 px units) to the wrapper. The font size is solved from
  // the face's real advance, so every cell is exactly 13 design px whatever monospace face the viewer has.
  function fitTerm(pre) {
    var wrap = pre.parentNode, cols = Number(pre.getAttribute('data-cols')) || 120;
    var design = 38 + cols * CELL + 2;
    var k = Math.min(1.25, Math.max(0.75, wrap.clientWidth / design));
    var probe = document.createElement('span');
    probe.style.cssText = 'position:absolute;visibility:hidden;white-space:pre;font-size:100px';
    probe.textContent = 'MMMMMMMMMM';
    pre.appendChild(probe);
    var em = probe.getBoundingClientRect().width / 10 / 100;
    pre.removeChild(probe);
    pre.style.fontSize = (CELL * k / em) + 'px';
    pre.style.lineHeight = ((term.plain ? 33 : UNIT_PX) * k) + 'px';
    pre.style.width = (design * k) + 'px';
    pre.style.paddingLeft = (38 * k) + 'px';
    pre.style.paddingTop = (12 * k) + 'px';
    wrap.style.paddingTop = (39 * k) + 'px';
  }

  function renderTerm() {
    var w = term.cols, g;
    var pre = $('#term');
    pre.setAttribute('data-cols', String(w));
    if (term.plain && term.screen === 'overview' && !term.help) {
      pre.className = 'term plain';
      pre.textContent = plainOverview().join('\n');
    } else {
      if (term.help) g = termHelp(w);
      else if (term.screen === 'mission') g = termMissionGrid(w);
      else if (term.screen === 'decision') g = termDecisionGrid(w);
      else if (term.screen === 'replay') g = termReplayGrid(w);
      else {
        g = Grid(w, UNITS);
        if (w >= 100) overview120(g); else overview80(g);
        termFrame(g, w >= 100 ? 'j/k select    Enter open    b Back    p Replay    t Tell    r Review    s Stop' : 'j/k  Enter open  b back  p replay  t tell  r review  s stop');
      }
      pre.className = 'term';
      pre.innerHTML = gridHTML(g.lines());
    }
    fitTerm(pre);
    $$('[data-tsize]').forEach(function (b) { b.setAttribute('aria-pressed', String(Number(b.getAttribute('data-tsize')) === w)); });
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

  renderRail();

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
