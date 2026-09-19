/* Background canvas behind the page. Everything it draws is masked out of the content column and
   is visible only through a lens around the pointer, so nothing shows unless a visitor plays.
   Dark: a small lens reveals a hidden geometry (weak-lensing cartoons over a cosmic web) that warps
   a square grid; a click drops a new lens into it and sends out a wavefront. Light: a larger lens
   reveals a flat grid, and a click draws a labelled bubble-chamber reaction inside it. Nothing runs
   when reduced motion is requested. */
(function () {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  var canvas = document.getElementById("bg"), main = document.querySelector("main");
  if (!canvas || !main) return;
  var ctx = canvas.getContext("2d"), root = document.documentElement;
  var hover = matchMedia("(hover: hover)").matches;
  var W = 0, H = 0, mouse = { x: -1e4, y: -1e4 }, fx = [], pending = false, col = { l: 0, r: 0 };
  var R = 160, RL = 230, G = 40, EDGE = 48;  /* lens radius dark / light, grid spacing, soft edge of the column mask */

  function dark() { return root.getAttribute("data-theme") === "dark"; }
  function cssVar(name) { return getComputedStyle(root).getPropertyValue(name).trim(); }
  function accent() { return getComputedStyle(document.body).getPropertyValue("--accent").trim(); }
  function rnd(a, b) { return a + Math.random() * (b - a); }
  function pick(arr) { return arr[Math.floor(Math.random() * arr.length)]; }

  function resize() {
    var dpr = Math.min(window.devicePixelRatio || 1, 2), b = main.getBoundingClientRect();
    W = window.innerWidth; H = window.innerHeight;
    canvas.width = W * dpr; canvas.height = H * dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    col.l = b.left; col.r = b.right;
    schedule();
  }
  function roomy() { return col.l > 100 || W - col.r > 100; }

  function schedule() {
    if (pending) return;
    pending = true;
    requestAnimationFrame(frame);
  }

  function frame(now) {
    pending = false;
    ctx.clearRect(0, 0, W, H);
    fx = fx.filter(function (e) { return now - e.t0 < e.dur; });
    var seen = hover && mouse.x > -1e3 && roomy(), live = false;
    if (seen) {
      live = drawGrid(now);
      fx.forEach(function (e) { e.draw((now - e.t0) / e.dur, now); });
      lens(dark() ? R : RL);
      maskColumn();
    }
    if (live || fx.length) schedule();
  }

  /* keep only what lies in a soft disc around the pointer */
  function lens(r) {
    var g = ctx.createRadialGradient(mouse.x, mouse.y, 0, mouse.x, mouse.y, r);
    g.addColorStop(0, "rgba(0,0,0,1)"); g.addColorStop(0.5, "rgba(0,0,0,0.8)"); g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.globalCompositeOperation = "destination-in";
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
    ctx.globalCompositeOperation = "source-over";
  }
  /* keep the canvas out of the reading column, with a soft edge */
  function maskColumn() {
    var w = col.r - col.l + 2 * EDGE, g = ctx.createLinearGradient(col.l - EDGE, 0, col.r + EDGE, 0);
    g.addColorStop(0, "rgba(0,0,0,0)"); g.addColorStop(EDGE / w, "rgba(0,0,0,1)");
    g.addColorStop(1 - EDGE / w, "rgba(0,0,0,1)"); g.addColorStop(1, "rgba(0,0,0,0)");
    ctx.globalCompositeOperation = "destination-out";
    ctx.fillStyle = g; ctx.fillRect(col.l - EDGE, 0, w, H);
    ctx.globalCompositeOperation = "source-over";
  }

  /* ---- hidden geometry (dark mode) ----
     Each object adds a closed-form displacement to the grid vertex at (x, y); weak-field terms are
     summed and soft-clamped, wells and rotations are added after the clamp. Objects sit in the side margins (side, x as a fraction of the margin, y of the viewport)
     and are kept in sessionStorage, so the same universe is explored while browsing.
       web      Zel'dovich cosmic web: gradient of a random potential, gentle filaments and voids everywhere
       lens     a mass as a gravity well (embedding-diagram picture, r' = r (1 - w e^(-r^2/2 sg^2)), never
                folds for w < 1) or, with m < 0, a void that pushes the grid apart; optional rotation a;
                with `hide` it is a black hole and the grid is not drawn inside
       string   cosmic string: both sides shift toward the line; the overlap strip is the double image
       wave     gravitational-wave packet along the line of sight, plus polarisation, h ~ 0.2
       binary   two lenses that inspiral and merge on a 90 s wall-clock cycle, radiating a spiral wave;
                a chirping burst at merger, then one heavier lens until a new pair fades in
                a lens with `star` has a small body on a precessing orbit; a string with `drift` moves
       shear    static tidal shear from a mass off screen (rhombic cells)
       ring     transient l = 2 wavefront from a click (plain, chirping merger, or rotating burst)
     A click swirl is a lens with a strong rotation and a 1.5 s ramp: it winds up smoothly and stays. */
  var geo = [], EPS2 = 40 * 40, CLAMP = 26, KEY = "geo8";   /* bump KEY when the object schema changes */
  function ox(o) { return o.side < 0 ? o.x * col.l : col.r + o.x * (W - col.r); }
  function oy(o) { return o.y * H; }
  function toMargin(px) {
    return px < (col.l + col.r) / 2 ? { side: -1, x: Math.max(0.05, Math.min(0.95, px / col.l)) }
                                    : { side: 1, x: Math.max(0.05, Math.min(0.95, (px - col.r) / (W - col.r))) };
  }
  function seed() {
    try { geo = JSON.parse(sessionStorage.getItem(KEY)) || []; } catch (e) { geo = []; }
    geo.forEach(function (o) { delete o.t0; delete o.t1; });
    if (geo.length) return;
    var modes = [], i, lam, th;
    for (i = 0; i < 6; i++) {                          /* gentle: rms about 4 px, so the objects stand out */
      lam = rnd(220, 600); th = rnd(0, Math.PI);
      modes.push([2 * Math.PI / lam * Math.cos(th), 2 * Math.PI / lam * Math.sin(th), rnd(0, 7), rnd(1.5, 3)]);
    }
    var objs = [
      { k: "lens", w: rnd(0.55, 0.75), sg: rnd(50, 70) },
      { k: "lens", w: rnd(0.55, 0.75), sg: rnd(50, 70) },
      { k: "lens", m: -rnd(400, 800) },
      { k: "lens", m: -rnd(400, 800) },
      { k: "lens", w: 0.5, sg: 55, a: rnd(400, 560) },
      { k: "lens", w: 0.95, sg: 60, a: 900, hide: 16, star: { a: rnd(60, 80), e: rnd(0.45, 0.65), kp: 0.92, T: rnd(9, 13), ph: rnd(0, 7) } },
      { k: "string", s0: rnd(8, 14), L: rnd(300, 500), th: rnd(0, Math.PI) },
      { k: "string", s0: rnd(8, 14), L: rnd(300, 500), th: rnd(0, Math.PI), drift: 30 },
      { k: "wave", h: rnd(0.14, 0.2), sg: rnd(200, 300), T: rnd(3000, 6000), ps: rnd(0, Math.PI), ph: rnd(0, 7) },
      { k: "binary", w: 0.65, sg: 40, s: rnd(80, 100), T: rnd(7, 10), ph0: rnd(0, 90) },
      { k: "shear", g: rnd(0.05, 0.08), sg: 250, ps: rnd(0, Math.PI) }
    ];
    /* seven slots per margin, staggered in two lanes, a little jitter; objects shuffled over them */
    var slots = [], side, row;
    for (side = -1; side <= 1; side += 2) for (row = 0; row < 6; row++)
      slots.push({ side: side, x: (row % 2 ? 0.68 : 0.32) + rnd(-0.06, 0.06), y: 0.14 + row * 0.146 + rnd(-0.03, 0.03) });
    slots.sort(function () { return Math.random() - 0.5; });
    objs.forEach(function (o, i) { o.side = slots[i].side; o.x = slots[i].x; o.y = slots[i].y; });
    geo = [{ k: "web", modes: modes }].concat(objs);
    save();
  }
  function save() {
    try { sessionStorage.setItem(KEY, JSON.stringify(geo.filter(function (o) { return o.k !== "ring" && !o.t1; }))); } catch (e) {}
  }
  function smooth(t) { t = Math.max(0, Math.min(1, t)); return t * t * (3 - 2 * t); }
  /* strength of an object: click objects grow in over 0.4 s (or their own ramp) and, when replaced, fade over 1.2 s */
  function strength(o, now) {
    var a = o.t0 ? smooth((now - o.t0) / (o.ramp || 400)) : 1;
    if (o.t1) a *= 1 - smooth((now - o.t1) / 1200);
    return a;
  }
  /* binary inspiral cycle (wall clock, so it continues across pages): TIN seconds of inspiral with
     separation s0 u^(1/4) and Kepler frequency ~ s^(-3/2), u = time left / TIN; then a merged lens
     until TCYC, then a new binary fades in */
  var TIN = 60, TCYC = 90, CGW = 120;   /* seconds, seconds, px/s wave speed */
  function bTau(o) { return (Date.now() / 1000 + o.ph0) % TCYC; }
  function bPhase(o, tau) { var u = Math.max(0, TIN - tau) / TIN; return 2 * Math.PI / o.T * TIN * 1.6 * (1 - Math.pow(u, 5 / 8)); }
  function bSep(o, tau) { return Math.max(8, o.s * Math.pow(Math.max(0, TIN - tau) / TIN, 0.25)); }
  function quad(rx, ry, ps) {  /* plus-polarised quadrupole pattern at angle ps */
    var c = Math.cos(2 * ps), s = Math.sin(2 * ps);
    return [rx * c + ry * s, rx * s - ry * c];
  }

  function disp(x, y, now, out) {
    var dx = 0, dy = 0, sx = 0, sy = 0, i, j, o, rx, ry, r2, r, k, a, q, m, c, sn;
    for (i = 0; i < geo.length; i++) {
      o = geo[i]; a = strength(o, now); if (!a) continue;
      if (o.k === "web") {
        for (j = 0; j < o.modes.length; j++) {
          m = o.modes[j]; k = -m[3] * Math.sin(m[0] * x + m[1] * y + m[2]) / Math.hypot(m[0], m[1]);
          dx += k * m[0]; dy += k * m[1];
        }
        continue;
      }
      rx = x - ox(o); ry = y - oy(o);
      if (o.drift) { rx -= o.drift * Math.sin(2 * Math.PI * Date.now() / 25000) * Math.cos(o.th + Math.PI / 2); ry -= o.drift * Math.sin(2 * Math.PI * Date.now() / 25000) * Math.sin(o.th + Math.PI / 2); }
      r2 = rx * rx + ry * ry;
      if (o.k === "lens") {
        if (o.w) { k = -a * o.w * Math.exp(-r2 / (2 * o.sg * o.sg)); sx += k * rx; sy += k * ry; }   /* well: r' = r (1 - w e^(-r^2/2s^2)) */
        else { k = a * o.m / (r2 + EPS2); dx += k * rx; dy += k * ry; }                             /* void: diverging, m < 0 */
        if (o.a) { k = a * o.a / (r2 + EPS2); c = Math.cos(k); sn = Math.sin(k); sx += c * rx - sn * ry - rx; sy += sn * rx + c * ry - ry; }
      } else if (o.k === "string") {
        var tx = Math.cos(o.th), ty = Math.sin(o.th), u = -rx * ty + ry * tx, v = rx * tx + ry * ty;
        k = -a * o.s0 * Math.tanh(u / 15) * (1 - smooth((Math.abs(v) - o.L / 2) / 60 + 1));
        dx += k * -ty; dy += k * tx;
      } else if (o.k === "wave") {
        q = quad(rx, ry, o.ps); k = a * o.h / 2 * Math.exp(-r2 / (2 * o.sg * o.sg)) * Math.cos(2 * Math.PI * now / o.T + o.ph);
        dx += k * q[0]; dy += k * q[1];
      } else if (o.k === "shear") {
        q = quad(rx, ry, o.ps); k = a * o.g * Math.exp(-r2 / (2 * o.sg * o.sg));
        dx += k * q[0]; dy += k * q[1];
      } else if (o.k === "binary") {
        var tau = bTau(o);
        if (tau < TIN) {                                    /* inspiral: two lenses plus the spiral wave they radiate */
          var sep = bSep(o, tau), ph = bPhase(o, tau), cx = sep / 2 * Math.cos(ph), cy = sep / 2 * Math.sin(ph), bx, by, fin = a * smooth(tau / 3);
          for (j = -1; j <= 1; j += 2) {
            bx = rx - j * cx; by = ry - j * cy; k = -fin * o.w * Math.exp(-(bx * bx + by * by) / (2 * o.sg * o.sg)); sx += k * bx; sy += k * by;
          }
          r = Math.sqrt(r2) || 1;
          var A = 45 * Math.min(4, Math.pow(o.s / sep, 0.75)) * fin * Math.exp(-r2 / (2 * 220 * 220)) / Math.sqrt(Math.max(r, 40));
          var pr = 2 * Math.atan2(ry, rx) - 2 * bPhase(o, Math.max(0, tau - r / CGW)), cw = Math.cos(pr), sw = Math.sin(pr);
          dx += A * (cw * rx / r + sw * ry / r); dy += A * (cw * ry / r - sw * rx / r);
        } else {                                            /* merged: one heavier lens, fading before the next cycle */
          k = -a * 0.85 * (1 - smooth((tau - TCYC + 3) / 3)) * Math.exp(-r2 / (2 * 55 * 55)); sx += k * rx; sy += k * ry;
        }
      } else if (o.k === "ring") {                        /* outgoing l = 2 wavefront, 200 px/s */
        var t = (now - o.t0) / 1000, f; r = Math.sqrt(r2) || 1; f = r - 200 * t;
        var lam = o.chirp ? 80 / (1 + t / 0.7) : 80, ps = o.rot ? o.rot * t : 0;
        k = o.A * Math.exp(-t / 1.2) * (1 - smooth((t - 1.1) / 0.8)) * Math.exp(-f * f / (2 * 50 * 50)) * Math.cos(2 * Math.PI * f / lam);
        var p2 = 2 * Math.atan2(ry, rx) - 2 * ps, c2 = Math.cos(p2), s2 = Math.sin(p2);
        dx += k * (c2 * rx / r + s2 * ry / r); dy += k * (c2 * ry / r - s2 * rx / r);
      }
    }
    var n = Math.hypot(dx, dy);
    if (n > 1e-6) { k = CLAMP * Math.tanh(n / CLAMP) / n; dx *= k; dy *= k; }
    out[0] = dx + sx; out[1] = dy + sy;
  }
  function hidden(x, y) {  /* inside the black hole the grid is not drawn */
    for (var i = 0; i < geo.length; i++) {
      var o = geo[i];
      if (o.hide && Math.hypot(x - ox(o), y - oy(o)) < o.hide) return true;
    }
    return false;
  }
  function animating(now) {  /* is anything time-dependent near the pointer? */
    for (var i = 0; i < geo.length; i++) {
      var o = geo[i], r = o.k === "web" ? 1e9 : Math.hypot(mouse.x - ox(o), mouse.y - oy(o));
      if (o.k === "ring" || (o.t0 && now - o.t0 < (o.ramp || 400)) || o.t1) return true;
      if (o.k === "wave" && r < R + 2 * o.sg) return true;
      if (o.k === "binary" && r < R + o.s + 250) return true;
      if ((o.star || o.drift) && r < R + 200) return true;
    }
    return false;
  }

  /* the grid around the pointer: warped by the hidden geometry in the dark, flat in the light */
  function drawGrid(now) {
    var isDark = dark(), mx = mouse.x, my = mouse.y, lo = (isDark ? R : RL) + G, d = [0, 0], x, y, t, step = isDark ? 6 : lo;
    geo = geo.filter(function (o) { return !(o.t1 && now - o.t1 > 1200) && !(o.k === "ring" && now - o.t0 > 1900); });
    ctx.save();
    ctx.beginPath(); ctx.lineWidth = 1; ctx.strokeStyle = accent(); ctx.globalAlpha = isDark ? 0.66 : 0.28;
    function pt(x, y) {
      if (isDark && hidden(x, y)) { t = 0; return; }
      if (isDark) disp(x, y, now, d);
      t++ ? ctx.lineTo(x + d[0], y + d[1]) : ctx.moveTo(x + d[0], y + d[1]);
    }
    for (x = Math.floor((mx - lo) / G) * G; x <= mx + lo; x += G) for (y = my - lo, t = 0; y <= my + lo; y += step) pt(x, y);
    for (y = Math.floor((my - lo) / G) * G; y <= my + lo; y += G) for (x = mx - lo, t = 0; x <= mx + lo; x += step) pt(x, y);
    ctx.stroke();
    if (isDark) {
      geo.forEach(function (o) {
        var cyc;
        if (o.k === "binary") {                             /* merger: one chirping burst per cycle */
          cyc = Math.floor((Date.now() / 1000 + o.ph0) / TCYC);
          if (bTau(o) >= TIN && o.cyc !== cyc) { o.cyc = cyc; geo.push({ k: "ring", A: 12, chirp: 1, side: o.side, x: o.x, y: o.y, t0: now }); }
        }
        if (o.star && Math.hypot(mx - ox(o), my - oy(o)) < lo + o.star.a * 2) {
          var st = o.star, T = Date.now() / 1000, i, ph, rr, px, py;
          ctx.lineWidth = 1.2;
          for (i = 0; i < 24; i++) {                        /* fading trail over the last third of an orbit */
            ph = 2 * Math.PI * (T - (24 - i) * st.T / 72) / st.T + st.ph; rr = st.a * (1 - st.e * st.e) / (1 + st.e * Math.cos(st.kp * ph));
            px = ox(o) + rr * Math.cos(ph); py = oy(o) + rr * Math.sin(ph);
            if (i) { ctx.globalAlpha = 0.7 * i / 24; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(px, py); ctx.stroke(); }
            x = px; y = py;
          }
          ctx.globalAlpha = 0.95; ctx.fillStyle = accent(); ctx.beginPath(); ctx.arc(x, y, 2.4, 0, 7); ctx.fill();
        }
      });
    }
    ctx.restore();
    return isDark && animating(now);
  }

  /* a click perturbs the geometry in one of five physical ways; a lens dropped within 120 px of an
     earlier click lens merges with it and chirps. Only the newest six click objects stay. */
  function perturb(x, y, now) {
    var pos = toMargin(x), fy = y / H, users = [], near = null, i, o, r = Math.random(), made, ring = { k: "ring", A: 8, side: pos.side, x: pos.x, y: fy, t0: now };
    for (i = 0; i < geo.length; i++) {
      o = geo[i]; if (!o.u || o.t1) continue;
      users.push(o);
      if (o.k === "lens" && o.w && Math.hypot(ox(o) - x, oy(o) - y) < 120) near = o;
    }
    if (near && r < 0.6) {                                /* merger */
      var p2 = toMargin((ox(near) + x) / 2);
      near.side = p2.side; near.x = p2.x; near.y = (near.y + fy) / 2; near.w = Math.min(0.9, near.w + 0.12); near.sg += 8;
      ring.A = 12; ring.chirp = 1;
    } else {
      if (r < 0.3) made = { k: "lens", w: 0.6, sg: 50 };
      else if (r < 0.45) { made = { k: "lens", m: -600 }; ring.A = -6; }
      else if (r < 0.6) made = { k: "string", s0: 12, L: 320, th: rnd(0, Math.PI) };
      else if (r < 0.8) { made = { k: "lens", w: 0.2, sg: 50, a: (Math.random() < 0.5 ? -1 : 1) * 2600, ramp: 1500 }; ring.A = 4; }   /* swirl: winds up smoothly and stays */
      else { ring.A = 12; ring.rot = 6; }                 /* a pure burst with rotating polarisation */
      if (made) {
        if (users.length >= 6) users[0].t1 = now;
        made.side = pos.side; made.x = pos.x; made.y = fy; made.u = 1; made.t0 = now;
        geo.push(made);
      }
    }
    geo.push(ring);
    save();
  }

  /* ---- scattering events (light mode) ----
     Bubble-chamber pictures of real reactions. A beam particle hits a proton at rest at the click;
     the products are drawn from a small table of reactions and carry the beam momentum, and each
     unstable product may decay in flight into its listed daughters, with momentum shared at every
     vertex. Charged tracks bend in a uniform field with radius 1.6 p/|q| px and everything moves at
     one speed. Line codes follow Feynman: photons wavy, neutrinos faint dotted, neutral hadrons
     invisible until they decay, electrons thin and spiralling in, protons thick and short; the beam may
     knock a slow electron out of an atom on its way in (a delta ray). Each
     track carries its name and the reaction is written at the vertex. Each piece of track fades by
     its own age, so a picture dissolves from the vertex outward. */
  var V = 320, LMAX = 340, HOLD = 0.7, FADE = 0.8;   /* px/s, max segment length, seconds */
  function expo(mean) { return -mean * Math.log(1 - Math.random()); }
  function mag(v) { return Math.hypot(v[0], v[1]); }

  /* particle table: label, charge, line style, width, momentum loss per px, decay [daughters, mean path] */
  var P = {
    "e-":  { l: "e⁻", q: -1, w: 1.1, loss: 0.04 },
    "e+":  { l: "e⁺", q: 1, w: 1.1, loss: 0.04 },
    "mu-": { l: "μ⁻", q: -1, dec: [["e-", "nu", "nu"], 900] },
    "mu+": { l: "μ⁺", q: 1, dec: [["e+", "nu", "nu"], 900] },
    "pi-": { l: "π⁻", q: -1, dec: [["mu-", "nu"], 700] },
    "pi+": { l: "π⁺", q: 1, dec: [["mu+", "nu"], 700] },
    "pi0": { l: "π⁰", q: 0, style: "none", dec: [["g", "g"], 0] },
    "K-":  { l: "K⁻", q: -1, dec: [["mu-", "nu"], 500] },
    "K+":  { l: "K⁺", q: 1, dec: [["mu+", "nu"], 500] },
    "K0":  { l: "K⁰", q: 0, style: "none", dec: [["pi+", "pi-"], 130] },
    "L":   { l: "Λ", q: 0, style: "none", dec: [["p", "pi-"], 150] },
    "S-":  { l: "Σ⁻", q: -1, dec: [["n", "pi-"], 60] },
    "Om-": { l: "Ω⁻", q: -1, dec: [["L", "K-"], 90] },
    "p":   { l: "p", q: 1, w: 2.2, loss: 0.35 },
    "pbar": { l: "p̄", q: -1, w: 2.2, loss: 0.35 },
    "n":   { l: "n", q: 0, style: "none" },
    "g":   { l: "γ", q: 0, style: "wavy", dec: [["e+", "e-"], 220], tangent: 1 },
    "nu":  { l: "ν", q: 0, style: "dots" }
  };
  /* reactions on a proton at rest: beam, products, weight */
  var reactions = [
    ["pi-", ["pi-", "p"], 3], ["pi-", ["K0", "L"], 3], ["pi-", ["pi0", "n"], 2], ["pi-", ["pi-", "pi+", "pi-", "p"], 3],
    ["pi+", ["p", "pi+"], 2], ["pi+", ["p", "pi+", "pi0"], 2],
    ["K-", ["Om-", "K+", "K0"], 2], ["K-", ["L", "pi0"], 2], ["K-", ["S-", "pi+"], 2], ["K-", ["K-", "p"], 1],
    ["p", ["p", "p", "pi+", "pi-", "pi0"], 3], ["p", ["p", "n", "pi+"], 2],
    ["pbar", ["pi+", "pi-", "pi+", "pi-", "pi0"], 3],
    ["g", ["e+", "e-", "p"], 2], ["e-", ["e-", "p", "g"], 2], ["mu-", ["mu-", "p"], 1]
  ];
  function pickWeighted(list) {
    var tot = 0, i, r; for (i = 0; i < list.length; i++) tot += list[i][2];
    r = Math.random() * tot; for (i = 0; i < list.length; i++) { r -= list[i][2]; if (r <= 0) return list[i]; }
    return list[0];
  }

  /* split a momentum among n daughters: random fractions, transverse kicks summing to zero */
  function split(p, n, tangent) {
    var f = [], tot = 0, i, out = [], nx = -p[1], ny = p[0], kicks = [], ksum = 0, m = mag(p);
    for (i = 0; i < n; i++) { f.push(rnd(0.5, 1.5)); tot += f[i]; }
    for (i = 0; i < n; i++) { kicks.push(tangent ? 0 : rnd(-0.25, 0.25)); ksum += kicks[i]; }
    for (i = 0; i < n; i++) { var k = kicks[i] - ksum / n; out.push([p[0] * f[i] / tot + nx * k, p[1] * f[i] / tot + ny * k]); }
    return out;
  }
  /* n momenta with a given sum, angles spread around the beam; magnitudes kept in [50, 400] */
  function momenta(n, sum) {
    var ps, i, ok, sx, sy, th = Math.atan2(sum[1], sum[0]), tries;
    for (tries = 0; tries < 60; tries++) {
      sx = 0; sy = 0; ps = [];
      for (i = 0; i < n; i++) {
        var m = Math.min(400, Math.max(50, expo(120))), a = th + Math.PI * (Math.random() + Math.random() - 1);
        ps.push([m * Math.cos(a), m * Math.sin(a)]); sx += ps[i][0]; sy += ps[i][1];
      }
      ok = true;
      for (i = 0; i < n; i++) {
        ps[i][0] += (sum[0] - sx) / n; ps[i][1] += (sum[1] - sy) / n;
        var k = mag(ps[i]); if (k < 50 || k > 400) ok = false;
      }
      if (ok) return ps;
    }
    return ps;
  }

  /* a track: particle, momentum, path length until it decays (Infinity if not within view), daughters */
  function track(name, p, depth) {
    var d = P[name], t = { d: d, p: p, len: Infinity, kids: [] };
    if (d.dec && depth < 4) {
      var len = d.dec[1] ? expo(d.dec[1]) : 0;
      if (len < LMAX) {
        t.len = len;
        split(p, d.dec[0].length, d.tangent).forEach(function (q, i) { t.kids.push(track(d.dec[0][i], q, depth + 1)); });
      }
    }
    return t;
  }

  function scatter(x, y) {
    var th = rnd(0, 2 * Math.PI), b = [Math.cos(th), Math.sin(th)], beam = [320 * b[0], 320 * b[1]];
    var rx = pickWeighted(reactions), root = { d: P[rx[0]], p: beam, len: 160, kids: [], beam: 1 }, tail = root, pb = beam;
    if (P[rx[0]].q && Math.random() < 0.3) {              /* delta ray: a slow electron knocked out of an atom on the way in */
      var dl = rnd(40, 110), pe = 0.12 * 320, ang = (Math.random() < 0.5 ? -1 : 1) * rnd(0.9, 1.4), e = [pe * Math.cos(th + ang), pe * Math.sin(th + ang)];
      pb = [beam[0] - e[0], beam[1] - e[1]];
      root.len = dl; tail = { d: P[rx[0]], p: pb, len: 160 - dl, kids: [], beam: 1 };
      root.kids.push(track("e-", e, 0), tail);
    }
    var ps = momenta(rx[1].length, pb);
    tail.kids = rx[1].map(function (n, i) { return track(n, ps[i], 0); });
    var formula = P[rx[0]].l + " p → " + rx[1].map(function (n) { return P[n].l; }).join(" ");
    function end(t) { var e = Math.min(t.len, LMAX); t.kids.forEach(function (k) { e = Math.max(e, Math.min(t.len, LMAX) + end(k)); }); return e; }
    var dur = (end(root) / V + HOLD + FADE) * 1000, x0 = x - b[0] * 160, y0 = y - b[1] * 160;

    function age(tHead, now) { return 1 - Math.max(0, (now - tHead - HOLD) / FADE); }
    function label(txt, px, py, ux, uy, a, col, off) {
      if (a <= 0) return;
      ctx.save(); ctx.globalAlpha = 0.9 * a; ctx.fillStyle = col; ctx.font = "11px Inter, system-ui, sans-serif"; ctx.textAlign = "center"; ctx.textBaseline = "middle";
      ctx.fillText(txt, px + (off || 12) * ux, py + (off || 12) * uy); ctx.restore();
    }
    /* draw one segment from (sx, sy) starting at time ts; integrates curvature and momentum loss */
    function drawSeg(sx, sy, t, ts, now, col, mut) {
      var d = t.d, q = t.beam ? 0 : d.q, p = mag(t.p), th = Math.atan2(t.p[1], t.p[0]), s = 0, ds = d.style === "wavy" ? 2 : 5, px = sx, py = sy, nx, ny, a, turn = 0, len = Math.min(t.len, LMAX), stopped = false;
      ctx.lineWidth = d.w || 1.4; ctx.strokeStyle = d.q ? col : mut;
      ctx.setLineDash(d.style === "dots" ? [1.5, 5] : []);
      while (s < len) {
        if (ts + s / V > now) break;                        /* the head has not got here yet */
        if (q) {
          th += q * ds / (1.6 * p); turn += ds / (1.6 * p); p -= (d.loss || 0) * ds;
          if (p < 6 || (!d.loss && turn > 1.5 * Math.PI)) { stopped = true; break; }
        }
        nx = px + ds * Math.cos(th); ny = py + ds * Math.sin(th);
        a = age(ts + s / V, now);
        if (a > 0 && d.style !== "none") {
          ctx.globalAlpha = (d.style === "dots" ? 0.45 : 0.9) * a; ctx.beginPath();
          if (d.style === "wavy") { var w = 2.2 * Math.sin(s * 0.52), w2 = 2.2 * Math.sin((s + ds) * 0.52); ctx.moveTo(px - Math.sin(th) * w, py + Math.cos(th) * w); ctx.lineTo(nx - Math.sin(th) * w2, ny + Math.cos(th) * w2); }
          else { ctx.moveTo(px, py); ctx.lineTo(nx, ny); }
          ctx.stroke();
        }
        px = nx; py = ny; s += ds;
      }
      var reached = s >= len, tHead = ts + Math.min(s, len) / V;
      if (d.style !== "none" && !t.beam) label(d.l, px, py, -Math.sin(th), Math.cos(th), age(tHead, now) * (d.style === "dots" ? 0.6 : 1), d.q ? col : mut);
      if (reached && !stopped && t.kids.length) {
        a = age(tHead, now);
        if (a > 0) {
          ctx.globalAlpha = 0.9 * a; ctx.fillStyle = col; ctx.beginPath(); ctx.arc(px, py, t.beam ? 2.6 : 1.8, 0, 7); ctx.fill();
          if (d.style === "none" && t.len > 0) label(d.l, px, py, Math.sin(th), -Math.cos(th), a, mut);
        }
        t.kids.forEach(function (k) { drawSeg(px, py, k, tHead, now, col, mut); });
      }
    }
    return { t0: performance.now(), dur: dur, draw: function (pr) {
      var now = pr * dur / 1000, col = accent(), mut = cssVar("--muted");
      ctx.save();
      drawSeg(x0, y0, root, 0, now, col, mut);
      label(P[rx[0]].l, x0 + b[0] * 20, y0 + b[1] * 20, -b[1], b[0], age(0, now), col);
      var up = b[0] < 0 ? 1 : -1;                          /* the side of the beam line that is higher on screen (y grows downward) */
      label(formula, x, y, -b[1] * up, b[0] * up, age(0.5, now), mut, 30);
      ctx.restore();
    } };
  }

  /* ---- events ---- */
  window.addEventListener("resize", resize);
  if (hover) {
    window.addEventListener("mousemove", function (e) { mouse.x = e.clientX; mouse.y = e.clientY; schedule(); }, { passive: true });
    document.addEventListener("mouseleave", function () { mouse.x = -1e4; schedule(); });
  }
  document.addEventListener("click", function (e) {
    if (e.target.closest("a, button, input, textarea, select, summary, label, iframe")) return;
    if (String(window.getSelection && window.getSelection())) return;
    if (!roomy()) return;
    if (dark()) perturb(e.clientX, e.clientY, performance.now());
    else fx.push(scatter(e.clientX, e.clientY));
    schedule();
  });
  new MutationObserver(schedule).observe(root, { attributes: true, attributeFilter: ["data-theme"] });
  resize();
  seed();
})();
