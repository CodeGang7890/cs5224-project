/* Ansera deck engine.
   Two modes, like Google Slides:
     · the editor: the slide, the speaker notes beside it (with reading-time estimates), and a filmstrip of every slide
       along the bottom. Click a thumbnail to go there; its ▶ presents from that slide.
     · presenting (▶ Slideshow / P): the slide alone, full screen. Esc goes back to the editor.
   Each <section class="slide"> has:
     data-speaker (merry | filbert | hazim | michael | adelia), data-title, optionally data-time (planned seconds; otherwise
     it's estimated from the script), data-fixed (a fixed slot, like the live demo), and an
     <aside class="notes"> with one <p data-step="k"> per build (what to say while build k is on screen; k = 0 before
     the first click). Elements with data-step="k" appear at click k. A note can set data-cue (what the next click shows) and
     data-at="m:ss" (its time into the slide; otherwise it's timed by its share of the words).
   Slide widgets (assets/slides.js) get enter / step / leave calls, so their animations follow the clicks, and an optional
   thumb(clone) call to dress the static thumbnails. */
(() => {
  "use strict";
  const SPEAKERS = {
    merry: { name: "Merry Rosalie", short: "Merry", hue: "#ff4f9a" },
    filbert: { name: "Filbert Reinaldha", short: "Filbert", hue: "#3b8bff" },
    hazim: { name: "Mohamed Nur Hazim", short: "Hazim", hue: "#ff9f1a" },
    michael: { name: "Michael Andrew Chan", short: "Michael", hue: "#22d07a" },
    adelia: { name: "Adelia Putri", short: "Adelia", hue: "#a66bff" },
  };
  const WPM = 165; // speaking pace for the estimates (165 words a minute keeps the talk under 15:00)
  const WPS = WPM / 60;
  const CLICK = 1.5; // and a pause for each build's animation

  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const el = (tag, cls, html) => { const n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; };
  const clock = (s) => { const neg = s < 0; s = Math.abs(Math.round(s)); return `${neg ? "−" : ""}${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; };
  const secs = (t) => { if (t == null || t === "") return null; const [m, s] = String(t).split(":").map(Number); return s == null ? m : m * 60 + s; };
  const words = (n) => (n.textContent.trim().match(/\S+/g) || []).length;
  const store = (k, d) => { try { return localStorage.getItem("ansera-deck-" + k) ?? d; } catch { return d; } };
  const save = (k, v) => { try { localStorage.setItem("ansera-deck-" + k, v); } catch { /* not remembered */ } };
  const body = document.body;
  const params = new URLSearchParams(location.search);
  const AUDIENCE = params.has("audience");
  if (AUDIENCE) body.classList.add("audience", "presenting");

  /* ------------------------------------------------------------ the slides and their timeline */
  const stage = $("#stage"), screen = $("#screen");
  const slides = $$(".slide", stage).map((s, i) => {
    const notes = $(".notes", s);
    const paras = notes ? $$(":scope > p[data-step], :scope > div[data-step]", notes) : [];
    const maxEl = Math.max(0, ...$$("[data-step]", s).filter((n) => !n.closest(".notes")).map((n) => Number(n.dataset.step)));
    const maxNote = Math.max(0, ...paras.map((p) => Number(p.dataset.step)));
    const w = paras.reduce((a, p) => a + (p.dataset.nowords != null ? 0 : words(p)), 0);
    const steps = Math.max(maxEl, maxNote);
    const read = w / WPS, est = read + steps * CLICK;
    return {
      el: s, i, id: s.id || `s${i + 1}`, title: s.dataset.title || `Slide ${i + 1}`, speaker: s.dataset.speaker || "merry",
      fixed: s.hasAttribute("data-fixed"), steps,
      paras, prep: notes ? $(".prep", notes) : null, warn: notes ? $$(".warn", notes) : [],
      words: w, read, est, plan: s.dataset.time ? Number(s.dataset.time) : Math.ceil(est),
    };
  });
  // planned start of each slide
  let total = 0;
  slides.forEach((s) => { s.t0 = total; total += s.plan; });
  const label = (s) => String(s.i + 1);
  // each note's time into its slide: data-at, or its share of the slide's words
  slides.forEach((s) => {
    const w = s.paras.map((p) => (p.dataset.nowords != null ? 0 : words(p)));
    const sum = w.reduce((a, b) => a + b, 0) || 1;
    let acc = 0;
    s.paraWords = w;
    s.paraAt = s.paras.map((p, k) => { const at = secs(p.dataset.at); const t = at != null ? at : (acc / sum) * s.plan; acc += w[k]; return t; });
    s.stepAt = (k) => { const idx = s.paras.findIndex((p) => Number(p.dataset.step) >= k); return idx < 0 ? s.plan : s.paraAt[idx]; };
  });

  // titles: split into words so they rise out of a mask
  $$(".slide h1.words, .slide h2", stage).forEach((h) => {
    h.classList.add("words");
    let i = 0;
    const walk = (node, grad = false) => {
      [...node.childNodes].forEach((c) => {
        if (c.nodeType === 3) {
          const frag = document.createDocumentFragment();
          c.textContent.split(/(\s+)/).forEach((part) => {
            if (!part) return;
            if (/^\s+$/.test(part)) { frag.append(document.createTextNode(" ")); return; }
            const w = el("span", "w"); const inner = el("span", grad ? "g" : null); inner.textContent = part; inner.style.setProperty("--i", i++); w.append(inner); frag.append(w);
          });
          c.replaceWith(frag);
        } else if (c.nodeType === 1 && c.tagName !== "BR") { if (c.tagName === "EM") c.classList.add("em-split"); walk(c, grad || c.tagName === "EM"); }
      });
    };
    walk(h);
  });
  // stagger children get an index
  $$(".stagger", stage).forEach((g) => [...g.children].forEach((c, k) => c.style.setProperty("--i", k)));

  /* ------------------------------------------------------------ fit the stage */
  const fit = () => { const w = screen.clientWidth; if (w) stage.style.transform = `scale(${w / 1600})`; };
  new ResizeObserver(fit).observe(screen);
  window.addEventListener("resize", fit);
  fit();

  /* ------------------------------------------------------------ HUD */
  const hud = $("#hud");
  const prog = el("div", "prog");
  slides.forEach((s) => { const i = el("i"); i.style.flex = String(s.plan); i.style.setProperty("--sc", SPEAKERS[s.speaker].hue); prog.append(i); s.bar = i; });
  hud.append(prog);
  const who = el("div", "who"); const num = el("div", "num");
  const brand = el("div", "brandmark", "<i>A</i>Ansera · Group 20");
  hud.append(who, num, brand);
  const handoff = el("div", "handoff");
  stage.append(handoff);

  /* ------------------------------------------------------------ background: an aurora tinted by the speaker */
  const Aurora = (() => {
    const cv = $("#bg"), ctx = cv.getContext("2d");
    const W = 400, H = 225; cv.width = W; cv.height = H; // drawn small, scaled up: soft and cheap
    const hex = (h) => [1, 3, 5].map((k) => parseInt(h.slice(k, k + 2), 16));
    let cur = hex("#25d366"), cur2 = hex("#3b8bff"), to = cur, to2 = cur2, energy = 0.6, energyTo = 0.6;
    const blobs = Array.from({ length: 5 }, (_, k) => ({ a: Math.random() * 6.28, b: Math.random() * 6.28, s: 0.00007 + k * 0.000025, r: 0.45 + (k % 3) * 0.14, k }));
    const stars = Array.from({ length: 70 }, () => ({ x: Math.random(), y: Math.random(), z: Math.random(), v: 0.2 + Math.random() }));
    let last = performance.now();
    function frame(t) {
      const dt = Math.min(50, t - last); last = t;
      const mix = (a, b) => a.map((v, k) => v + (b[k] - v) * Math.min(1, dt * 0.0022));
      cur = mix(cur, to); cur2 = mix(cur2, to2); energy += (energyTo - energy) * Math.min(1, dt * 0.002);
      ctx.globalCompositeOperation = "source-over";
      const g = ctx.createLinearGradient(0, 0, W, H); g.addColorStop(0, "#081129"); g.addColorStop(1, "#04081a");
      ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
      ctx.globalCompositeOperation = "lighter";
      blobs.forEach((b) => {
        b.a += b.s * dt * (0.6 + energy); b.b += b.s * 0.7 * dt * (0.6 + energy);
        const x = W * (0.5 + 0.42 * Math.cos(b.a + b.k)), y = H * (0.5 + 0.38 * Math.sin(b.b * 1.3 + b.k * 2));
        const c = b.k % 2 ? cur2 : cur, r = W * b.r;
        const rg = ctx.createRadialGradient(x, y, 0, x, y, r);
        const al = (b.k % 2 ? 0.16 : 0.22) * (0.75 + energy * 0.4);
        rg.addColorStop(0, `rgba(${c.map(Math.round).join(",")},${al})`); rg.addColorStop(1, "rgba(0,0,0,0)");
        ctx.fillStyle = rg; ctx.fillRect(0, 0, W, H);
      });
      stars.forEach((s) => {
        s.y -= 0.000012 * dt * s.v * (0.5 + energy); if (s.y < 0) { s.y = 1; s.x = Math.random(); }
        const tw = 0.35 + 0.35 * Math.sin(t * 0.002 * s.v + s.x * 40);
        ctx.fillStyle = `rgba(255,255,255,${0.12 + tw * 0.25 * s.z})`; ctx.fillRect(s.x * W, s.y * H, s.z > 0.8 ? 1.2 : 0.7, s.z > 0.8 ? 1.2 : 0.7);
      });
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
    return { tint(a, b, e = 0.6) { to = hex(a); to2 = hex(b); energyTo = e; }, pulse() { energy = 1.6; } };
  })();

  /* ------------------------------------------------------------ count-ups */
  const fmtCount = (n, v) => (n.dataset.prefix || "") + v.toLocaleString("en-US", { minimumFractionDigits: Number(n.dataset.dec || 0), maximumFractionDigits: Number(n.dataset.dec || 0) }) + (n.dataset.suffix || "");
  function countUp(n) {
    if (n.dataset.done) return; n.dataset.done = 1;
    const to = Number(n.dataset.count), t0 = performance.now(), dur = Number(n.dataset.dur || 1400);
    const step = (t) => { const k = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - k, 4); n.textContent = fmtCount(n, to * e); if (k < 1) requestAnimationFrame(step); };
    requestAnimationFrame(step);
  }
  const resetCounts = (root) => $$("[data-count]", root).forEach((n) => { delete n.dataset.done; n.textContent = fmtCount(n, 0); });

  /* ------------------------------------------------------------ navigation */
  let cur = -1, step = 0, everStarted = false;
  const W = () => window.WIDGETS || {};
  const widget = (s) => W()[s.id];

  function applyStep(s, k, dir) {
    const els = $$("[data-step]", s.el).filter((n) => !n.closest(".notes"));
    const latest = Math.max(0, ...els.map((n) => Number(n.dataset.step)).filter((a) => a <= k));
    els.forEach((n) => {
      const at = Number(n.dataset.step), was = n.classList.contains("in"), on = at <= k;
      n.classList.toggle("in", on);
      n.classList.toggle("now", on && at === latest && at > 0 && n.classList.contains("hl"));
      if (on && !was) { $$("[data-count]", n).concat(n.dataset.count ? [n] : []).forEach(countUp); }
      if (!on && was) resetCounts(n);
    });
    try { widget(s)?.step?.(s.el, k, dir, ctx); } catch (e) { console.error(e); }
  }

  function go(i, k = 0, { dir = i >= cur ? 1 : -1, silent = false } = {}) {
    i = Math.max(0, Math.min(slides.length - 1, i));
    const s = slides[i];
    k = Math.max(0, Math.min(s.steps, k));
    if (i !== cur) {
      const old = slides[cur];
      if (old) {
        old.el.classList.remove("on", "enter", "enter-back");
        old.el.classList.add(dir > 0 ? "leave" : "leave-back");
        setTimeout(() => old.el.classList.remove("leave", "leave-back"), 650);
        try { widget(old)?.leave?.(old.el, ctx); } catch (e) { console.error(e); }
      }
      $$("[data-step]", s.el).forEach((n) => n.classList.remove("in", "now"));
      resetCounts(s.el);
      void s.el.offsetWidth; // so the builds transition in again, not just appear
      s.el.classList.remove("leave", "leave-back");
      s.el.classList.add("on", dir > 0 ? "enter" : "enter-back");
      // the title words animate again on every entry
      $$(".words .w > span", s.el).forEach((w) => { w.style.animation = "none"; void w.offsetWidth; w.style.animation = ""; });
      const prevSpeaker = old?.speaker;
      cur = i; step = k;
      try { widget(s)?.enter?.(s.el, ctx); } catch (e) { console.error(e); }
      applyStep(s, k, dir);
      const hue = SPEAKERS[s.speaker].hue;
      Aurora.tint(s.el.dataset.tint || hue, s.el.dataset.tint2 || "#3b8bff", Number(s.el.dataset.energy || 0.6));
      document.documentElement.style.setProperty("--c", hue);
      if (old && prevSpeaker !== s.speaker && dir > 0) showHandoff(s.speaker, s.title);
      slideClock = performance.now();
    } else {
      const d = k > step ? 1 : -1;
      step = k;
      applyStep(s, k, d);
    }
    paint();
    if (!silent) broadcast();
    try { history.replaceState(null, "", `${location.pathname}${location.search}#${i + 1}${k ? "." + k : ""}`); } catch { /* some file:// pages refuse */ }
  }
  const next = () => { if (!everStarted && presenting()) startTimer(); const s = slides[cur]; if (step < s.steps) go(cur, step + 1); else if (cur < slides.length - 1) go(cur + 1, 0, { dir: 1 }); };
  const prev = () => { if (step > 0) go(cur, step - 1); else if (cur > 0) { const p = slides[cur - 1]; go(cur - 1, p.steps, { dir: -1 }); } };

  let hoTimer = 0;
  function showHandoff(sp, title) {
    const p = SPEAKERS[sp];
    handoff.style.setProperty("--hc", p.hue);
    handoff.innerHTML = `<span class="av">${p.short[0]}</span><span><b>${p.name}</b><small>${title}</small></span>`;
    handoff.classList.remove("show"); void handoff.offsetWidth; handoff.classList.add("show");
    clearTimeout(hoTimer); hoTimer = setTimeout(() => handoff.classList.remove("show"), 3600);
    Aurora.pulse();
  }

  /* ------------------------------------------------------------ thumbnails (filmstrip and grid) */
  function thumbClone(s) {
    const clone = s.el.cloneNode(true);
    clone.classList.add("on"); clone.classList.remove("enter", "leave", "enter-back", "leave-back");
    clone.removeAttribute("id");
    $$("[id]", clone).forEach((n) => n.removeAttribute("id"));
    $$("[data-step]", clone).forEach((n) => n.classList.add("in"));
    $$("[data-count]", clone).forEach((n) => { n.textContent = fmtCount(n, Number(n.dataset.count)); });
    try { widget(s)?.thumb?.(clone, s.steps); } catch (e) { console.error(e); }
    return clone;
  }
  function thumb(s) {
    const th = el("div", "thumb"), mini = el("div", "mini");
    mini.append(thumbClone(s)); th.append(mini);
    return th;
  }
  const scaleThumbs = (root) => requestAnimationFrame(() => $$(".thumb", root).forEach((t) => { if (t.clientWidth) $(".mini", t).style.transform = `scale(${t.clientWidth / 1600})`; }));

  /* ------------------------------------------------------------ the filmstrip */
  const strip = $("#filmstrip");
  function buildStrip() {
    if (AUDIENCE) return;
    let lastSp = null;
    slides.forEach((s) => {
      if (s.speaker !== lastSp) {
        lastSp = s.speaker;
        const sep = el("div", "fs-sep", `<span>${SPEAKERS[s.speaker].short}</span>`);
        sep.style.setProperty("--c", SPEAKERS[s.speaker].hue);
        strip.append(sep);
      }
      const item = el("div", "fs-item");
      item.tabIndex = 0;
      item.style.setProperty("--c", SPEAKERS[s.speaker].hue);
      item.title = `${label(s)}. ${s.title}`;
      const th = thumb(s);
      const play = el("button", "fs-play", "▶");
      play.title = "Present from this slide";
      play.onclick = (e) => { e.stopPropagation(); present(s.i); };
      th.append(play);
      item.append(el("div", "fs-num", label(s)), th,
        el("div", "fs-meta", `<span class="fs-t">${s.title}</span><span class="fs-time">${(s.fixed ? "" : "≈") + clock(s.plan)}</span>`));
      item.onclick = () => go(s.i, 0);
      item.onkeydown = (e) => { if (e.key === "Enter") { e.stopPropagation(); go(s.i, 0); } };
      strip.append(item);
      s.fs = item;
    });
    scaleThumbs(strip);
  }

  /* ------------------------------------------------------------ the speaker notes */
  const P = {
    av: $("#pr-av"), name: $("#pr-name"), title: $("#pr-title"), est: $("#pr-est"), elapsed: $("#pr-elapsed"), slideT: $("#pr-slide"), pace: $("#pr-pace"),
    paceBox: $("#pr-pace-box"), bar: $("#pr-bar"), script: $("#pr-script"), cue: $("#pr-cue"), up: $("#pr-up"), dots: $("#pr-dots"), timerBtn: $("#btn-timer"),
  };
  function renderScript(s) {
    P.script.innerHTML = "";
    s.warn.forEach((w) => P.script.append(el("div", "warn", w.innerHTML)));
    if (s.prep) P.script.append(el("div", "prep", s.prep.innerHTML));
    s.paras.forEach((p, idx) => {
      const k = Number(p.dataset.step);
      const box = el("div", "nt", "");
      box.dataset.k = k;
      const at = s.paraAt[idx];
      const meta = `+${clock(at)} · ${clock(s.t0 + at)} · ≈ ${clock(s.paraWords[idx] / WPS)} to read`;
      box.innerHTML = `<span class="at">${meta}</span>${p.innerHTML}`;
      const isLastOfStep = !s.paras.slice(idx + 1).some((q) => Number(q.dataset.step) === k);
      if (isLastOfStep) {
        const nk = s.paras.find((q) => Number(q.dataset.step) === k + 1);
        if (k < s.steps) box.insertAdjacentHTML("beforeend", ` <span class="click">▶ CLICK${nk?.dataset.cue ? " · " + nk.dataset.cue : ""}</span>`);
        else if (s.i < slides.length - 1) box.insertAdjacentHTML("beforeend", ` <span class="click">▶ CLICK · next slide</span>`);
      }
      box.onclick = () => go(s.i, k);
      P.script.append(box);
    });
  }
  let renderedFor = -1;
  function paint() {
    const s = slides[cur], sp = SPEAKERS[s.speaker];
    body.style.setProperty("--c", sp.hue);
    who.innerHTML = `<span class="dot"></span>${sp.name}`;
    num.textContent = `${String(s.i + 1).padStart(2, "0")} / ${slides.length}`;
    hud.classList.toggle("hide-chrome", s.el.hasAttribute("data-nochrome"));
    slides.forEach((t) => { t.bar.classList.toggle("done", t.i < cur); t.bar.classList.toggle("now", t.i === cur); });
    if (s.bar) s.bar.style.setProperty("--f", `${s.steps ? (step / s.steps) * 100 : 100}%`);
    $("#pb-num").textContent = `${s.i + 1} / ${slides.length}`;
    if (AUDIENCE) return;
    // filmstrip
    slides.forEach((x) => x.fs?.classList.toggle("now", x.i === cur));
    if (s.fs && renderedFor !== cur) {
      const r = s.fs.offsetLeft - strip.clientWidth / 2 + s.fs.clientWidth / 2;
      strip.scrollTo({ left: r, behavior: renderedFor < 0 ? "auto" : "smooth" });
    }
    // notes
    P.av.textContent = sp.short[0];
    P.name.textContent = sp.name;
    P.title.textContent = `Slide ${s.i + 1} of ${slides.length} · ${s.title}`;
    P.est.innerHTML = s.fixed
      ? `<b>${clock(s.plan)}</b> fixed slot (live demo) · slot <b>${clock(s.t0)} → ${clock(s.t0 + s.plan)}</b>`
      : `<b>≈ ${clock(s.est)}</b> to present: ${s.words} words at ${WPM} wpm (${clock(s.read)}) + ${s.steps} click${s.steps === 1 ? "" : "s"}` +
        ` · slot <b>${clock(s.t0)} → ${clock(s.t0 + s.plan)}</b>`;
    $("#pr-plan").textContent = clock(s.plan);
    if (renderedFor !== cur) { renderScript(s); renderedFor = cur; }
    $$(".nt", P.script).forEach((b) => { const k = Number(b.dataset.k); b.classList.toggle("now", k === step); b.classList.toggle("past", k < step); });
    const now = $(".nt.now", P.script);
    if (now) P.script.scrollTo({ top: now.offsetTop - 14, behavior: "smooth" });
    // next cue
    const nk = s.paras.find((q) => Number(q.dataset.step) === step + 1);
    if (step < s.steps) {
      P.cue.className = "cue";
      P.cue.innerHTML = `<b>▶ Next click (${step + 1}/${s.steps})</b> ${nk?.dataset.cue ? "shows " + nk.dataset.cue : "next build"} · at ≈ ${clock(s.t0 + s.stepAt(step + 1))}`;
    } else if (cur < slides.length - 1) {
      const n = slides[cur + 1], ns = SPEAKERS[n.speaker];
      P.cue.className = "cue slide-change";
      P.cue.style.setProperty("--nc", ns.hue);
      P.cue.innerHTML = `<b>▶ Next click: slide ${label(n)}</b> ${n.title}${n.speaker !== s.speaker ? ` · <b>hand over to ${ns.short}</b>` : ""} · at ${clock(n.t0)}`;
    } else { P.cue.className = "cue"; P.cue.innerHTML = "<b>End of the deck</b>"; }
    const after = slides.filter((t) => t.i > cur).slice(0, 2);
    P.up.innerHTML = after.length ? "Coming up: " + after.map((t) => `<span class="chip" style="--k:${SPEAKERS[t.speaker].hue}">${clock(t.t0)}</span> ${t.title}`).join(" · ") : "";
    P.dots.innerHTML = Array.from({ length: s.steps + 1 }, (_, k) => `<i class="${k < step ? "done" : k === step ? "now" : ""}"></i>`).join("");
    $$(".ov-card", $("#overview")).forEach((c, k) => c.classList.toggle("now", k === cur));
    markRunsheet();
  }

  /* ------------------------------------------------------------ timers */
  let running = false, elapsedBase = 0, startedAt = 0, slideClock = performance.now();
  const elapsed = () => elapsedBase + (running ? (performance.now() - startedAt) / 1000 : 0);
  const timerLabel = () => { if (P.timerBtn) { P.timerBtn.textContent = running ? "Pause timer" : "Start timer"; P.timerBtn.classList.toggle("on", running); } };
  function startTimer() { if (running) return; running = true; everStarted = true; startedAt = performance.now(); timerLabel(); }
  function pauseTimer() { if (!running) return; elapsedBase = elapsed(); running = false; timerLabel(); }
  function resetTimer() { running = false; elapsedBase = 0; everStarted = false; slideClock = performance.now(); timerLabel(); }
  function tick() {
    if (cur >= 0) {
      const s = slides[cur], e = elapsed(), inSlide = (performance.now() - slideClock) / 1000;
      $("#pb-clock").textContent = clock(e);
      if (!AUDIENCE) {
        P.elapsed.textContent = clock(e);
        P.slideT.textContent = clock(inSlide);
        const f = s.plan ? inSlide / s.plan : 0;
        P.bar.style.width = Math.min(100, f * 100) + "%";
        P.bar.classList.toggle("over", f > 1.15);
        if (everStarted) {
          // where we should be: the planned time of the current build
          const due = s.t0 + s.stepAt(step), d = e - due;
          P.pace.textContent = Math.abs(d) < 5 ? "on time" : d > 0 ? `${clock(d)} behind` : `${clock(-d)} ahead`;
          P.paceBox.className = "pace " + (d > 30 ? "late" : d > 5 ? "behind" : "ahead");
        } else { P.pace.textContent = everStarted ? "—" : "not started"; P.paceBox.className = "pace"; }
      }
    }
    requestAnimationFrame(tick);
  }

  /* ------------------------------------------------------------ presenting */
  const presenting = () => body.classList.contains("presenting");
  let ownFullscreen = false;
  function present(i = cur, fromStart = false) {
    if (fromStart) i = 0;
    toggle(null, false);
    body.classList.add("presenting");
    go(i, 0, { dir: 1 });
    const d = document.documentElement;
    const req = d.requestFullscreen || d.webkitRequestFullscreen;
    if (req && !(document.fullscreenElement || document.webkitFullscreenElement)) {
      try { const p = req.call(d); ownFullscreen = true; p?.catch?.(() => { ownFullscreen = false; }); } catch { ownFullscreen = false; }
    }
    if (!running) startTimer();
    showBar();
    setTimeout(fit, 60);
  }
  function exitPresent() {
    if (AUDIENCE || !presenting()) return;
    body.classList.remove("presenting");
    if (ownFullscreen && (document.fullscreenElement || document.webkitFullscreenElement)) (document.exitFullscreen || document.webkitExitFullscreen).call(document);
    ownFullscreen = false;
    setTimeout(() => { fit(); scaleThumbs(strip); paint(); }, 60);
  }
  document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement && ownFullscreen) { ownFullscreen = false; exitPresent(); }
    setTimeout(fit, 60);
  });
  // the controls along the bottom fade in when the mouse moves, as in Google Slides
  const bar = $("#pres-bar");
  let barT = 0;
  function showBar() { bar.classList.add("show"); clearTimeout(barT); barT = setTimeout(() => bar.classList.remove("show"), 2600); }
  document.addEventListener("mousemove", () => { if (presenting() && !AUDIENCE) showBar(); });
  $("#pb-prev").onclick = (e) => { e.stopPropagation(); prev(); };
  $("#pb-next").onclick = (e) => { e.stopPropagation(); next(); };
  $("#pb-exit").onclick = (e) => { e.stopPropagation(); exitPresent(); };

  /* ------------------------------------------------------------ presenter ⇄ audience windows */
  const chan = "BroadcastChannel" in window ? new BroadcastChannel("ansera-deck") : null;
  let fromPeer = false;
  function broadcast() { if (chan && !fromPeer) chan.postMessage({ type: "pos", i: cur, k: step }); }
  if (chan) chan.onmessage = (e) => {
    const m = e.data;
    if (m.type === "pos" && (m.i !== cur || m.k !== step)) { fromPeer = true; go(m.i, m.k, { silent: true }); fromPeer = false; }
    if (m.type === "hello" && !AUDIENCE) { peerOpen = true; broadcast(); }
    if (m.type === "bye" && !AUDIENCE) peerOpen = false;
  };
  // presenter view is on while an audience window is open (opened from here, or from its own ?audience link)
  let audWin = null, peerOpen = false;
  const presenterView = () => (audWin && !audWin.closed) || peerOpen;
  if (AUDIENCE && chan) window.addEventListener("pagehide", () => chan.postMessage({ type: "bye" }));
  function openAudience() {
    const u = new URL(location.href); u.searchParams.set("audience", ""); u.hash = "";
    audWin = window.open(u.toString().replace("audience=", "audience"), "ansera-audience", "width=1280,height=720");
    if (!running) startTimer();
  }

  /* ------------------------------------------------------------ grid and run sheet */
  const overview = $("#overview"), runsheet = $("#runsheet");
  function buildOverview() {
    const grid = $(".ov-grid", overview);
    grid.innerHTML = "";
    slides.forEach((s) => {
      const c = el("button", "ov-card");
      c.style.setProperty("--c", SPEAKERS[s.speaker].hue);
      c.append(thumb(s));
      c.append(el("div", "meta", `<b>${label(s)}. ${s.title}</b><code>${clock(s.t0)}</code>`));
      c.onclick = () => { toggle(overview, false); go(s.i, 0); };
      grid.append(c);
    });
    scaleThumbs(grid);
  }
  function buildRunsheet() {
    const tb = $("tbody", runsheet);
    tb.innerHTML = "";
    let lastSp = null;
    const per = {};
    slides.forEach((s) => { per[s.speaker] = (per[s.speaker] || 0) + s.plan; });
    const words = slides.reduce((a, s) => a + (s.fixed ? 0 : s.words), 0);
    $(".rs-sum", runsheet).innerHTML = `<span>Estimated total <b>${clock(total)}</b></span><span>${slides.length} slides, ${slides.reduce((a, s) => a + s.steps, 0)} clicks inside slides</span>` +
      Object.entries(per).map(([k, v]) => `<span style="--c:${SPEAKERS[k].hue}"><b>${SPEAKERS[k].short}</b> ${clock(v)}</span>`).join("") +
      `<span>Script: ${words} words ≈ <b>${clock(words / WPS)}</b> at ${WPM} wpm, plus ${CLICK} s a click and the live demo</span>`;
    slides.forEach((s) => {
      if (s.speaker !== lastSp) {
        lastSp = s.speaker;
        tb.append(el("tr", "ch", `<td colspan="4" style="--c:${SPEAKERS[s.speaker].hue}"><span class="sp"></span>${SPEAKERS[s.speaker].name}</td>`));
      }
      // the yellow CLICK chips jump to the build that click shows (or the next slide); the slide's name jumps to its start
      const steps = s.paras.map((p, idx) => {
        const k = Number(p.dataset.step);
        const isLast = !s.paras.slice(idx + 1).some((q) => Number(q.dataset.step) === k);
        const nk = s.paras.find((q) => Number(q.dataset.step) === k + 1);
        const chip = (i, kk, text) => ` <button class="click" data-i="${i}" data-k="${kk}" title="Go to this point">${text}</button>`;
        const click = isLast && k < s.steps ? chip(s.i, k + 1, `CLICK${nk?.dataset.cue ? " · " + nk.dataset.cue : ""}`) : isLast && s.i < slides.length - 1 ? chip(s.i + 1, 0, "CLICK · next slide") : "";
        return `<div class="rs-p" data-i="${s.i}" data-k="${k}"><code>${clock(s.t0 + s.paraAt[idx])}</code> ${p.innerHTML}${click}</div>`;
      }).join("");
      const len = `${clock(s.plan)}<br><small style="color:var(--dim);font-weight:500">${s.fixed ? "fixed" : `${s.words} words`}</small>`;
      const tr = el("tr", "", `<td class="t">${clock(s.t0)}</td><td class="t">${len}</td><td><button class="rs-go" data-i="${s.i}" data-k="0" title="Go to the start of this slide">${label(s)}. ${s.title}</button><br><small style="color:var(--dim)">${s.steps} click${s.steps === 1 ? "" : "s"}</small></td><td>${steps}</td>`);
      tb.append(tr);
    });
  }
  // jump from the run sheet; with presenter view on, it stays open (the audience sees the slide), otherwise it closes
  $("tbody", runsheet).addEventListener("click", (e) => {
    const b = e.target.closest("button[data-i]"); if (!b) return;
    b.blur();
    const i = Number(b.dataset.i), k = Number(b.dataset.k);
    if (!presenterView()) toggle(runsheet, false);
    go(i, k, { dir: i >= cur ? 1 : -1 });
  });
  function markRunsheet() {
    if (!runsheet.classList.contains("show")) return;
    $$(".rs-p.now", runsheet).forEach((d) => d.classList.remove("now"));
    const now = $$(`.rs-p[data-i="${cur}"]`, runsheet).filter((d) => Number(d.dataset.k) === step);
    now.forEach((d) => d.classList.add("now"));
    now[0]?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }
  function toggle(ov, show) {
    const on = ov ? show ?? !ov.classList.contains("show") : false;
    [overview, runsheet].forEach((o) => o.classList.remove("show"));
    if (on) { (ov === overview ? buildOverview : buildRunsheet)(); ov.classList.add("show"); if (ov === runsheet) markRunsheet(); }
  }
  $$(".overlay .x").forEach((b) => (b.onclick = () => toggle(b.closest(".overlay"), false)));
  $("#rs-print").onclick = () => window.print();

  /* ------------------------------------------------------------ keys, clicks, buttons */
  const help = $("#help");
  let goBuf = "", goTimer = 0;
  const clearGo = () => { goBuf = ""; $("#goto").classList.remove("show"); };
  function handleKey(e) {
    const k = e.key.toLowerCase(), shift = e.shiftKey;
    if (["arrowright", "pagedown", " ", "enter", "arrowdown"].includes(k)) {
      if (goBuf) { const n = Number(goBuf); clearGo(); go(n - 1); return; }
      shift ? go(cur + 1, 0) : next();
    }
    else if (["arrowleft", "pageup", "arrowup", "backspace"].includes(k)) shift ? go(cur - 1, 0, { dir: -1 }) : prev();
    else if (k === "home") go(0, 0, { dir: -1 });
    else if (k === "end") go(slides.length - 1, slides[slides.length - 1].steps);
    else if (/^[0-9]$/.test(k)) { goBuf += k; $("#goto").textContent = `→ ${goBuf}`; $("#goto").classList.add("show"); clearTimeout(goTimer); goTimer = setTimeout(clearGo, 2500); }
    else if (k === "escape") { if ($(".overlay.show")) toggle(null, false); else exitPresent(); clearGo(); }
    else if (AUDIENCE) return;
    else if (k === "p") present(cur, shift);
    else if (k === "v") openAudience();
    else if (k === "n") toggleNotes();
    else if (k === "o") toggle(overview);
    else if (k === "s") toggle(runsheet);
    else if (k === "t") (running ? pauseTimer() : startTimer());
    else if (k === "r") resetTimer();
    else if (k === "f") fullscreen();
    else if (k === "b" || k === ".") screen.classList.toggle("black");
    else if (k === "?" || k === "h") help.classList.toggle("show");
  }
  window.addEventListener("keydown", (e) => {
    if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return;
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter" && !AUDIENCE) { e.preventDefault(); present(cur, e.shiftKey); return; }
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    if ([" ", "ArrowRight", "ArrowLeft", "ArrowUp", "ArrowDown", "PageUp", "PageDown", "Backspace"].includes(e.key)) e.preventDefault();
    handleKey(e);
  });
  // a click on the slide (not on its buttons) is "next"; swipes work too
  stage.addEventListener("click", (e) => { if (e.target.closest("button, input, a, .interactive")) return; next(); });
  let tx = 0;
  stage.addEventListener("touchstart", (e) => { tx = e.touches[0].clientX; }, { passive: true });
  stage.addEventListener("touchend", (e) => { const d = e.changedTouches[0].clientX - tx; if (Math.abs(d) > 50) (d < 0 ? next() : prev()); }, { passive: true });
  // the mouse wheel over the filmstrip scrolls it sideways
  strip.addEventListener("wheel", (e) => { if (Math.abs(e.deltaY) > Math.abs(e.deltaX)) { strip.scrollLeft += e.deltaY; e.preventDefault(); } }, { passive: false });

  function toggleNotes() { body.classList.toggle("no-notes"); save("notes", body.classList.contains("no-notes") ? "off" : "on"); setTimeout(fit, 30); }
  function fullscreen() {
    const d = document;
    if (d.fullscreenElement || d.webkitFullscreenElement) (d.exitFullscreen || d.webkitExitFullscreen).call(d);
    else (d.documentElement.requestFullscreen || d.documentElement.webkitRequestFullscreen)?.call(d.documentElement);
  }
  if (!AUDIENCE) {
    if (store("notes", "on") === "off") body.classList.add("no-notes");
    $("#btn-notes").onclick = toggleNotes;
    $("#btn-home").onclick = () => go(0, 0, { dir: -1 });
    $("#btn-grid").onclick = () => toggle(overview);
    $("#btn-run").onclick = () => toggle(runsheet);
    $("#btn-aud").onclick = openAudience;
    $("#btn-play").onclick = () => present(cur);
    $("#btn-play-start").onclick = () => present(0, true);
    $("#btn-reset").onclick = resetTimer;
    P.timerBtn.onclick = () => (running ? pauseTimer() : startTimer());
    $("#btn-prev").onclick = prev; $("#btn-next").onclick = next;
    // drag the notes panel's left edge to resize it
    const rz = $(".notes-panel .resize-x");
    const setW = (w) => { document.documentElement.style.setProperty("--notes-w", w + "px"); fit(); };
    const savedW = Number(store("notes-w", 0)); if (savedW) setW(savedW);
    rz.onpointerdown = (e) => {
      rz.setPointerCapture(e.pointerId);
      rz.onpointermove = (m) => setW(Math.max(300, Math.min(innerWidth * 0.6, innerWidth - m.clientX)));
      rz.onpointerup = () => { rz.onpointermove = null; save("notes-w", parseInt(getComputedStyle(document.documentElement).getPropertyValue("--notes-w"))); };
    };
    $("#pr-total").textContent = `Talk / ${clock(total)}`;
    setTimeout(() => help.classList.add("show"), 600);
    setTimeout(() => help.classList.remove("show"), 7000);
  }
  // a clicked button mustn't keep the focus, or Space would press it again
  document.addEventListener("click", (e) => { const b = e.target.closest("button, a, .fs-item"); if (b && !b.closest(".overlay")) b.blur(); });

  /* ------------------------------------------------------------ helpers the slide widgets use */
  const ctx = {
    $, $$, el, clock,
    pulse: () => Aurora.pulse(),
    tint: (a, b, e) => Aurora.tint(a, b, e),
    get step() { return step; },
  };
  window.DECK = { go, next, prev, present, exitPresent, slides, ctx, SPEAKERS, total };

  /* ------------------------------------------------------------ start */
  buildStrip();
  const [hi, hk] = location.hash.slice(1).split(".").map(Number);
  go(Number.isFinite(hi) && hi > 0 ? hi - 1 : 0, hk || 0, { dir: 1, silent: AUDIENCE });
  if (AUDIENCE && chan) chan.postMessage({ type: "hello" });
  requestAnimationFrame(tick);
})();
