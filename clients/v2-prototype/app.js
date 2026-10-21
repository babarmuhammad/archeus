(function () {
  'use strict';

  var TAU = Math.PI * 2;
  var reduce = window.matchMedia('(prefers-reduced-motion: reduce)');
  var STATE_WORD = { waiting: 'Needs you', running: 'Running', done: 'Done', idle: 'Idle' };
  var STATE_RANK = { waiting: 0, running: 1, idle: 2, done: 3 };
  var COLOR = {
    waiting: '#F2B544', running: '#5AA9FF', done: '#5FD08B', idle: '#A7B0BD',
    connected: '#5FD08B', recent: '#5AA9FF', future: '#8A94A3', exec: '#E6EAF0'
  };
  var PHASES = ['Understand', 'Plan', 'Approve', 'Run', 'Verify', 'Review'];
  var FREE_SLOTS = [[30, 74], [66, 76], [86, 44], [12, 48], [50, 84]];
  var PHONE_SLOTS = [[24, 48], [76, 48], [50, 70]];

  var missions = [
    { id: 'm-search', title: 'Search provenance', project: 'Archeus', branch: 'feat/search', state: 'waiting', stateText: 'Review plan', phase: 2, x: 26, y: 26, what: 'Search recorded sources and show where each result came from.', latest: 'Plan v1 waiting for your decision.', task: 'Plan v1, 3 tasks, not started.', exec: false },
    { id: 'm-date', title: 'Fix date test', project: 'Archeus', branch: 'fix/date-test', state: 'running', stateText: 'Verifying', phase: 4, x: 64, y: 26, what: 'Run the date test suite and confirm the fix.', latest: 'Tool result received.', task: 'not recorded', exec: true },
    { id: 'm-done', title: 'Write changelog', project: 'Archeus', branch: 'docs/changelog', state: 'done', stateText: 'Review passed', phase: 6, x: 22, y: 66, what: 'Summarise the merged changes for the release.', latest: 'Review passed.', task: 'none', exec: false },
    { id: 'm-index', title: 'Index notes', project: 'Notes', branch: 'feat/index', state: 'idle', stateText: 'Not started', phase: -1, x: 82, y: 70, what: 'Build an index over the notes folder.', latest: 'none recorded', task: 'none', exec: false }
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
  var current = null;
  var raf = 0;
  var lastStar = null;
  var sheetOpen = null;

  function $(sel, root) { return (root || document).querySelector(sel); }
  function $$(sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); }
  function esc(s) {
    return String(s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function find(id) { return missions.filter(function (m) { return m.id === id; })[0]; }
  function count(state) { return missions.filter(function (m) { return m.state === state; }).length; }
  function stateLine(m) { return STATE_WORD[m.state] + ' · ' + m.stateText; }
  function sorted(list) { return list.slice().sort(function (a, b) { return STATE_RANK[a.state] - STATE_RANK[b.state]; }); }
  function say(text) { $('#say').textContent = text; }
  function sentence() {
    var w = count('waiting'), r = count('running');
    if (!w && !r) return 'Nothing running. Tell Archeus what to do.';
    return w + ' needs you · ' + r + ' running';
  }
  function commentsFor(id) { return comments.filter(function (c) { return c.mission === id; }); }
  function selectedComments() { return comments.filter(function (c) { return c.mission === planId && c.carry; }); }

  function nameHtml(m, mode) {
    var t = esc(m.title);
    if (mode === 'button') return '<button type="button" class="nl-name" data-act="review" data-id="' + m.id + '">' + t + '</button>';
    if (mode === 'link') return '<a class="nl-name" href="#/mission/' + m.id + '">' + t + '</a>';
    return '<span class="nl-name">' + t + '</span>';
  }
  function labelHtml(m, mode) {
    var h = nameHtml(m, mode) + '<span class="nl-state st-' + m.state + '">' + esc(stateLine(m)) + '</span>';
    if (m.state === 'waiting' && mode === 'link') h += '<a class="nl-action" href="#/plan/' + m.id + '">Review</a>';
    return h;
  }
  function missionNode(m, x, y, mode) {
    return { kind: 'mission', state: m.state, x: x, y: y, id: m.id, label: labelHtml(m, mode) };
  }

  function nowScene() {
    var nodes = [], edges = [], groups = {};
    missions.forEach(function (m) {
      var i = nodes.length;
      nodes.push(missionNode(m, m.x, m.y, 'link'));
      edges.push([-1, i]);
      (groups[m.project] = groups[m.project] || []).push([m.x, m.y]);
      if (m.exec) {
        nodes.push({ kind: 'exec', state: 'exec', x: m.x, y: m.y + 14, label: '<span class="nl-state">Codex · execution</span>' });
        edges.push([i, nodes.length - 1]);
      }
    });
    return {
      core: { x: 50, y: 46, s: 1, label: '<span class="nl-name">ARCHEUS</span><span class="nl-state">Your projects, in context</span>' },
      hulls: Object.keys(groups).map(function (k) { return { pts: groups[k] }; }),
      nodes: nodes, edges: edges, breath: count('running') > 0
    };
  }

  function missionScene(m) {
    var nodes = [missionNode(m, 50, 42, 'text')], edges = [[-1, 0]], pts = [[50, 42]];
    if (m.exec) {
      nodes.push({ kind: 'exec', state: 'exec', x: 50, y: 78, label: '<span class="nl-name">Codex · execution</span>' });
      edges.push([0, 1]);
      pts.push([50, 78]);
    }
    return {
      core: { x: 12, y: 22, s: 0.6, label: '<span class="nl-name">ARCHEUS</span>' },
      hulls: [{ pts: pts }], nodes: nodes, edges: edges, breath: m.state === 'running'
    };
  }

  function phoneScene() {
    var list = sorted(missions).slice(0, PHONE_SLOTS.length);
    var nodes = list.map(function (m, i) {
      var n = missionNode(m, PHONE_SLOTS[i][0], PHONE_SLOTS[i][1], 'button');
      n.below = true;
      return n;
    });
    return {
      core: { x: 50, y: 14, s: 1.1, label: '<span class="nl-name">ARCHEUS</span>' },
      hulls: [{ pts: PHONE_SLOTS.slice(0, list.length) }],
      nodes: nodes,
      edges: list.map(function (m, i) { return [-1, i]; }),
      breath: count('running') > 0,
      overflow: missions.length - list.length
    };
  }

  function sharedScene() {
    var nodes = [
      { kind: 'agent', state: 'waiting', x: 18, y: 20, label: '<span class="nl-name">Planner</span><span class="nl-state st-waiting">Needs you · Search provenance</span>' },
      { kind: 'agent', state: 'running', x: 82, y: 20, label: '<span class="nl-name">Codex</span><span class="nl-state st-running">Running · Fix date test</span>' },
      { kind: 'device', state: 'connected', x: 18, y: 80, label: '<span class="nl-name">This desktop</span><span class="nl-state st-done">Connected</span>' },
      { kind: 'device', state: 'recent', x: 50, y: 86, label: '<span class="nl-name">Paired phone</span><span class="nl-state st-running">Recent</span>' },
      { kind: 'device', state: 'future', x: 82, y: 80, label: '<span class="nl-name">Other people</span><span class="nl-state st-future">Future contract, not available</span>' }
    ];
    return {
      core: { x: 50, y: 46, s: 1, label: '<span class="nl-name">ARCHEUS</span><span class="nl-state">Shared records</span>' },
      hulls: [{ pts: nodes.map(function (n) { return [n.x, n.y]; }) }],
      nodes: nodes,
      edges: nodes.map(function (n, i) { return [-1, i]; }),
      breath: count('running') > 0
    };
  }

  function addLabel(inner, x, y, html, right, below) {
    var el = document.createElement('div');
    el.className = 'node-label' + (below ? ' below' : right ? ' right' : '');
    el.innerHTML = html;
    if (below) {
      el.style.left = x + '%';
      el.style.top = 'calc(' + y + '% + 30px)';
    } else {
      el.style.top = y + '%';
      if (right) { el.style.right = (100 - x) + '%'; el.style.marginRight = '18px'; }
      else { el.style.left = x + '%'; el.style.marginLeft = '18px'; }
    }
    inner.appendChild(el);
  }

  function buildStage(stage, scene) {
    var inner = $('.stage-inner', stage);
    scene.canvas = $('canvas', inner);
    $$('.node-label', inner).forEach(function (el) { el.parentNode.removeChild(el); });
    scene.nodes.forEach(function (n) { addLabel(inner, n.x, n.y, n.label, n.x > 60, n.below); });
    var c = document.createElement('div');
    c.className = 'node-label core-label';
    c.innerHTML = scene.core.label;
    c.style.left = scene.core.x + '%';
    c.style.top = 'calc(' + scene.core.y + '% + ' + Math.round(34 * scene.core.s + 6) + 'px)';
    inner.appendChild(c);
    current = scene;
    drawScene(scene, performance.now());
    if (scene.breath) startLoop();
  }

  function drawScene(scene, t) {
    var cv = scene.canvas;
    var w = cv.clientWidth, h = cv.clientHeight, dpr = Math.min(window.devicePixelRatio || 1, 2);
    cv.width = Math.max(1, Math.round(w * dpr));
    cv.height = Math.max(1, Math.round(h * dpr));
    var g = cv.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    var m = Math.min(w, h);
    function at(x, y) { return [x / 100 * w, y / 100 * h]; }

    scene.hulls.forEach(function (hl) {
      var pts = hl.pts.map(function (q) { return at(q[0], q[1]); });
      var cx = 0, cy = 0, r = 0;
      pts.forEach(function (q) { cx += q[0]; cy += q[1]; });
      cx /= pts.length; cy /= pts.length;
      pts.forEach(function (q) { r = Math.max(r, Math.hypot(q[0] - cx, q[1] - cy)); });
      r = (r + 0.07 * m + 16) / Math.cos(Math.PI / 6);
      g.beginPath();
      for (var i = 0; i < 6; i++) {
        var a = Math.PI / 3 * i - Math.PI / 2;
        if (i === 0) g.moveTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
        else g.lineTo(cx + Math.cos(a) * r, cy + Math.sin(a) * r);
      }
      g.closePath();
      g.fillStyle = 'rgba(138,148,163,0.06)';
      g.fill();
      g.strokeStyle = 'rgba(138,148,163,0.4)';
      g.lineWidth = 1;
      g.stroke();
    });

    scene.edges.forEach(function (e) {
      var a = e[0] < 0 ? scene.core : scene.nodes[e[0]];
      var b = e[1] < 0 ? scene.core : scene.nodes[e[1]];
      var p = at(a.x, a.y), q = at(b.x, b.y);
      g.beginPath();
      g.moveTo(p[0], p[1]);
      g.lineTo(q[0], q[1]);
      g.strokeStyle = 'rgba(244,241,234,0.3)';
      g.lineWidth = 1;
      g.stroke();
    });

    var breath = scene.breath && !reduce.matches ? 1 + 0.06 * Math.sin(TAU * (t || 0) / 6000) : 1;
    var k = scene.core.s * breath;
    var c = at(scene.core.x, scene.core.y);
    g.strokeStyle = '#F4F1EA';
    for (var j = 0; j < 8; j++) {
      var ang = Math.PI / 4 * j;
      var len = (j % 2 ? 0.45 : 1) * 22 * k;
      g.lineWidth = j % 2 ? 0.8 : 1.4;
      g.beginPath();
      g.moveTo(c[0], c[1]);
      g.lineTo(c[0] + Math.cos(ang) * len, c[1] + Math.sin(ang) * len);
      g.stroke();
    }
    g.beginPath();
    g.arc(c[0], c[1], 3 * k + 1, 0, TAU);
    g.fillStyle = '#F4F1EA';
    g.fill();

    scene.nodes.forEach(function (n) {
      var p = at(n.x, n.y);
      if (n.kind === 'mission') drawMission(g, p, n.state);
      else if (n.kind === 'device') drawDevice(g, p, n.state);
      else drawTriangle(g, p, COLOR[n.state] || COLOR.exec, n.kind === 'agent');
    });
  }

  function drawMission(g, p, state) {
    var col = COLOR[state];
    g.strokeStyle = col;
    g.lineWidth = 2;
    if (state === 'waiting') {
      g.setLineDash([4, 3]);
      g.beginPath();
      g.arc(p[0], p[1], 15, 0, TAU);
      g.stroke();
      g.setLineDash([]);
    } else if (state === 'running') {
      g.lineWidth = 1;
      g.beginPath();
      g.arc(p[0], p[1], 15, 0, TAU);
      g.stroke();
      g.lineWidth = 2;
    }
    g.beginPath();
    g.arc(p[0], p[1], 9, 0, TAU);
    if (state !== 'idle') { g.fillStyle = col; g.fill(); }
    g.stroke();
    if (state === 'done') {
      g.beginPath();
      g.moveTo(p[0] - 4, p[1]);
      g.lineTo(p[0] - 1, p[1] + 3);
      g.lineTo(p[0] + 4, p[1] - 3);
      g.strokeStyle = '#0E1116';
      g.stroke();
    }
  }

  function drawTriangle(g, p, col, filled) {
    g.beginPath();
    g.moveTo(p[0], p[1] - 11);
    g.lineTo(p[0] + 10, p[1] + 7);
    g.lineTo(p[0] - 10, p[1] + 7);
    g.closePath();
    g.strokeStyle = col;
    g.lineWidth = 1.5;
    if (filled) { g.fillStyle = col; g.fill(); }
    g.stroke();
  }

  function drawDevice(g, p, state) {
    g.strokeStyle = COLOR[state];
    g.lineWidth = 1.5;
    if (state === 'future') g.setLineDash([3, 3]);
    g.strokeRect(p[0] - 12, p[1] - 9, 24, 18);
    g.setLineDash([]);
  }

  function startLoop() { if (!raf) raf = requestAnimationFrame(tick); }
  function tick(t) {
    raf = 0;
    if (!current || !current.breath || document.hidden || reduce.matches) return;
    drawScene(current, t);
    raf = requestAnimationFrame(tick);
  }
  document.addEventListener('visibilitychange', function () {
    if (!document.hidden && current && current.breath) startLoop();
  });
  window.addEventListener('resize', function () { if (current) drawScene(current, performance.now()); });
  if (reduce.addEventListener) {
    reduce.addEventListener('change', function () {
      if (current) { drawScene(current, performance.now()); if (current.breath) startLoop(); }
    });
  }

  function renderNow() {
    $('#s-now [data-sentence]').textContent = sentence();
    buildStage($('#s-now .stage'), nowScene());
    $('#now-list').innerHTML = sorted(missions).map(function (m) {
      return '<li><a href="#/mission/' + m.id + '">' + esc(m.title) + '</a>' +
        '<span class="small">' + esc(m.project) + ' · ' + esc(m.branch) + '</span>' +
        '<span class="st-' + m.state + '">' + esc(stateLine(m)) + '</span>' +
        (m.state === 'waiting' ? '<a href="#/plan/' + m.id + '">Review plan</a>' : '') + '</li>';
    }).join('');
  }

  function phaseRows(m) {
    return PHASES.map(function (name, i) {
      var mark, word, cls = '';
      if (m.phase === 6 || i < m.phase) { mark = '✓'; word = 'Done'; }
      else if (i === m.phase) { mark = '●'; word = m.state === 'waiting' ? 'Waiting for you' : 'Current'; cls = 'current'; }
      else { mark = '○'; word = 'Not reached'; }
      return '<li class="' + cls + '"><span aria-hidden="true">' + mark + '</span><span class="ph-name">' + name + '</span><span class="ph-state">' + word + '</span></li>';
    }).join('');
  }

  function renderMission(id) {
    var m = find(id) || find('m-date');
    var sec = $('#s-mission');
    $('[data-m-project]', sec).textContent = m.project;
    $('[data-m-crumb]', sec).textContent = m.title;
    $('[data-m-title]', sec).textContent = m.title;
    $('[data-m-meta]', sec).textContent = m.project + ' · ' + m.branch;
    var st = $('[data-m-state]', sec);
    st.textContent = stateLine(m);
    st.className = 'state-line st-' + m.state;
    buildStage($('.stage', sec), missionScene(m));
    $('#m-phases').innerHTML = phaseRows(m);
    $('[data-m-latest]', sec).textContent = m.latest;
    $('[data-m-task]', sec).textContent = m.task;
    $('[data-m-links]', sec).innerHTML = plans[m.id]
      ? '<a href="#/plan/' + m.id + '">Plan v' + plans[m.id].version + '</a>'
      : 'No plan recorded.';
  }

  function renderShared() {
    $('#s-shared [data-sentence]').textContent = sentence();
    buildStage($('#s-shared .stage'), sharedScene());
  }

  function closeSheet(silent) {
    var inner = $('#phone-stage .stage-inner');
    var sheet = $('#sheet');
    inner.style.transform = '';
    if (sheet.hidden) return;
    sheet.hidden = true;
    sheet.innerHTML = '';
    sheetOpen = null;
    if (!silent && lastStar && lastStar.isConnected) lastStar.focus();
  }

  function openSheet(id, el) {
    var m = find(id), node = current.nodes.filter(function (n) { return n.id === id; })[0];
    var stage = $('#phone-stage'), w = stage.clientWidth, h = stage.clientHeight, s = 1.35;
    var tx = w / 2 - s * node.x / 100 * w, ty = h * 0.4 - s * node.y / 100 * h;
    $('#phone-stage .stage-inner').style.transform = 'translate(' + tx.toFixed(1) + 'px,' + ty.toFixed(1) + 'px) scale(' + s + ')';
    var waiting = m.state === 'waiting', p = plans[m.id];
    var why = waiting && p ? p.why : 'Status: ' + stateLine(m) + '.';
    var consequence = waiting && p ? p.approve : 'Core records this run. This prototype changes nothing.';
    var sheet = $('#sheet');
    sheet.innerHTML =
      '<p class="small st-' + m.state + '">' + esc(stateLine(m)) + '</p>' +
      '<h2 id="sheet-h" tabindex="-1">' + esc(m.title) + '</h2>' +
      '<p><span class="lbl">What</span>' + esc(m.what) + '</p>' +
      '<p><span class="lbl">Why</span>' + esc(why) + '</p>' +
      '<p><span class="lbl">Core (fixture text)</span>' + esc(consequence) + '</p>' +
      '<div class="row"><a class="btn primary" href="' + (waiting ? '#/plan/' : '#/mission/') + m.id + '">' +
      (waiting ? 'Open decision' : 'Open mission') + '</a><button type="button" class="btn" data-act="close-sheet">Close</button></div>';
    sheet.hidden = false;
    sheetOpen = id;
    lastStar = el;
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
    buildStage($('#phone-stage'), sc);
  }

  function renderPlan(id) {
    var m = find(id) || find('m-search');
    planId = m.id;
    var p = plans[m.id], sec = $('#s-plan');
    if (!p) {
      $('[data-plan-title]', sec).textContent = m.title;
      $('[data-plan-meta]', sec).textContent = m.project + ' · ' + m.branch;
      $('[data-plan-why]', sec).textContent = 'No plan is recorded for this mission.';
      $('#plan-tasks').innerHTML = '';
      $('#plan-consequences').innerHTML = '';
      $('[data-plan-count]', sec).textContent = '';
      $('#plan-selected').textContent = '';
      return;
    }
    $('[data-plan-title]', sec).textContent = 'Review plan v' + p.version + ' · ' + m.title;
    $('[data-plan-meta]', sec).textContent = m.project + ' · ' + m.branch + ' · ' + stateLine(m);
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
    var slot = FREE_SLOTS[counter % FREE_SLOTS.length];
    counter++;
    missions.push({ id: 'm-new-' + counter, title: title, project: project, branch: 'not created', state: 'idle', stateText: 'Not started', phase: -1, x: slot[0], y: slot[1], what: what, latest: 'none recorded', task: 'none', exec: false });
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
    var el = e.target.closest('[data-act]');
    if (!el) return;
    var act = el.getAttribute('data-act');
    if (act === 'review') openSheet(el.getAttribute('data-id'), el);
    else if (act === 'close-sheet') closeSheet(false);
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
    if (e.key === 'Escape' && sheetOpen) closeSheet(false);
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
      addMission(text.split('\n')[0].slice(0, 48), 'Archeus', text);
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
      addMission(title.slice(0, 120), $('#m-project').value, objective);
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

  window.addEventListener('hashchange', route);
  route();

  if ('serviceWorker' in navigator && /^https?:$/.test(location.protocol)) {
    navigator.serviceWorker.register('sw.js');
  }
})();
