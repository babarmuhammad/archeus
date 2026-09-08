"""Cluster inspector — one cluster, filling the frame.

    py tools/inspect_cluster.py [out.png] [--node N]

The graph scene is forty clusters at forty times the distance, and at that size
a cage, the population inside it and the beads on its surface are one grey
speck: every judgement about whether a rod reads as glass, whether a bead has a
shell, whether the interior is a haze or a few specks, is being made at a size
where none of it is visible. Six rounds of "still not high quality" came from
tuning parameters nobody could see.

So this parks the camera on one cluster and fills the frame with it. It boots
the REAL scene from `claude_sessions/web/stage.js` and overrides ONLY the
camera — no second implementation of the geometry or the shaders, because a
copy of the thing you are judging drifts from it within a day and then you are
grading the copy.

Not part of any gate: it produces a picture, and a picture needs eyes. It is
kept in tools/ rather than a scratch directory because the next person to
change these shaders will want it, and because a bench that has to be rewritten
before it can be used is a bench nobody uses.
"""
import sys, threading, pathlib
from http.server import ThreadingHTTPServer
sys.path.insert(0, r"D:\Claude")
sys.path.insert(0, r"D:\Claude\tools")
import smoke_gui                                    # noqa: E402
from claude_sessions import gui                     # noqa: E402
from playwright.sync_api import sync_playwright     # noqa: E402

OUT = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else 'cluster.png')
NODE = int(sys.argv[sys.argv.index('--node') + 1]) if '--node' in sys.argv else -1
LINK = '--link' in sys.argv

# Frame the chosen cluster: park the camera on its own axis at a distance that
# makes its radius fill ~70% of the frame height, and stop the scene's own
# camera walk. Everything else — geometry, shaders, physics — is untouched.
FRAME = """(sel) => {
  const sc = STAGE._sc, ns = sc.__nodes;
  let k = sel;
  if (k < 0) { k = 0; for (let i = 1; i < ns.length; i++) if (ns[i].r > ns[k].r) k = i; }
  const orig = sc.update;
  sc.update = f => {
    orig(f);
    // the LIVE position: the physics moves cages every frame and only u_np
    // knows where they are — nodes[] holds where they started. Read off the
    // scene's own named handle, never through scene.children[0]: that was a
    // ShaderMaterial until the scene gained a light, and then this threw once
    // per frame and the canvas went black with nothing in the console.
    const np = sc.__np[k];
    const r = ns[k].r;
    const d = r / Math.tan(27.5 * Math.PI / 180) / 0.7;
    sc.camera.position.set(np.x + d * 0.30, np.y + d * 0.16, np.z + d * 0.94);
    sc.camera.lookAt(np.x, np.y, np.z);
  };
  return {node: k, r: ns[k].r, tone: ns[k].tone};
}"""

LINK_FRAME = """(sel) => {
  // the conduit between the two largest cages: park side-on to its midpoint,
  // far enough back to see both collars
  const sc = STAGE._sc, ns = sc.__nodes;
  const u = sc.__np;
  let a = 0; for (let i = 1; i < ns.length; i++) if (ns[i].r > ns[a].r) a = i;
  let b = -1, best = 1e9;
  for (let i = 0; i < ns.length; i++) {
    if (i === a) continue;
    const d = u[i].distanceTo(u[a]);
    if (d < best) { best = d; b = i; }
  }
  const orig = sc.update;
  sc.update = f => {
    orig(f);
    const p = u[a].clone().add(u[b]).multiplyScalar(0.5);
    const ax = u[b].clone().sub(u[a]).normalize();
    const side = new THREE.Vector3(0, 0, 1).cross(ax).normalize();
    // 1.15x the span, not 0.55: at half the span the camera sits INSIDE one
    // of the two hulls it is trying to photograph the gap between.
    sc.camera.position.copy(p).addScaledVector(side, best * 1.15)
             .addScaledVector(new THREE.Vector3(0, 1, 0), best * 0.22);
    sc.camera.lookAt(p);
  };
  return {a, b, span: best};
}"""

srv = ThreadingHTTPServer(('127.0.0.1', smoke_gui.PORT), smoke_gui.H)
threading.Thread(target=srv.serve_forever, daemon=True).start()
with sync_playwright() as pw:
    br = pw.chromium.launch(args=['--use-gl=angle', '--use-angle=swiftshader',
                                  '--enable-unsafe-swiftshader',
                                  '--ignore-gpu-blocklist'])
    pg = br.new_page(viewport={'width': 1100, 'height': 1100})
    pg.on('pageerror', lambda e: print('PAGE ERROR:', e))
    pg.goto(f'http://127.0.0.1:{smoke_gui.PORT}/?k={gui.TOKEN}')
    pg.wait_for_function("window.STAGE!==undefined", timeout=15000)
    pg.evaluate("ST.world='graph';applyTheme(ST.theme)")
    pg.wait_for_timeout(1500)
    pg.evaluate("setZen(true)")
    pg.wait_for_timeout(1500)
    print(pg.evaluate(LINK_FRAME if LINK else FRAME, NODE))
    pg.wait_for_timeout(3000)
    pg.screenshot(path=str(OUT))
    br.close()
srv.shutdown()
print('wrote', OUT)
