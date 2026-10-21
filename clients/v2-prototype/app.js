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
    done: { word: 'Done', color: '#6FD39A' },
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
    { id: 'harbor', name: 'Harbor', hue: '#7FCFC0', at: [0.25, 0.5], offs: [[-70, -84], [-156, 22], [26, 72]] },
    { id: 'notes', name: 'Notes', hue: '#E7A3AE', at: [0.8, 0.27], offs: [[-70, -30], [46, 40]] },
    { id: 'lantern', name: 'Lantern', hue: '#C7B2F0', at: [0.76, 0.8], offs: [[-54, -42], [54, 40]] }
  ];

  var missions = [
    { id: 'm-search', title: 'Search provenance', project: 'harbor', branch: 'feat/search', state: 'waiting', stateText: 'Review plan', phase: 2, glyph: 'search', what: 'Search recorded sources and show where each result came from.', latest: 'Plan v1 waiting for your decision.', task: 'Plan v1, 3 tasks, not started.', exec: false, related: [{ key: 'plan', title: 'Plan v1', sub: '3 tasks, not started', glyph: 'list', verb: 'proposes' }], log: ['Plan v1 recorded.', 'Waiting for your decision.'] },
    { id: 'm-date', title: 'Fix date test', project: 'harbor', branch: 'fix/date-test', state: 'running', stateText: 'Verifying', phase: 4, glyph: 'term', what: 'Run the date test suite and confirm the fix.', latest: 'Tool result received.', task: 'Run date suite on fix/date-test and collect the results.', exec: true, related: [{ key: 'suite', title: 'Date test suite', sub: 'Test definitions and inputs', glyph: 'doc', verb: 'uses' }, { key: 'results', title: 'Results', sub: 'Test execution outputs', glyph: 'chart', verb: 'produces' }, { key: 'verify', title: 'Verification', sub: 'Confirms behaviour', glyph: 'check', verb: 'verifies', from: 'results' }], log: ['Tool call received.', 'Tool result received.', 'Not passed tests.', 'Parsing results.', 'Proceeding to verification checks.'] },
    { id: 'm-done', title: 'Write changelog', project: 'harbor', branch: 'docs/changelog', state: 'done', stateText: 'Review passed', phase: 6, glyph: 'check', what: 'Summarise the merged changes for the release.', latest: 'Review passed.', task: 'none', exec: false, related: [], log: ['Review passed.'] },
    { id: 'm-index', title: 'Index notes', project: 'notes', branch: 'feat/index', state: 'idle', stateText: 'Not started', phase: -1, glyph: 'doc', what: 'Build an index over the notes folder.', latest: 'none recorded', task: 'none', exec: false, related: [], log: ['No activity recorded.'] },
    { id: 'm-read', title: 'Reading list export', project: 'notes', branch: 'docs/reading', state: 'done', stateText: 'Done', phase: 6, glyph: 'doc', what: 'Export the reading list as a file.', latest: 'Export completed.', task: 'none', exec: false, related: [], log: ['Export completed.'] },
    { id: 'm-map', title: 'Map relations', project: 'lantern', branch: 'feat/map', state: 'idle', stateText: 'Not started', phase: -1, glyph: 'code', what: 'Map recorded relations between notes.', latest: 'none recorded', task: 'none', exec: false, related: [], log: ['No activity recorded.'] },
    { id: 'm-export', title: 'Export graph', project: 'lantern', branch: 'fix/export', state: 'done', stateText: 'Review passed', phase: 6, glyph: 'chart', what: 'Export the graph as an image.', latest: 'Review passed.', task: 'none', exec: false, related: [], log: ['Review passed.'] }
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
  var missionTab = 'overview';
  var sharedTab = 'overview';
  var missionShown = 'm-date';

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
    return w + ' needs you, ' + r + ' running';
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
      g.beginPath(); g.arc(P[i].x, P[i].y, o.dotR || 2.2, 0, TAU); g.fill();
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

  function drawCore(g, c, t, hot, s) {
    var breath = hot && t ? 1 + 0.05 * Math.sin(t / 1000 * TAU / 6) : 1;
    var R = 150 * s * breath;
    var rg = g.createRadialGradient(c.x, c.y, 0, c.x, c.y, R);
    rg.addColorStop(0, 'rgba(239,233,218,0.22)');
    rg.addColorStop(0.45, 'rgba(239,233,218,0.05)');
    rg.addColorStop(1, 'rgba(239,233,218,0)');
    g.fillStyle = rg; g.beginPath(); g.arc(c.x, c.y, R, 0, TAU); g.fill();
    g.strokeStyle = IVORY; g.fillStyle = IVORY; g.lineCap = 'round';
    for (var i = 0; i < 16; i++) {
      var a = i * TAU / 16 + 0.05;
      var L = (i % 4 === 0 ? 96 : i % 2 === 0 ? 74 : 34) * s * breath;
      g.globalAlpha = i % 4 === 0 ? 0.95 : 0.55;
      g.lineWidth = i % 2 === 0 ? 1.2 : 0.8;
      line(g, c.x + Math.cos(a) * 6 * s, c.y + Math.sin(a) * 6 * s, c.x + Math.cos(a) * L, c.y + Math.sin(a) * L);
    }
    g.globalAlpha = 0.3; g.setLineDash([2, 5]); g.lineWidth = 1;
    g.beginPath(); g.arc(c.x, c.y, 26 * s, 0, TAU); g.stroke(); g.setLineDash([]);
    g.globalAlpha = 1; g.shadowColor = IVORY; g.shadowBlur = 22;
    g.beginPath(); g.arc(c.x, c.y, 4.5 * s, 0, TAU); g.fill();
    g.shadowBlur = 0;
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

  function nowScene(w, h) {
    var narrow = w < 640;
    var k = Math.max(0.5, Math.min(w / 1150, h / 640, 1.1));
    var sc = mk(w, h, { x: w * 0.5, y: h * 0.5 }, k, narrow);
    var shape = Math.max(0.62, Math.min(k, 1));
    projects.forEach(function (p) {
      var ms = missions.filter(function (x) { return x.project === p.id; });
      var live = ms.filter(isLive).length;
      var cx = w * p.at[0], cy = h * p.at[1];
      sc.projects.push({ id: p.id, name: p.name, hue: p.hue, x: cx, y: cy, members: ms.map(function (m) { return m.id; }), count: ms.length, live: live, active: live > 0 });
      sc.parent[p.id] = 'core';
      sc.links.push({ a: 'core', b: p.id, col: p.hue, live: live > 0, kind: 'project', hue: p.hue });
      ms.forEach(function (m, i) {
        var o = p.offs[i] || [0, 0];
        var mx = cx + o[0] * shape, my = cy + o[1] * shape;
        sc.nodes.push(nodeFor(m, mx, my, 62 * shape, p.id, true));
        sc.parent[m.id] = p.id;
        sc.links.push({ a: p.id, b: m.id, col: isLive(m) ? STATE[m.state].color : p.hue, live: isLive(m), kind: 'mission', hue: p.hue });
        if (m.exec) {
          var ex = execFor(m, mx + 74 * shape, my + 92 * shape, 30 * shape, i);
          sc.nodes.push(ex);
          sc.parent[ex.id] = m.id;
          sc.links.push({ a: m.id, b: ex.id, col: IVORY, live: ex.live, kind: 'exec', hue: IVORY });
        }
      });
    });
    return sc;
  }

  function missionScene(m, w, h) {
    var p = projectOf(m.project);
    var k = Math.max(0.7, Math.min(w / 720, 1.1));
    var sc = mk(w, h, { x: w * 0.5, y: h * 0.12 }, k, false);
    var live = isLive(m);
    sc.projects.push({ id: p.id, name: p.name, hue: p.hue, x: w * 0.2, y: h * 0.4, shape: 'octa', members: null, count: 0, live: live ? 1 : 0, active: live });
    sc.parent[p.id] = 'core';
    sc.links.push({ a: 'core', b: p.id, col: p.hue, live: live, kind: 'project', hue: p.hue, verb: 'orchestrates' });
    var mx = w * 0.56, my = h * 0.5;
    sc.nodes.push(nodeFor(m, mx, my, 84 * k, p.id, false));
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

  function phoneScene(w, h) {
    var list = sorted(missions).slice(0, 2);
    var k = Math.max(0.6, Math.min(w / 380, 1));
    var slots = [[0.27, 0.66], [0.73, 0.66]];
    var sc = mk(w, h, { x: w * 0.5, y: h * 0.26 }, k, true);
    list.forEach(function (m, i) {
      var n = nodeFor(m, w * slots[i][0], h * slots[i][1], 46 * k, 'core', true);
      sc.nodes.push(n);
      sc.parent[m.id] = 'core';
      sc.links.push({ a: 'core', b: m.id, col: isLive(m) ? STATE[m.state].color : IVORY, live: isLive(m), kind: 'mission', hue: IVORY });
    });
    sc.overflow = missions.length - list.length;
    return sc;
  }

  /* ---------- The stage: one renderer for every screen ---------- */

  function makeStage(root, opts) {
    var onPick = opts && opts.onPick ? opts.onPick : null;
    var S = {
      root: root,
      fx: $('.fx', root), sky: $('.sky', root), world: $('.world', root), card: $('.card', root),
      ctx: null, w: 0, h: 0, dpr: 1,
      src: null, scene: null, cam: null, focus: null, hover: null, cardFor: null,
      items: {}, meta: {}, verbItems: [],
      last: 0, raf: 0
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

    // Static backdrop: a starfield and a restrained ambient mesh, painted once per size.
    function paintSky() {
      var g = S.sky.getContext('2d');
      var W = S.sky.width / S.dpr, H = S.sky.height / S.dpr;
      g.setTransform(S.dpr, 0, 0, S.dpr, 0, 0);
      g.clearRect(0, 0, W, H);
      var seed = 7 + Math.round(W) * 3;
      var rnd = function () { seed = (seed * 16807) % 2147483647; return seed / 2147483647; };
      var pts = [], i, j;
      for (i = 0; i < 70; i++) pts.push({ x: rnd() * W, y: rnd() * H });
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

    function scene() { return typeof S.src === 'function' ? S.src(S.w, S.h) : S.src; }

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
        if (p.members) {
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
      g.save(); g.setLineDash([2, 8]); g.lineWidth = 1;
      [[230, 0.1], [330, 0.06]].forEach(function (o) {
        g.strokeStyle = 'rgba(239,233,218,' + o[1] + ')';
        g.beginPath(); g.ellipse(c.x, c.y, o[0] * s, o[0] * 0.62 * s, -0.12, 0, TAU); g.stroke();
      });
      g.restore();

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
        if (!p.members) return;
        var ring = [];
        p.members.forEach(function (id) {
          var q = pos[id], halo = S.items[id] ? S.items[id].r * s + 46 * s : 60 * s;
          for (var j = 0; j < 8; j++) ring.push({ x: q.x + Math.cos(j * TAU / 8) * halo, y: q.y + Math.sin(j * TAU / 8) * halo });
        });
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
        if (it) { it.cx = cc.x; it.cy = cc.y; it.hr = hr + 6; it.pt = { x: anchor.x + dx * 10, y: anchor.y + dy * 10 }; it.r = 0; }
        g.save();
        g.beginPath(); hull.forEach(function (v, j) { if (j) g.lineTo(v.x, v.y); else g.moveTo(v.x, v.y); }); g.closePath();
        g.fillStyle = rgba(p.hue, lit ? 0.08 : 0.035); g.fill();
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
        var lit = !!(H[l.a] && H[l.b]);
        g.save();
        if (lit) {
          g.strokeStyle = l.col; g.globalAlpha = 0.45; g.lineWidth = 3.2 * Math.min(1.2, s);
          if (l.live) { g.shadowColor = l.col; g.shadowBlur = 16; }
          line(g, a.x, a.y, b.x, b.y);
          g.shadowBlur = 0; g.globalAlpha = 0.95; g.lineWidth = 1.4;
          g.setLineDash(l.dash ? [2, 6] : []);
          line(g, a.x, a.y, b.x, b.y);
          g.setLineDash([]);
          if (l.live && !reduce.matches) {
            var u = ((t / 1800) + idx * 0.31) % 1;
            g.fillStyle = '#FFF6E0'; g.shadowColor = l.col; g.shadowBlur = 12; g.globalAlpha = 1;
            g.beginPath(); g.arc(a.x + (b.x - a.x) * u, a.y + (b.y - a.y) * u, 2.6, 0, TAU); g.fill();
          }
        } else {
          g.strokeStyle = 'rgba(239,233,218,' + (l.dash ? 0.1 : 0.16) + ')'; g.lineWidth = 0.8;
          if (l.dash) g.setLineDash([3, 5]);
          line(g, a.x, a.y, b.x, b.y);
        }
        g.restore();
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

      // Figures: receding first, lit last.
      var order = sc.nodes.slice().sort(function (a, b) { return (H[a.id] ? 1 : 0) - (H[b.id] ? 1 : 0); });
      order.forEach(function (n, idx) {
        var q = pos[n.id], lit = !!H[n.id], R = n.r * s;
        var rot = { y: n.seed * TAU + anim * (n.state === 'running' ? 0.00055 : 0.00022), x: 0.42 + 0.14 * Math.sin(anim * 0.00025 + n.seed * 7) };
        var alpha = lit || n.live ? 1 : n.kind === 'device' || n.kind === 'record' ? 0.55 : 0.5;
        var col = STATE[n.state] ? STATE[n.state].color : IVORY;
        if (n.kind === 'mission' || n.kind === 'record') {
          if (n.kind === 'mission' && n.state === 'waiting') {
            g.save(); g.strokeStyle = col; g.lineWidth = 1.2; g.setLineDash([4, 5]);
            g.lineDashOffset = -anim / 60; g.globalAlpha = 0.9;
            g.beginPath(); g.arc(q.x, q.y, R * 1.2, 0, TAU); g.stroke(); g.restore();
          }
          drawSolid(g, n.solid, q.x, q.y, R, rot, col, { alpha: alpha, wash: true, glow: lit, glyph: n.glyph, inner: true, dotR: lit ? 2.6 : 2.1 });
        } else if (n.kind === 'exec' || n.kind === 'agent') {
          drawSolid(g, n.solid, q.x, q.y, R, rot, n.kind === 'exec' ? IVORY : col, { alpha: n.kind === 'exec' ? 0.9 : 1, wash: true, glow: lit, glyph: n.glyph, dotR: 2.4 });
        } else if (n.kind === 'device') {
          drawSolid(g, n.solid, q.x, q.y, R, rot, col, { alpha: 0.85, dash: n.dash ? [3, 3] : [], glyph: n.glyph, dotR: 1.8, lw: 1.2 });
        }
        if (n.kind === 'mission' || n.kind === 'agent' || n.kind === 'exec') {
          if (n.kind === 'mission') drawBadge(g, n.state, q.x - R * 0.78, q.y - R * 0.82, anim, !reduce.matches);
          if (n.kind === 'agent') drawBadge(g, n.state, q.x - R * 0.9, q.y - R * 0.86, anim, !reduce.matches);
        }
        var it = S.items[n.id];
        if (it) { it.cx = q.x; it.cy = q.y; it.hr = R + 10; it.pt = q; it.r = R; }
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
        core.lbl.style.transform = 'translate(' + (c.x - core.tw / 2).toFixed(1) + 'px,' + (c.y + 62 * s).toFixed(1) + 'px)';
        placed.push({ x0: c.x - core.tw / 2, y0: c.y + 62 * s, x1: c.x + core.tw / 2, y1: c.y + 62 * s + core.th });
      }
      var order = sc.projects.map(function (p) { return p.id; });
      sc.nodes.slice().sort(function (a, b) {
        var ra = a.kind === 'mission' ? RANK[a.state] : 4, rb = b.kind === 'mission' ? RANK[b.state] : 4;
        return ra - rb;
      }).forEach(function (n) { order.push(n.id); });
      var dirs = candidatesFor(sc);

      order.forEach(function (id) {
        var it = S.items[id];
        if (!it || !it.lbl || !it.pt) return;
        var pt = it.pt, off = it.r + 12;
        var ox = pt.x - c.x, oy = pt.y - c.y, len = Math.hypot(ox, oy) || 1;
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
          for (var k = 0; k < placed.length; k++) if (overlaps(bx, placed[k], 8)) cost += 500;
          circles.forEach(function (ci) { if (ci.id !== id && circleHitsBox(ci.x, ci.y, ci.r, bx)) cost += 300; });
          if (!best || cost < best.cost) best = { cost: cost, cand: cands[i], box: bx };
          if (cost === 0) break;
        }
        var box = best.box, bw = box.x1 - box.x0, bh = box.y1 - box.y0;
        var sx = Math.min(Math.max(box.x0, 8), S.w - bw - 8), sy = Math.min(Math.max(box.y0, 8), S.h - bh - 8);
        box = { x0: sx, y0: sy, x1: sx + bw, y1: sy + bh };
        placed.push(box);
        var quiet = sc.compact && it.kind === 'mission' && !(sc.nodes.some(function (n) { return n.id === id && n.live; })) && S.hover !== id;
        it.lbl.className = it.cls + ' d-' + best.cand.d + (quiet ? ' quiet' : '');
        it.lbl.style.transform = 'translate(' + box.x0.toFixed(1) + 'px,' + box.y0.toFixed(1) + 'px)';
      });
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
        var mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
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
      S.world.innerHTML = '';
      S.items = {}; S.meta = {}; S.verbItems = [];
      S.card.hidden = true; S.cardFor = null;
      S.items.core = addLabel('core', { cls: 'lbl core', kicker: '', title: 'Archeus', sub: 'Core connected', kind: 'core' });
      sc.projects.forEach(function (p) {
        var live = p.members ? sc.nodes.filter(function (n) { return p.members.indexOf(n.id) >= 0 && n.live; }).length : p.live;
        var sub = (p.count || (p.members ? p.members.length : 0)) + ' missions, ' + live + ' live';
        addLabel(p.id, { cls: 'lbl project', kicker: 'Project', title: p.name, sub: sub, kind: 'project' });
        if (p.members) addHit(p.id, { aria: p.name + ', ' + sub, kind: 'project', meta: { kicker: 'Project', title: p.name, lines: [sub] } });
        else S.items[p.id].hit = null;
      });
      sc.nodes.forEach(function (n) {
        var st = n.st, sub = n.detail || n.sub;
        var subCls = n.kind === 'mission' ? 'st-' + n.state : '';
        var action = n.kind === 'mission' && n.state === 'waiting' ? { href: '#/plan/' + n.id, text: 'Review', aria: 'Review plan for ' + n.title } : null;
        addLabel(n.id, { cls: 'lbl ' + n.kind, kicker: n.kicker + (n.kind === 'mission' ? '' : ''), title: n.title, sub: st ? st + (sub ? ' · ' + sub : '') : sub, subCls: subCls, kind: n.kind, action: action });
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
        S.verbItems.push({ el: lbl, a: l.a, b: l.b });
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
    S.setHover = setHover;
    S.relayout = relayout;
    S.kick = kick;
    return S;
  }

  /* ---------- Stages and screens ---------- */

  var nowStage = makeStage($('#now-stage'), {
    onPick: function (id, kind) {
      if (kind === 'project') location.hash = '#/now/' + id;
      else location.hash = '#/mission/' + id;
    }
  });
  var missionStage = makeStage($('#mission-stage'), {
    onPick: function (id, kind) { if (kind === 'project') location.hash = '#/now/' + id; }
  });
  var sharedStage = makeStage($('#shared-stage'));
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
    $('#now-overview').hidden = true;
    $$('#rail-projects a').forEach(function (a) { a.classList.remove('on'); });
    $('#now-list').innerHTML = sorted(missions).map(function (m) {
      return '<li><a href="#/mission/' + m.id + '">' + esc(m.title) + '</a>' +
        '<span class="row-meta">' + esc(projectOf(m.project).name) + ' · ' + esc(m.branch) + '</span>' +
        '<span class="row-state st-' + m.state + '">' + esc(stateLine(m)) + '</span>' +
        (m.state === 'waiting' ? '<a class="btn review" href="#/plan/' + m.id + '">Review plan</a>' : '') + '</li>';
    }).join('');
    if (pid && projectOf(pid)) zoomTo(pid);
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

  function renderShared() {
    $('#s-shared [data-sentence]').textContent = sentence();
    sharedStage.setScene(sharedScene);
    renderSharedPanel();
  }

  function renderSharedPanel() {
    $$('[data-stab]').forEach(function (b) { b.setAttribute('aria-selected', String(b.getAttribute('data-stab') === sharedTab)); });
    var box = $('#s-panel');
    if (sharedTab === 'content') {
      box.innerHTML = '<dl class="kv"><dt>Project files</dt><dd>12 items</dd><dt>Notes</dt><dd>34 items</dd><dt>Agent logs</dt><dd>28 items</dd><dt>Build outputs</dt><dd>18 items</dd><dt>Related content</dt><dd>156 items</dd></dl>';
    } else if (sharedTab === 'relations') {
      box.innerHTML = '<dl class="kv"><dt>Harbor</dt><dd>linked, 3 missions</dd><dt>Notes</dt><dd>linked, 2 missions</dd><dt>Lantern</dt><dd>linked, 2 missions</dd></dl><p class="small">Relations are fixture text. Core supplies the real ones.</p>';
    } else {
      box.innerHTML = '<dl class="kv"><dt>Type</dt><dd>Core system</dd><dt>Status</dt><dd>Verified</dd><dt>Updated</dt><dd>Today, 10:24</dd><dt>Items</dt><dd>248</dd><dt>Agents</dt><dd>2 active</dd><dt>Linked projects</dt><dd>3</dd></dl>' +
        '<p class="kicker">Evidence</p><p class="small">Same records, device permissions apply.</p>';
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
    counter++;
    missions.push({ id: 'm-new-' + counter, title: title, project: project, branch: 'not created', state: 'idle', stateText: 'Not started', phase: -1, glyph: 'doc', what: what, latest: 'none recorded', task: 'none', exec: false, related: [], log: ['Created on this page only.'] });
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
      addMission(text.split('\n')[0].slice(0, 48), 'harbor', text);
      $('#tell-text').value = '';
      location.hash = '#/now';
      say('Fake: a star was added to Harbor on this page only. Nothing was sent or started.');
    } else if (f.id === 'mission-form') {
      e.preventDefault();
      var title = $('#m-title').value.trim();
      if (!title) {
        $('#m-error').textContent = 'Give the mission a title.';
        return $('#m-title').focus();
      }
      $('#m-error').textContent = '';
      var objective = $('#m-objective').value.trim() || 'No objective given.';
      var proj = $('#m-project').value.toLowerCase();
      addMission(title.slice(0, 120), proj, objective);
      location.hash = '#/now';
      say('Fake: "' + title + '" was added as idle in ' + $('#m-project').value + '. Nothing was created in Core.');
    }
  });

  var SCREENS = {
    now: renderNow,
    mission: function (id) { renderMission(id); },
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
