/* The slide widgets: each one follows the clicks (enter / step / leave), so its animation always matches the build on
   screen, forwards or backwards. thumb(clone, lastStep) dresses the static copy used in the filmstrip and the grid. */
(() => {
  "use strict";
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  const el = (tag, cls, html) => { const n = document.createElement(tag); if (cls) n.className = cls; if (html != null) n.innerHTML = html; return n; };
  const wait = (ms) => new Promise((r) => setTimeout(r, ms));
  const NS = "http://www.w3.org/2000/svg";
  const svgEl = (tag, attrs = {}) => { const n = document.createElementNS(NS, tag); Object.entries(attrs).forEach(([k, v]) => n.setAttribute(k, v)); return n; };
  // a cancellable sequence: a newer run (or leaving the slide) makes the old one throw at its next alive()
  function runner() {
    let tok = 0;
    return {
      stop() { tok++; },
      go(fn) { const my = ++tok; const alive = () => { if (my !== tok) throw new Error("stale"); }; return Promise.resolve().then(() => fn(alive)).catch((e) => { if (e?.message !== "stale") console.error(e); }); },
    };
  }

  /* ================================================================ problem: messages pile up at night */
  const NIGHT = ["<b>Dewi</b> Any brownies left?", "<b>Andi</b> Do you deliver to Bekasi?", "<b>Sari</b> How much is the layer cake?", "<b>Budi</b> Are you open tomorrow?", "<b>Rina</b> Cash on delivery OK?", "<b>Tono</b> Is it in stock?", "<b>Lina</b> I'd like 3 boxes 🙏", "<b>Agus</b> Hello? 😕", "<b>Maya</b> Still open?", "<b>Joko</b> Can I pay by bank transfer?"];
  const problem = (() => {
    let timer = 0;
    const clear = (s) => { $(".np-list", s).innerHTML = ""; $(".np-badge", s).textContent = "0"; };
    return {
      enter(s) { clearInterval(timer); clear(s); },
      step(s, k) {
        clearInterval(timer);
        if (k < 1) { clear(s); return; }
        let n = 0;
        const list = $(".np-list", s), badge = $(".np-badge", s);
        const add = () => {
          list.append(el("div", "", NIGHT[n % NIGHT.length]));
          while (list.children.length > 5) list.firstChild.remove();
          n++; badge.textContent = n; badge.classList.remove("bump"); void badge.offsetWidth; badge.classList.add("bump");
          if (n >= 47) clearInterval(timer);
        };
        add(); timer = setInterval(add, 520);
      },
      leave() { clearInterval(timer); },
      thumb(c) { $(".np-list", c).innerHTML = NIGHT.slice(0, 5).map((t) => `<div>${t}</div>`).join(""); $(".np-badge", c).textContent = "47"; },
    };
  })();

  /* ================================================================ solution: a chat that follows the features */
  const SOL = [
    [["bot", "Hi! 👋 Welcome to Rally Point Courts. Ask me anything, book a court, or order gear."]],
    [["me", "is there parking?"], ["bot", "Yes! A car park next door ($1.20 an hour) 🚗"], ["me", "can I book a badminton court tomorrow 7pm?"], ["bot", "🏸 Court 1 · tomorrow 7–8pm<br><b>Total: $20.00</b> · reply CONFIRM"]],
    [["me", "CONFIRM"], ["bot", "✅ Booked! Invoice sent to your email 🧾 Pay here: <span class='lnk'>checkout.xendit.co/…</span>"], ["bot", "⏰ Reminder: your court is tomorrow at 7pm. See you then!"]],
  ];
  const solution = (() => {
    const r = runner();
    let last = -1;
    const paint = (box, upto, animateFrom) => r.go(async (alive) => {
      box.innerHTML = "";
      let idx = 0;
      for (const [si, group] of SOL.slice(0, upto + 1).entries()) {
        for (const [who, text] of group) {
          const b = el("div", `bub ${who}`, `${text}<small>${who === "me" ? "18:0" + (idx % 10) : "✓✓"}</small>`);
          b.dataset.msg = "";
          if (si >= animateFrom) {
            if (who === "bot") { const t = el("div", "bub bot", '<div class="typing"><span></span><span></span><span></span></div>'); box.append(t); await wait(650); alive(); t.remove(); }
            box.append(b); void b.offsetWidth; b.classList.add("in"); await wait(who === "me" ? 380 : 260); alive();
          } else { box.append(b); b.classList.add("in"); }
          idx++;
          while (box.children.length > 7) box.firstChild.remove();
        }
      }
    });
    return {
      enter(s) { r.stop(); $(".msgs", s).innerHTML = ""; last = -1; },
      step(s, k, dir) { paint($(".msgs", s), k, dir > 0 && last < k ? (last < 0 ? 0 : k) : 99); last = k; },
      leave() { r.stop(); },
      thumb(c) { $(".msgs", c).innerHTML = SOL.flat().slice(-6).map(([w, t]) => `<div class="bub ${w} in" data-msg>${t}<small>✓✓</small></div>`).join(""); },
    };
  })();

  /* ================================================================ competitors: the positioning map */
  const competitors = {
    step(s, k) {
      $$(".dot", s).forEach((d, i) => {
        const at = Number(d.dataset.at), show = k >= at, isA = d.dataset.k === "ansera";
        clearTimeout(d._t);
        if (show && !d.classList.contains("in")) d._t = setTimeout(() => d.classList.add("in"), 250);
        if (!show) d.classList.remove("in");
        d.classList.toggle("dim", !isA && k >= 3);
      });
    },
    leave(s) { $$(".dot", s).forEach((d) => { clearTimeout(d._t); d.classList.remove("in", "dim"); }); },
    thumb(c) { $$(".dot", c).forEach((d) => d.classList.add("in")); },
  };

  /* ================================================================ architecture & user flow: the diagram */
  // laid out in columns (actors → edge → ingesters → queues → workers → external services) and one row per plane, so the
  // lines run straight along their row and none of them cross. Only the main links are drawn (see the footnote).
  const K = { actor: "#f6c34a", ext: "#ff8fc0", gcp: "#22d3ee", edge: "#ff7a45", run: "#3b8bff", queue: "#a66bff", data: "#25d366", dlq: "#ff5a5a" };
  // [x, y, w, h, kind, icon, title ("|" breaks a line), subtitle]
  const NODES = {
    owner: [0, 40, 116, 62, "actor", "👩‍🍳", "Owner", "dashboard"],
    customer: [0, 275, 116, 62, "actor", "🙋", "Customer", "on WhatsApp"],
    firebase: [148, 40, 172, 62, "gcp", "🔥", "Firebase Hosting", "frontend"],
    meta: [148, 275, 172, 62, "ext", "💬", "WhatsApp", "Meta Cloud API"],
    xendit: [148, 410, 172, 62, "ext", "💳", "Xendit", "hosted payment page"],
    sched: [148, 545, 172, 58, "gcp", "⏱️", "Cloud Scheduler", "every hour"],
    lb: [360, 40, 120, 432, "edge", "⚖️", "Load|balancer", "HTTPS · Cloud Armor WAF · one public IP · routes by path"],
    config: [516, 40, 205, 62, "run", "⚙️", "configuration-service", "main backend · tenants"],
    ming: [516, 275, 205, 62, "run", "📥", "messaging-ingester", "verify · queue · 200"],
    ping: [516, 410, 205, 62, "run", "🧾", "payment-ingester", "Xendit links · webhook"],
    njob: [516, 545, 205, 58, "run", "⏰", "notification-job", "hourly reminders"],
    sql: [771, 130, 170, 100, "data", "🐘", "Cloud SQL", "PostgreSQL · one shared schema for every business"],
    mq: [771, 275, 170, 62, "queue", "📬", "messaging-queue", "Pub/Sub"],
    pq: [771, 410, 170, 62, "queue", "📬", "payment-queue", "Pub/Sub"],
    dlq: [771, 545, 170, 58, "dlq", "☠️", "dead letter", "5 attempts · alert"],
    msvc: [985, 275, 195, 62, "run", "🤖", "messaging-service", "LLM turn · scales out"],
    psvc: [985, 410, 195, 62, "run", "🧮", "processing-service", "verify · paid · PDFs"],
    vertex: [1232, 275, 165, 62, "gcp", "✨", "Vertex AI", "Gemini"],
    brevo: [1232, 410, 165, 62, "ext", "✉️", "Brevo", "email to customers"],
    gcs: [1232, 545, 165, 58, "data", "🗂️", "Cloud Storage", "PDFs · signed URLs"],
  };
  // the shared platform, a box in the top-right corner (two columns); Secret Manager has its own key, so
  // configuration-service can point at it
  const PLAT = { x: 1060, y: 38, w: 337, items: [["secret", "🔐 Secret Manager"], ["plat", "📈 Cloud Logging"], ["plat", "📊 Monitoring"], ["plat", "📦 Artifact Registry"], ["plat", "🏗️ Cloud Build"], ["plat", "🧩 Terraform"]] };
  PLAT.iw = (PLAT.w - 30) / 2; PLAT.h = 8 + Math.ceil(PLAT.items.length / 2) * 38;
  // a right-angled path through the points, with rounded corners
  const orth = (...pts) => {
    let d = `M${pts[0][0]},${pts[0][1]}`;
    for (let i = 1; i < pts.length - 1; i++) {
      const [px, py] = pts[i - 1], [cx, cy] = pts[i], [nx, ny] = pts[i + 1];
      const r = Math.min(10, Math.hypot(cx - px, cy - py) / 2, Math.hypot(nx - cx, ny - cy) / 2);
      d += ` L${cx - Math.sign(cx - px) * r},${cy - Math.sign(cy - py) * r} Q${cx},${cy} ${cx + Math.sign(nx - cx) * r},${cy + Math.sign(ny - cy) * r}`;
    }
    const [lx, ly] = pts[pts.length - 1];
    return `${d} L${lx},${ly}`;
  };
  // an edge: its points, its label (and where it goes), and its style. dash = a call out (verify · send · create),
  // fail = a failed delivery, both = arrows at both ends
  const E = (pts, label = "", at, more = {}) => ({ d: orth(...pts), label, at, ...more });
  const EDGES = {
    // control plane (row 1)
    "o-fb": E([[116, 71], [148, 71]]),
    "fb-lb": E([[320, 71], [360, 71]], "API calls", [340, 124]),
    "lb-cfg": E([[480, 71], [516, 71]], "REST", [498, 63]),
    "cfg-sql": E([[690, 102], [690, 180], [771, 180]], "config · catalog", [760, 121], { both: true }),
    "cfg-sec": E([[721, 61], [1070, 61]], "secrets", [900, 54]),
    // message plane (row 2)
    "c-meta": E([[116, 306], [148, 306]], "", null, { both: true }),
    "meta-lb": E([[320, 306], [360, 306]], "signed webhook", [340, 262]),
    "lb-ming": E([[480, 306], [516, 306]]),
    "ming-cfg": E([[618, 275], [618, 102]], "verify signature", [618, 248], { dash: true }),
    "ming-mq": E([[721, 306], [771, 306]], "publish", [746, 298]),
    "mq-ms": E([[941, 306], [985, 306]], "pull", [963, 298]),
    "ms-vx": E([[1180, 306], [1232, 306]], "Gemini", [1206, 298]),
    "ms-sql": E([[1005, 275], [1005, 215], [941, 215]], "chat state", [977, 208], { both: true }),
    "ms-cfg": E([[1045, 275], [1045, 90], [721, 90]], "send reply", [850, 83], { dash: true }),
    graph: E([[540, 102], [540, 225], [234, 225], [234, 275]], "Graph API · replies", [290, 216], { dash: true }),
    // payment plane (row 3)
    "ms-pay": E([[1040, 337], [1040, 372], [618, 372], [618, 410]], "create payment link", [830, 365], { dash: true }),
    "ms-ps": E([[1150, 337], [1150, 410]], "invoice", [1150, 379]),
    "c-x": E([[58, 337], [58, 441], [148, 441]], "pays", [58, 395]),
    "x-lb": E([[320, 441], [360, 441]], "webhook", [340, 398]),
    "lb-ping": E([[480, 441], [516, 441]]),
    "pay-x": E([[618, 472], [618, 505], [234, 505], [234, 472]], "create link", [420, 498], { dash: true }),
    "ping-pq": E([[721, 441], [771, 441]], "publish", [746, 433]),
    "pq-ps": E([[941, 441], [985, 441]], "pull", [963, 433]),
    "ps-brevo": E([[1180, 441], [1232, 441]], "email", [1206, 433]),
    "ps-gcs": E([[1110, 472], [1110, 574], [1232, 574]], "PDFs", [1170, 567]),
    "pq-dlq": E([[856, 472], [856, 545]], "5 failures", [856, 512], { dash: true, fail: true }),
    // reminders (row 4)
    "sch-nj": E([[320, 574], [516, 574]], "hourly", [418, 567]),
  };
  const ALL = [...Object.keys(NODES), ...Object.keys(EDGES), "plat", "secret", "gcp"];
  // each slide's builds: what's shown (cumulative on the overview), what glows, and the packets that run
  const PLAN = {
    planes: [
      { show: ["gcp"], flows: [] },
      { color: "#ff4f9a", show: ["owner", "firebase", "lb", "config", "sql", "o-fb", "fb-lb", "lb-cfg", "cfg-sql"], flows: [["o-fb", "fb-lb", "lb-cfg", "cfg-sql"]] },
      { color: "#3b8bff", show: ["customer", "meta", "c-meta", "meta-lb", "lb-ming", "ming", "ming-cfg", "ming-mq", "mq", "mq-ms", "msvc", "ms-vx", "vertex", "ms-sql", "ms-cfg", "graph"], hot: ["lb"], flows: [["c-meta", "meta-lb", "lb-ming", "ming-mq", "mq-ms", "ms-vx"], ["ms-cfg", "graph", "-c-meta"]] },
      { color: "#25d366", show: ["xendit", "c-x", "x-lb", "lb-ping", "ping", "ping-pq", "pq", "pq-ps", "psvc", "ps-gcs", "gcs", "ps-brevo", "brevo", "ms-pay", "ms-ps", "pay-x"], hot: ["lb"], flows: [["c-x", "x-lb", "lb-ping", "ping-pq", "pq-ps", "ps-gcs"], ["ps-brevo"]] },
      { color: "#22d3ee", show: ["secret", "cfg-sec", "plat", "sched", "njob", "sch-nj", "dlq", "pq-dlq"], flows: [["sch-nj"], ["cfg-sec"]] },
    ],
    flow1: [
      { hot: ["customer", "meta", "lb", "ming", "c-meta", "meta-lb", "lb-ming"], flows: [["c-meta", "meta-lb", "lb-ming"]] },
      { hot: ["ming", "config", "mq", "ming-cfg", "ming-mq"], flows: [["ming-cfg", "-ming-cfg", "ming-mq"]] },
      { hot: ["ming", "mq", "ming-mq"], flows: [["ming-mq"], ["ming-mq"], ["ming-mq"]] },
      { hot: ["mq", "msvc", "sql", "vertex", "mq-ms", "ms-sql", "ms-vx"], flows: [["mq-ms", "ms-sql", "-ms-sql", "ms-vx"]] },
      { hot: ["msvc", "config", "secret", "meta", "customer", "ms-cfg", "graph", "c-meta", "cfg-sec"], flows: [["ms-cfg", "graph", "-c-meta"], ["-cfg-sec"]] },
      { hot: ["msvc", "sql", "psvc", "ping", "xendit", "brevo", "ms-sql", "ms-ps", "ps-brevo", "ms-pay", "pay-x"], flows: [["ms-sql"], ["ms-ps", "ps-brevo"], ["ms-pay", "pay-x"]] },
    ],
    flow2: [
      { hot: ["customer", "xendit", "lb", "ping", "pq", "c-x", "x-lb", "lb-ping", "ping-pq"], flows: [["c-x", "x-lb", "lb-ping", "ping-pq"]] },
      // the receipt goes out by email (Brevo) and on WhatsApp (through configuration-service, as every message does)
      { hot: ["pq", "psvc", "sql", "gcs", "brevo", "config", "meta", "customer", "pq-ps", "ps-gcs", "ps-brevo", "graph", "c-meta"], flows: [["pq-ps", "ps-gcs"], ["pq-ps", "ps-brevo"], ["graph", "-c-meta"]] },
      { hot: ["sched", "njob", "sql", "config", "meta", "customer", "sch-nj", "graph", "c-meta"], flows: [["sch-nj"], ["graph", "-c-meta"]] },
    ],
  };
  const PLANE_COL = { planes: "#ff4f9a", flow1: "#3b8bff", flow2: "#25d366" };

  function buildArch(box) {
    const svg = svgEl("svg", { viewBox: "-10 0 1432 655", preserveAspectRatio: "xMidYMid meet" });
    const defs = svgEl("defs"), mk = svgEl("marker", { id: "dg-arrow", viewBox: "0 0 10 10", refX: 9, refY: 5, markerWidth: 9, markerHeight: 9, markerUnits: "userSpaceOnUse", orient: "auto-start-reverse" });
    mk.append(svgEl("path", { d: "M0,0 L10,5 L0,10 z", fill: "context-stroke" })); defs.append(mk); svg.append(defs);
    const zone = svgEl("g", { class: "dg-node zone", "data-k": "gcp" });
    zone.append(svgEl("rect", { x: 340, y: 8, width: 1072, height: 642, rx: 22 }));
    const zt = svgEl("text", { x: 360, y: 28 }); zt.textContent = "GOOGLE CLOUD · ASIA-SOUTHEAST1 (SINGAPORE) · DECLARED IN TERRAFORM"; zone.append(zt);
    const pt = svgEl("text", { x: PLAT.x + 8, y: 28 }); pt.textContent = "SHARED PLATFORM"; zone.append(pt);
    // the footnote and the legend, along the bottom of the zone
    const nt = svgEl("text", { class: "nt", x: 360, y: 622 }); nt.textContent = "Only the main links are drawn: every service reads and writes Cloud SQL, and every WhatsApp message goes out through configuration-service."; zone.append(nt);
    [["", "request / event", 360], ["dash", "call out: verify · send · create", 530], ["dash fail", "failed delivery", 790]].forEach(([cls, txt, x]) => {
      zone.append(svgEl("line", { class: "lg " + cls, x1: x, y1: 638, x2: x + 30, y2: 638 }));
      const t = svgEl("text", { class: "nt", x: x + 38, y: 642 }); t.textContent = txt; zone.append(t);
    });
    svg.append(zone);
    const edges = svgEl("g"), labels = svgEl("g"), nodes = svgEl("g"), pkts = svgEl("g");
    svg.append(edges, nodes, labels, pkts);
    Object.entries(EDGES).forEach(([k, e]) => {
      const p = svgEl("path", { d: e.d, class: "dg-edge" + (e.dash ? " dash" : "") + (e.fail ? " fail" : ""), "data-k": k, "marker-end": "url(#dg-arrow)" });
      if (e.both) p.setAttribute("marker-start", "url(#dg-arrow)");
      edges.append(p);
      if (e.label) { const t = svgEl("text", { class: "dg-label", "data-k": k, "text-anchor": "middle", x: e.at[0], y: e.at[1] }); t.textContent = e.label; labels.append(t); }
    });
    Object.entries(NODES).forEach(([k, [x, y0, w, h, kind, ic, t, s]]) => {
      let y = y0;
      const g = svgEl("g", { class: "dg-node", "data-k": k, style: `--nk:${K[kind]}` });
      g.append(svgEl("rect", { class: "box", x, y, width: w, height: h, rx: 14 }));
      const big = h >= 100;
      const icon = svgEl("text", { class: "ic", x: x + 10, y: big ? y + 36 : y + h / 2 + 8 }); icon.textContent = ic; g.append(icon);
      const tl = t.split("|");
      tl.forEach((line, i) => { const tt = svgEl("text", { class: "t", x: x + 40, y: (big ? y + 32 : s ? y + h / 2 - 2 : y + h / 2 + 6) + i * 19 }); tt.textContent = line; g.append(tt); });
      if (s) {
        if (big) {
          y += (tl.length - 1) * 19;
          // wrap the long sub-title over a few lines, as many characters as the box is wide
          const max = Math.floor((w - 24) / 6.6), ws = s.split(" "); let line = ""; const lines = [];
          ws.forEach((wd) => { if ((line + " " + wd).length > max) { lines.push(line); line = wd; } else line = line ? line + " " + wd : wd; });
          lines.push(line);
          lines.forEach((ln, i) => { const st = svgEl("text", { class: "s", x: x + 14, y: y + 58 + i * 18 }); st.textContent = ln; g.append(st); });
        } else { const st = svgEl("text", { class: "s", x: x + 40, y: y + h / 2 + 16 }); st.textContent = s; g.append(st); }
      }
      nodes.append(g);
    });
    // the shared platform box
    const plat = svgEl("g", { class: "dg-plat", "data-k": "plat" });
    plat.append(svgEl("rect", { class: "frame", x: PLAT.x, y: PLAT.y, width: PLAT.w, height: PLAT.h, rx: 14 }));
    nodes.append(plat);
    PLAT.items.forEach(([key, it], i) => {
      const x = PLAT.x + 10 + (i % 2) * (PLAT.iw + 10), y = PLAT.y + 8 + Math.floor(i / 2) * 38;
      const g = key === "plat" ? plat : nodes.appendChild(svgEl("g", { class: "dg-plat", "data-k": key }));
      g.append(svgEl("rect", { x, y, width: PLAT.iw, height: 30, rx: 9 }));
      const t = svgEl("text", { x: x + PLAT.iw / 2, y: y + 20, "text-anchor": "middle" }); t.textContent = it; g.append(t);
    });
    box.append(svg);
    // measure the edges, so they can draw themselves in
    $$(".dg-edge", svg).forEach((p) => p.style.setProperty("--len", p.getTotalLength()));
    return { svg, pkts };
  }

  const arch = (() => {
    const st = new WeakMap();
    function state(plane, k) {
      const steps = PLAN[plane], shown = new Set(), hot = new Set();
      if (plane === "planes") {
        for (let i = 0; i <= k; i++) steps[i].show.forEach((x) => shown.add(x));
        steps[k].show.forEach((x) => hot.add(x));
      } else ALL.forEach((x) => shown.add(x));
      (steps[k].hot || []).forEach((x) => { hot.add(x); shown.add(x); });
      return { shown, hot, flows: steps[k].flows, color: steps[k].color || PLANE_COL[plane] };
    }
    function paintState(S, k) {
      const { shown, hot, color } = state(S.plane, k);
      S.svg.style.setProperty("--ek", color);
      $$("[data-k]", S.svg).forEach((n) => {
        const key = n.dataset.k, was = n.classList.contains("shown");
        n.classList.toggle("shown", shown.has(key));
        n.classList.toggle("hot", hot.has(key));
        if (!was && shown.has(key) && n.classList.contains("dg-node") && !S.thumb) { n.classList.remove("pop"); void n.getBoundingClientRect(); n.classList.add("pop"); }
      });
    }
    function animatePackets(S, flows, color) {
      cancelAnimationFrame(S.raf);
      S.pkts.innerHTML = "";
      if (!flows.length) return;
      const chains = flows.map((chain) => chain.map((id) => { const rev = id.startsWith("-"); const p = $(`.dg-edge[data-k="${rev ? id.slice(1) : id}"]`, S.svg); return { p, rev, len: p.getTotalLength() }; }));
      const dots = chains.map((c, i) => {
        const g = svgEl("g", { class: "dg-pkt", style: `--pk:${color}` });
        g.append(svgEl("circle", { r: 13, fill: color, opacity: 0.25 }), svgEl("circle", { r: 7, fill: "#fff" }), svgEl("circle", { r: 5, fill: color }));
        S.pkts.append(g);
        return { g, c, total: c.reduce((a, s) => a + s.len, 0), delay: i * 0.9 };
      });
      const SPEED = 330; // svg units a second
      const t0 = performance.now();
      const frame = (t) => {
        const e = (t - t0) / 1000;
        dots.forEach((d) => {
          const dur = d.total / SPEED, cycle = dur + 1.1;
          let u = (e - d.delay) % cycle;
          if (e < d.delay) u = -1;
          if (u < 0 || u > dur) { d.g.setAttribute("opacity", 0); return; }
          let dist = u * SPEED, seg = d.c[0];
          for (const s of d.c) { if (dist <= s.len) { seg = s; break; } dist -= s.len; seg = s; }
          const pt = seg.p.getPointAtLength(seg.rev ? seg.len - Math.min(dist, seg.len) : Math.min(dist, seg.len));
          d.g.setAttribute("opacity", Math.min(1, u * 5, (dur - u) * 5)); d.g.setAttribute("transform", `translate(${pt.x},${pt.y})`);
        });
        S.raf = requestAnimationFrame(frame);
      };
      S.raf = requestAnimationFrame(frame);
    }
    const journey = (s, k) => $$(".journey li", s).forEach((li) => { const j = Number(li.dataset.k); li.classList.toggle("on", j === k); li.classList.toggle("done", j < k); });
    return {
      enter(s) {
        const box = $(".arch", s);
        if (!st.has(s)) st.set(s, { ...buildArch(box), raf: 0, plane: box.dataset.plane });
      },
      step(s, k) {
        const S = st.get(s);
        paintState(S, k);
        journey(s, k);
        clearTimeout(S.t);
        const { flows, color } = state(S.plane, k);
        S.t = setTimeout(() => animatePackets(S, flows, color), 700);
      },
      leave(s) { const S = st.get(s); if (S) { cancelAnimationFrame(S.raf); clearTimeout(S.t); S.pkts.innerHTML = ""; } },
      thumb(c, last) {
        const box = $(".arch", c);
        box.innerHTML = "";
        const S = { ...buildArch(box), plane: box.dataset.plane, thumb: true };
        // the overview shows everything; the flows show their first step
        paintState(S, S.plane === "planes" ? last : 0);
        $$(".journey li", c).forEach((li) => li.classList.remove("on", "done"));
      },
    };
  })();

  /* ================================================================ the event pipeline */
  const X = { meta: 110, ing: 345, q: 580, w: 815, db: 1050, cust: 1300 };
  const NODE_TXT = {
    meta: ["💬", "WhatsApp", "Meta · signed webhook"], ing: ["📥", "messaging-ingester", "verify · publish"], q: ["📬", "Pub/Sub", "messaging-queue"],
    w: ["🤖", "messaging-service", "one LLM turn"], db: ["🐘", "Cloud SQL", "one transaction"], cust: ["📱", "Customer", "gets the reply"],
  };
  const PIPE_HTML = `<div class="rail"></div>` +
    Object.entries(NODE_TXT).map(([k, [em, b, sm]]) => `<div class="pn" data-n="${k}" style="left:${X[k]}px;--k:var(--${{ meta: "wa", ing: "blue", q: "violet", w: "filbert", db: "wa", cust: "amber" }[k]})"><span class="em">${em}</span><b>${b}</b><small>${sm}</small>${k === "db" ? '<span class="ver"></span>' : ""}</div>`).join("") +
    `<div class="pn dlq" data-n="dlq" style="left:${X.q}px;--k:var(--red)"><b>☠️ Dead-letter queue</b><small>after 5 failed attempts · alert</small></div>
    <div class="chatlog"></div>`;
  function pipeline() {
    let pipe; const r = runner(); let loopT = 0, id = "";
    const node = (k) => $(`[data-n="${k}"]`, pipe);
    const flash = (k, cls = "flash") => { const n = node(k); n.classList.remove("flash", "bad", "warn"); void n.offsetWidth; n.classList.add(cls); setTimeout(() => n.classList.remove(cls), 800); };
    const busy = (k, on) => node(k).classList.toggle("busy", on);
    const notes = {};
    const note = (k, text, cls = "", dy = 0, x = X[k]) => {
      notes[k]?.remove();
      const n = el("div", "pnote " + cls, text); n.style.left = x + "px"; n.style.top = (k === "dlq" ? 300 : 196) + dy + "px";
      pipe.append(n); notes[k] = n;
      setTimeout(() => { n.classList.add("out"); setTimeout(() => n.remove(), 400); }, 2600);
    };
    const pkt = (label, color = "var(--wa)", x = X.meta, top = 116) => { const p = el("div", "pkt", label); p.style.left = x + "px"; p.style.top = top + "px"; p.style.setProperty("--pk", color); pipe.append(p); return p; };
    const move = (p, x, ms = 600, prop = "left") => p.animate([{ [prop]: p.style[prop] }, { [prop]: x + "px" }], { duration: ms, easing: "cubic-bezier(.45,0,.25,1)", fill: "forwards" }).finished.then(() => { p.style[prop] = x + "px"; }).catch(() => {});
    const gone = (p) => p.animate([{ opacity: 1, transform: "scale(1)" }, { opacity: 0, transform: "scale(.4)" }], { duration: 380, fill: "forwards" }).finished.then(() => p.remove()).catch(() => p.remove());
    const ver = (v, bump = true) => { const b = $(".ver", node("db")); b.textContent = v; b.classList.toggle("show", !!v); if (bump) { b.classList.add("bump"); setTimeout(() => b.classList.remove("bump"), 300); } };
    const log = (items) => { const c = $(".chatlog", pipe); c.innerHTML = ""; items.forEach((t, i) => { const s = el("span", t.r ? "r" : "", t.t); s.style.animationDelay = i * 80 + "ms"; c.append(s); }); };
    const relabel = (map) => Object.entries(map).forEach(([k, [em, b, sm]]) => { const n = node(k); $(".em", n).textContent = em; $("b", n).textContent = b; $("small", n).textContent = sm; });
    const reset = () => {
      $$(".pkt, .pnote", pipe).forEach((n) => n.remove()); Object.keys(notes).forEach((k) => delete notes[k]);
      $$(".pn", pipe).forEach((n) => n.classList.remove("busy", "flash", "bad", "warn", "lit")); ver("", false); $(".chatlog", pipe).innerHTML = "";
      relabel(NODE_TXT);
    };
    async function arrive(alive, p, { ack = true, label = "✓ signature checked" } = {}) {
      flash("meta"); await move(p, X.ing, 560); alive();
      busy("ing", true); note("ing", label); await wait(450); busy("ing", false); alive();
      await move(p, X.q, 520); alive(); flash("q");
      if (ack) { const a = pkt("200", "var(--wa)", X.ing, 160); a.classList.add("ack"); note("meta", "← 200 in ~100 ms", "green"); move(a, X.meta, 650).then(() => gone(a)); }
    }
    async function turn(alive, p, label = "LLM turn", ms = 900) {
      await move(p, X.w, 540); alive();
      busy("w", true); note("w", label, "violet"); await wait(ms); busy("w", false); alive();
      await move(p, X.db, 460); alive(); flash("db");
    }
    async function reply(alive, text = "reply") { const rp = pkt(text, "var(--amber)", X.db); await move(rp, X.cust, 600); alive(); flash("cust"); gone(rp); }
    const SCEN = {
      send: async (alive) => {
        const p = pkt("message");
        await arrive(alive, p); await wait(400); alive();
        await turn(alive, p); note("db", "✓ committed", "green"); gone(p);
        await reply(alive); await wait(900); alive();
        // and when Pub/Sub can't take it: no 200, so Meta sends it again
        const f = pkt("message", "var(--red)");
        flash("meta"); await move(f, X.ing, 560); alive(); busy("ing", true); note("ing", "✓ signature"); await wait(350); busy("ing", false);
        flash("q", "bad"); note("q", "✕ publish failed", "red"); await wait(450); alive();
        const n = pkt("503", "var(--red)", X.ing, 160); n.classList.add("ack"); n.style.color = "#ff8a8a"; n.style.borderColor = "#ff5a5a";
        note("meta", "← 503: Meta retries", "amber"); await move(n, X.meta, 650); alive(); gone(n); gone(f);
      },
      dup: async (alive) => {
        const a = pkt("wamid A");
        const first = (async () => { await arrive(alive, a); await turn(alive, a, "claim id A · answer"); note("db", "✓ id A claimed", "green"); gone(a); await reply(alive); })().catch(() => {});
        await wait(1700); alive();
        const b = pkt("wamid A", "var(--amber)");
        note("meta", "redelivery: same id A", "amber");
        await arrive(alive, b, { ack: true }); await wait(250); alive();
        await move(b, X.w, 540); alive();
        flash("w", "warn"); note("w", "id A already claimed → skip", "amber");
        await wait(500); gone(b); await first;
      },
      burst: async (alive) => {
        // three messages from one chat in a few seconds (no ordering key): each one is saved under a row lock that bumps
        // the chat's version, so the turn that started on v8 can't save its reply; it runs again, and one reply answers all three
        ver("chat v7", false);
        const a1 = pkt("A1 · hi", "var(--merry)");
        await arrive(alive, a1, { label: "✓ signature" }); alive();
        await move(a1, X.db, 600); alive(); flash("db"); ver("chat v8"); note("db", "A1 saved → v8", "violet"); gone(a1);
        const t = pkt("turn · v8", "var(--blue)", X.q);
        await move(t, X.w, 480); alive(); busy("w", true); note("w", "LLM turn reads v8", "violet");
        for (const [i, txt] of [[2, "can I order"], [3, "2 boxes pls"]]) {
          const m = pkt(`A${i} · ${txt}`, "var(--merry)");
          await arrive(alive, m, { ack: false, label: "✓ signature" }); alive();
          await move(m, X.db, 600); alive(); flash("db"); ver(`chat v${i + 7}`); gone(m);
        }
        note("db", "a burst: v8 → v10", "violet");
        await wait(600); alive(); busy("w", false);
        await move(t, X.db, 460); alive(); flash("db", "bad"); note("db", "v8 ≠ v10 → not saved, runs again", "red");
        await wait(1100); alive();
        await move(t, X.w, 460); alive(); t.textContent = "turn · v10"; busy("w", true); note("w", "rerun: reads A1 · A2 · A3", "violet"); await wait(900); alive(); busy("w", false);
        await move(t, X.db, 460); alive(); flash("db"); ver("chat v11"); note("db", "✓ committed", "green"); gone(t);
        log([{ t: "chat A: A1 · A2 · A3 → one reply to all three", r: true }]);
        await reply(alive, "one reply · A1–A3");
      },
      atomic: async (alive) => {
        // one turn: the chat and stock rows are locked, then its state, order and reply commit together
        ver("chat v7", false);
        const a = pkt("turn · 2 boxes", "var(--blue)", X.q);
        await move(a, X.w, 520); alive();
        busy("w", true); note("w", "LLM turn: an order", "violet"); await wait(900); alive(); busy("w", false);
        await move(a, X.db, 460); alive(); flash("db", "warn"); note("db", "🔒 row lock: chat + stock", "amber"); await wait(1000); alive();
        log([{ t: "state ✓" }, { t: "order ✓" }, { t: "reply ✓" }]);
        flash("db"); ver("chat v8"); note("db", "✓ state + order + reply: one commit", "green"); gone(a);
        await wait(400); alive();
        log([{ t: "state ✓", r: true }, { t: "order ✓", r: true }, { t: "reply ✓", r: true }]);
        await reply(alive);
      },
      fail: async (alive) => {
        const p = pkt("poison msg", "var(--red)", X.q);
        const waits = ["retry in 30 s", "retry in 1 min", "retry in 3 min", "retry in 10 min"];
        for (let k = 1; k <= 5; k++) {
          await move(p, X.w, 380); alive();
          flash("w", "bad"); note("w", `attempt ${k}/5 ✕ error`, "red"); await wait(420); alive();
          await move(p, X.q, 360); alive();
          if (k < 5) { note("q", waits[k - 1], "amber"); await wait(320 + k * 120); alive(); }
        }
        node("dlq").classList.add("lit");
        await move(p, 248, 600, "top"); alive(); flash("dlq", "bad"); note("dlq", "dead-lettered · alert raised", "red", 0, X.q + 240);
        await wait(1200); gone(p);
      },
      pay: async (alive) => {
        relabel({ meta: ["💳", "Xendit", "payment webhook"], ing: ["🧾", "payment-ingester", "verify token · publish"], q: ["📬", "Pub/Sub", "payment-queue"], w: ["🧮", "processing-service", "only a pending order changes"], db: ["🐘", "Cloud SQL", "order status"], cust: ["📱", "Customer", "gets the receipt"] });
        ver("order: pending", false);
        const p = pkt("PAID · evt_1");
        await arrive(alive, p, { label: "✓ callback token" }); await wait(300); alive();
        await turn(alive, p, "pending → paid · amount ✓", 700); ver("order: paid"); note("db", "✓ marked paid", "green"); gone(p);
        await reply(alive, "receipt"); await wait(500); alive();
        const d = pkt("PAID · evt_1", "var(--amber)");
        note("meta", "Xendit retries: same event", "amber");
        await arrive(alive, d, { label: "✓ callback token" }); await wait(200); alive();
        await move(d, X.w, 540); alive(); flash("w", "warn"); note("w", "already paid: a repeat is a no-op", "amber"); await wait(900); alive(); gone(d);
        await wait(500); alive();
        const e = pkt("EXPIRED · late", "var(--red)");
        await arrive(alive, e, { label: "✓ callback token" }); await wait(200); alive();
        await turn(alive, e, "expiry for a paid order?", 700); flash("db", "warn"); note("db", "already paid → the expiry is ignored", "amber"); gone(e);
        await wait(600); alive(); ver("order: paid");
      },
    };
    const STEPS = { "pipe-in": ["send", "dup", "burst"], "pipe-out": ["atomic", "fail", "pay"] };
    return {
      enter(s) { pipe = $("[data-pipe]", s); if (!pipe.children.length) pipe.innerHTML = PIPE_HTML; id = s.id; reset(); },
      step(s, k) {
        clearTimeout(loopT); r.stop(); reset();
        const name = STEPS[id][k];
        const loop = () => r.go(async (alive) => { await wait(500); alive(); await SCEN[name](alive); await wait(1800); alive(); reset(); loopT = setTimeout(loop, 400); });
        loop();
      },
      leave() { r.stop(); clearTimeout(loopT); if (pipe) reset(); },
      thumb(c) { $("[data-pipe]", c).innerHTML = PIPE_HTML; },
    };
  }

  /* ================================================================ LLM engine: the router types out its JSON */
  const llm = (() => {
    const r = runner();
    const MSG = "can I get 2 Astrox 99 Pro, and where's my last order?";
    const PLAIN = '{ "intents": ["order", "order_status"] }';
    const JSON_HTML = '{ <span class="k">"intents"</span>: [<span class="s">"order"</span>, <span class="s">"order_status"</span>] }';
    const done = (s) => { $("#eng-json", s).innerHTML = JSON_HTML; $$(".intents span", s).forEach((x) => x.classList.toggle("on", ["order", "order_status"].includes(x.textContent))); };
    return {
      enter(s) { r.stop(); $("#eng-text", s).textContent = ""; $("#eng-json", s).innerHTML = ""; $$(".intents span", s).forEach((x) => x.classList.remove("on")); },
      step(s, k) {
        const txt = $("#eng-text", s), js = $("#eng-json", s), chips = $$(".intents span", s);
        r.go(async (alive) => {
          if (k === 0) {
            js.innerHTML = ""; chips.forEach((x) => x.classList.remove("on"));
            for (let i = 1; i <= MSG.length; i++) { txt.innerHTML = MSG.slice(0, i) + '<span class="caret"></span>'; await wait(32); alive(); }
            txt.textContent = MSG;
            return;
          }
          txt.textContent = MSG;
          if (k === 1) {
            js.innerHTML = ""; chips.forEach((x) => x.classList.remove("on"));
            await wait(500); alive();
            for (let i = 1; i <= PLAIN.length; i++) { js.textContent = PLAIN.slice(0, i); await wait(28); alive(); }
          }
          done(s);
        });
      },
      leave() { r.stop(); },
      thumb(c) { c.querySelector(".eng-msg span:last-child").textContent = MSG; c.querySelector(".json").innerHTML = JSON_HTML; },
    };
  })();

  /* ================================================================ scaling: CPU over 60% adds instances, up to 3; Pub/Sub holds the rest */
  const scaling = (() => {
    // An illustration, not a measurement: each instance runs 10 turns at once; a turn is drawn as ~5 s, so an instance
    // answers ~2 msg/s. CPU is the share of busy slots; above 60% Cloud Run adds an instance, up to the cap of 3.
    let raf = 0;
    const TURN = 5, SLOTS = 10, CAP = 3;
    function sim(s, k) {
      const cv = $("#sc-chart", s), g = cv.getContext("2d"), insts = $("#sc-insts", s);
      const st = { t: 0, backlog: 0, inFlight: [], n: 1, hist: [], hot: 0, cold: 0, lastAdd: -9, note: "" };
      const rate = (t) => { const c = t % 26; return c < 4 ? 1 : c < 13 ? 9 : 1; };
      $("#sc-back-g", s).classList.toggle("focus", k >= 1);
      const paintInst = (cpuOf) => {
        while (insts.children.length < st.n) { const d = el("div", "inst", `<b>container <small>#${insts.children.length + 1}</small></b><div class="slots">${"<i></i>".repeat(SLOTS)}</div><div class="icpu"><i></i></div>`); insts.append(d); }
        while (insts.children.length > st.n) insts.lastChild.remove();
        [...insts.children].forEach((d, i) => { const busyN = cpuOf(i); $$(".slots i", d).forEach((c, j) => c.classList.toggle("on", j < busyN)); $(".icpu i", d).style.width = busyN * 10 + "%"; });
      };
      let last = performance.now(), acc = 0;
      const frame = (now) => {
        const dt = Math.min(0.05, (now - last) / 1000) * 1.6; last = now; // 1.6×: the burst plays a little faster than real time
        st.t += dt;
        const r = rate(st.t);
        acc += r * dt;
        while (acc >= 1) { acc -= 1; st.backlog++; }
        st.inFlight = st.inFlight.filter((f) => f.end > st.t);
        for (let i = 0; i < st.n; i++) {
          while (st.backlog > 0 && st.inFlight.filter((f) => f.i === i).length < SLOTS) { st.backlog--; st.inFlight.push({ i, end: st.t + TURN * (0.8 + Math.random() * 0.4) }); }
        }
        const busyOf = (i) => st.inFlight.filter((f) => f.i === i).length;
        const cpu = st.inFlight.length / (st.n * SLOTS);
        // Cloud Run's rule, simplified: sustained CPU over 60% adds an instance (up to the cap); low CPU removes one
        st.hot = cpu > 0.6 ? st.hot + dt : 0; st.cold = cpu < 0.3 ? st.cold + dt : 0;
        if (st.hot > 1.2 && st.n < CAP && st.t - st.lastAdd > 1.5) { st.n++; st.lastAdd = st.t; st.hot = 0; }
        if (st.cold > 4 && st.n > 1 && busyOf(st.n - 1) === 0) { st.n--; st.lastAdd = st.t; st.cold = 0; }
        if (!st.hist.length || st.t - st.hist.at(-1).t > 0.12) { st.hist.push({ t: st.t, r, b: st.backlog, c: cpu * 100 }); if (st.hist.length > 180) st.hist.shift(); }
        // draw
        const W = cv.width, H = cv.height;
        g.clearRect(0, 0, W, H);
        g.strokeStyle = "rgba(255,255,255,.07)"; g.lineWidth = 1;
        for (let q = 1; q < 4; q++) { g.beginPath(); g.moveTo(0, (H * q) / 4); g.lineTo(W, (H * q) / 4); g.stroke(); }
        const y = (v, max) => H - 8 - (Math.min(v, max) / max) * (H - 24);
        g.setLineDash([10, 8]); g.strokeStyle = "rgba(37,211,102,.55)"; g.lineWidth = 2; g.beginPath(); g.moveTo(0, y(60, 110)); g.lineTo(W, y(60, 110)); g.stroke(); g.setLineDash([]);
        const xs = (i) => (i / 179) * W;
        const draw = (key, max, color, fill) => {
          g.beginPath();
          st.hist.forEach((h, i) => (i ? g.lineTo(xs(i), y(h[key], max)) : g.moveTo(xs(i), y(h[key], max))));
          if (fill) { g.lineTo(xs(st.hist.length - 1), H); g.lineTo(0, H); g.closePath(); const gr = g.createLinearGradient(0, 0, 0, H); gr.addColorStop(0, color + (k >= 1 ? "cc" : "88")); gr.addColorStop(1, color + "05"); g.fillStyle = gr; g.fill(); }
          else { g.strokeStyle = color; g.lineWidth = 3; g.shadowColor = color; g.shadowBlur = 10; g.stroke(); g.shadowBlur = 0; }
        };
        draw("b", 60, "#a66bff", true);
        draw("r", 12, "#ff9f1a", false);
        draw("c", 110, "#25d366", false);
        $("#sc-rate", s).textContent = `${r} msg/s`;
        $("#sc-src", s).textContent = k >= 1 ? (r > 1 ? "WhatsApp chats + Xendit webhooks" : "WhatsApp + Xendit") : "WhatsApp chats";
        $("#sc-cpu", s).textContent = `${Math.round(cpu * 100)}%`;
        $("#sc-cpu-bar", s).style.width = Math.round(cpu * 100) + "%";
        $("#sc-cpu-g", s).classList.toggle("over", cpu > 0.6);
        $("#sc-back", s).textContent = st.backlog;
        $("#sc-n", s).textContent = `${st.n} / ${CAP}`;
        const nt = r > 1 ? (st.n < CAP ? (cpu > 0.6 ? "CPU over 60%: Cloud Run adds a container" : "Burst: traffic climbs") : k >= 1 ? "At the cap: Pub/Sub holds the backlog, nothing is lost" : "Burst: scaled out to the cap of 3")
          : st.backlog > 0 ? "Burst over: the queue drains" : st.n > 1 ? "Quiet again: containers scale back in" : "Steady traffic: one container";
        if (nt !== st.note) { st.note = nt; $("#sc-note", s).textContent = nt; }
        paintInst(busyOf);
        raf = requestAnimationFrame(frame);
      };
      insts.innerHTML = "";
      raf = requestAnimationFrame(frame);
    }
    return {
      step(s, k) { cancelAnimationFrame(raf); sim(s, k); },
      leave() { cancelAnimationFrame(raf); },
    };
  })();

  /* ================================================================ security: requests and attacks against the VPC, the LB and Cloud Armor */
  const security = (() => {
    const r = runner(); let loopT = 0;
    const ATTACKS = {
      0: [{ em: "✉️", ok: true, stop: 400, top: 290, text: "webhook → load balancer → ingester ✓", lx: 360, ly: 470 },
        { em: "🕵️", stop: 505, top: 470, text: "direct to Cloud SQL → no authorised network: refused", lx: 300, ly: 540 }],
      3: [{ em: "💉", stop: 150, top: 160, text: "SQL injection → blocked", lx: 230, ly: 30 },
        { em: "📜", stop: 150, top: 300, text: "cross-site scripting → blocked", lx: 230, ly: 30 },
        { em: "🌊", stop: 150, top: 120, n: 6, text: "DDoS flood → absorbed", lx: 230, ly: 30 },
        { em: "✉️", ok: true, stop: 400, top: 290, text: "real customer ✓ through", lx: 360, ly: 470 }],
    };
    async function fire(alive, s, a) {
      const box = $("#attacks", s), n = a.n || 1, dur = a.ok ? 1300 : 750;
      for (let i = 0; i < n; i++) {
        const shot = el("div", "shot" + (a.ok ? " ok" : ""), a.em);
        shot.style.left = "-60px"; shot.style.top = a.top + ((i * 61) % 300) + "px";
        box.append(shot);
        shot.animate([{ left: "-60px" }, { left: a.stop + "px" }], { duration: dur, delay: i * 110, easing: "ease-in", fill: "forwards" }).finished.then(() => {
          const wall = a.ok ? null : a.stop < 300 ? $(".armor", s) : $(".vpc", s);
          if (wall) { wall.classList.remove("hit"); void wall.offsetWidth; wall.classList.add("hit"); }
          shot.animate([{ opacity: 1, transform: "scale(1)" }, { opacity: 0, transform: a.ok ? "scale(1.6)" : "scale(2) rotate(40deg)" }], { duration: 420, fill: "forwards" }).finished.then(() => shot.remove());
        }).catch(() => shot.remove());
      }
      await wait(dur + n * 110); alive();
      const lab = el("div", "atk-label" + (a.ok ? " ok" : ""), a.text);
      lab.style.left = a.lx + "px"; lab.style.top = a.ly + "px";
      box.append(lab); setTimeout(() => lab.remove(), 2000);
    }
    return {
      step(s, k) {
        clearTimeout(loopT); r.stop(); $("#attacks", s).innerHTML = "";
        const list = ATTACKS[k]; if (!list) return;
        const loop = () => r.go(async (alive) => { await wait(600); alive(); for (const a of list) { await fire(alive, s, a); await wait(600); alive(); } await wait(1200); alive(); loopT = setTimeout(loop, 200); });
        loop();
      },
      leave(s) { clearTimeout(loopT); r.stop(); $("#attacks", s).innerHTML = ""; },
    };
  })();

  /* ================================================================ the demo: the agenda before, every step ticked off after (one click, on return from the app) */
  const demo = {
    step(s, k) { $(".demo", s).classList.toggle("complete", k >= 1); if (k >= 1) window.DECK?.ctx.pulse(); },
    thumb(c) { $(".demo", c).classList.remove("complete"); },
  };

  /* ================================================================ conclusion: a fireworks finale, with the light thrown on the scene */
  const fireworks = (() => {
    const W = 1600, H = 900, GRAV = 0.075;
    const COLORS = ["255,79,154", "59,139,255", "255,170,40", "37,211,102", "166,107,255", "246,215,90", "255,255,255", "34,211,238"];
    const GOLD = "255,196,90";
    const rnd = (a, b) => a + Math.random() * (b - a), pick = (a) => a[(Math.random() * a.length) | 0];
    let cv, g, flash, raf = 0, on = false, parts = [], rockets = [], clock = 0, nextShow = 0, nextText = 0, textIdx = 0, last = 0;
    // glowing dot sprites, one per colour: a soft halo with a hot core (drawn with "lighter", they add up into light)
    const sprites = {};
    const sprite = (c) => {
      if (sprites[c]) return sprites[c];
      const s = document.createElement("canvas"); s.width = s.height = 32;
      const x = s.getContext("2d"), gr = x.createRadialGradient(16, 16, 0, 16, 16, 16);
      gr.addColorStop(0, "rgba(255,255,255,1)"); gr.addColorStop(0.18, `rgba(${c},1)`); gr.addColorStop(0.45, `rgba(${c},.35)`); gr.addColorStop(1, `rgba(${c},0)`);
      x.fillStyle = gr; x.fillRect(0, 0, 32, 32);
      return (sprites[c] = s);
    };
    // words written in fireworks: points sampled from the text
    const textCache = {};
    const textPoints = (str) => {
      if (textCache[str]) return textCache[str];
      const c = document.createElement("canvas"); c.width = 1000; c.height = 190;
      const x = c.getContext("2d"); x.fillStyle = "#fff"; x.font = "900 150px Inter, -apple-system, Arial, sans-serif"; x.textAlign = "center"; x.textBaseline = "middle"; x.fillText(str, 500, 98);
      const d = x.getImageData(0, 0, 1000, 190).data, pts = [];
      for (let y = 0; y < 190; y += 7) for (let xx = 0; xx < 1000; xx += 7) if (d[(y * 1000 + xx) * 4 + 3] > 140) pts.push([xx - 500, y - 95]);
      return (textCache[str] = pts);
    };
    // every pop throws its colour on the scene: a bright bloom where it bursts, and a quick tint over everything
    let flashIdx = 0;
    const light = (x, y, c, k = 1) => {
      const fl = flash[flashIdx++ % flash.length];
      fl.style.setProperty("--fx", (x / W) * 100 + "%"); fl.style.setProperty("--fy", (y / H) * 100 + "%");
      fl.style.setProperty("--fc", `rgba(${c},${Math.min(0.85, 0.55 * k)})`);
      fl.style.setProperty("--fa", `rgba(${c},${Math.min(0.2, 0.1 * k)})`);
      fl.classList.remove("go"); void fl.offsetWidth; fl.classList.add("go");
      if (k > 1.2) window.DECK?.ctx.pulse();
    };
    const spark = (o) => parts.push({ drag: 0.985, grav: GRAV, size: 1, life: 0, tw: 0, ...o });
    function launch(type = pick(["peony", "peony", "ring", "willow", "crackle", "double", "palm"]), x = rnd(220, 1380), top = rnd(110, 360)) {
      rockets.push({ x, y: H + 10, vx: rnd(-0.8, 0.8), vy: -Math.sqrt(2 * 0.11 * (H - top)), type, c: pick(COLORS) });
    }
    function burst(r) {
      const { x, y, c, type } = r;
      if (type === "text") {
        const pts = textPoints(r.text), col = r.c;
        pts.forEach(([px, py]) => spark({ x, y, tx: x + px * 0.92, ty: y + py * 0.92, mode: "form", c: Math.random() < 0.2 ? "255,255,255" : col, size: 0.9, max: 230, hold: 120 }));
        for (let i = 0; i < 80; i++) { const a = rnd(0, 6.28), v = rnd(3, 9); spark({ x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, c: GOLD, max: rnd(50, 80), size: 0.8 }); }
        light(x, y, col, 1.8);
        return;
      }
      const n = type === "ring" ? 80 : type === "willow" ? 130 : type === "palm" ? 9 : 150;
      for (let i = 0; i < n; i++) {
        let a = rnd(0, 6.28), v = rnd(1.5, 6.5);
        if (type === "ring") { a = (i / n) * 6.28; v = 5.6 + rnd(-0.2, 0.2); }
        if (type === "palm") { a = (i / n) * 6.28 + rnd(-0.1, 0.1); v = 7; }
        const base = { x, y, vx: Math.cos(a) * v, vy: Math.sin(a) * v, c, max: rnd(65, 100), size: 1.1, tw: Math.random() < 0.3 ? 1 : 0 };
        if (type === "willow") Object.assign(base, { c: GOLD, drag: 0.972, grav: 0.035, max: rnd(150, 200), trail: 1, size: 0.9 });
        if (type === "palm") Object.assign(base, { c: GOLD, drag: 0.978, grav: 0.05, max: 120, trail: 1, size: 1.6, palm: 1 });
        if (type === "crackle") base.crackle = 1;
        spark(base);
      }
      if (type === "double") { const c2 = pick(COLORS); for (let i = 0; i < 70; i++) { const a = (i / 70) * 6.28; spark({ x, y, vx: Math.cos(a) * 8, vy: Math.sin(a) * 8, c: c2, max: 85, size: 1.2 }); } }
      for (let i = 0; i < 14; i++) spark({ x, y, vx: rnd(-1.2, 1.2), vy: rnd(-1.2, 1.2), c: "255,255,255", max: 14, size: 2.6, grav: 0, drag: 0.9 });
      light(x, y, type === "willow" || type === "palm" ? GOLD : c, type === "double" ? 1.4 : 1);
    }
    function frame(t) {
      const f = Math.min(3, (t - last) / 16.7); last = t; clock += f;
      // the show: a salvo now and then, and a word in the sky every so often
      if (on) {
        if (clock > nextShow) { const salvo = Math.random() < 0.25 ? 3 : 1; for (let i = 0; i < salvo; i++) setTimeout(() => on && launch(), i * 180); nextShow = clock + rnd(28, 55); }
        if (clock > nextText) { rockets.push({ x: 800, y: H + 10, vx: 0, vy: -Math.sqrt(2 * 0.11 * (H - 140)), type: "text", text: ["THANK YOU", "ANSERA"][textIdx++ % 2], c: pick(["255,79,154", "37,211,102", "166,107,255", "34,211,238"]) }); nextText = clock + 900; }
      }
      // fade what was drawn, so everything leaves a trail but the canvas stays see-through
      g.globalCompositeOperation = "destination-out"; g.fillStyle = "rgba(0,0,0,0.2)"; g.fillRect(0, 0, W, H);
      g.globalCompositeOperation = "lighter";
      rockets = rockets.filter((r) => {
        r.x += r.vx * f; r.y += r.vy * f; r.vy += 0.11 * f;
        spark({ x: r.x + rnd(-2, 2), y: r.y + 6, vx: rnd(-0.4, 0.4), vy: rnd(0.5, 1.5), c: GOLD, max: rnd(18, 30), size: 0.8, grav: 0.02 });
        g.drawImage(sprite("255,240,200"), r.x - 9, r.y - 9, 18, 18);
        if (r.vy >= -0.6) { burst(r); return false; }
        return true;
      });
      const out = [];
      for (const p of parts) {
        p.life += f;
        if (p.mode === "form") {
          // fly into place, hold the word (twinkling), then let go
          if (p.life < 45) { const k = 1 - Math.pow(1 - p.life / 45, 3); p.x += (p.tx - p.x) * 0.16 * f; p.y += (p.ty - p.y) * 0.16 * f; void k; }
          else if (p.life < 45 + p.hold) { p.x = p.tx + rnd(-0.6, 0.6); p.y = p.ty + rnd(-0.6, 0.6); }
          else { p.mode = null; p.vx = rnd(-0.6, 0.6); p.vy = rnd(-0.5, 0.8); p.grav = 0.04; p.drag = 0.99; }
        } else {
          p.vx *= Math.pow(p.drag, f); p.vy *= Math.pow(p.drag, f); p.vy += p.grav * f; p.x += p.vx * f; p.y += p.vy * f;
        }
        const rem = 1 - p.life / p.max;
        if (rem <= 0) {
          if (p.crackle) for (let i = 0; i < 3; i++) spark({ x: p.x, y: p.y, vx: rnd(-1.5, 1.5), vy: rnd(-1.5, 1.5), c: "255,250,220", max: rnd(8, 16), size: 0.7, grav: 0.02 });
          continue;
        }
        if (p.trail && Math.random() < 0.35) spark({ x: p.x, y: p.y, vx: 0, vy: 0.2, c: p.c, max: 26, size: p.size * 0.6, grav: 0.01 });
        let a = Math.min(1, rem * 1.6);
        if (p.tw) a *= 0.4 + 0.6 * Math.abs(Math.sin(p.life * 0.5 + p.x));
        const sz = 14 * p.size * (0.6 + 0.4 * rem);
        g.globalAlpha = a; g.drawImage(sprite(p.c), p.x - sz / 2, p.y - sz / 2, sz, sz);
        out.push(p);
      }
      g.globalAlpha = 1;
      parts = out.length > 4500 ? out.slice(-4500) : out;
      if (on || parts.length || rockets.length) raf = requestAnimationFrame(frame); else raf = 0;
    }
    return {
      start(s) {
        cv = $(".fw-canvas", s); g = cv.getContext("2d"); flash = $$(".fw-flashes i", s);
        on = true; clock = 0; nextShow = 70; nextText = 95; textIdx = 0;
        // the opening: a fan of rockets, then the word
        [[380, 260, "peony"], [800, 200, "double"], [1220, 250, "ring"], [580, 330, "crackle"], [1020, 320, "willow"]].forEach(([x, top, type], i) => setTimeout(() => on && launch(type, x, top), i * 160));
        if (!raf) { last = performance.now(); raf = requestAnimationFrame(frame); }
      },
      stop(hard) {
        on = false;
        if (hard) { cancelAnimationFrame(raf); raf = 0; parts = []; rockets = []; g?.clearRect(0, 0, W, H); }
      },
    };
  })();

  /* ================================================================ conclusion: confetti, then the finale */
  const end = {
    enter(s) {
      const box = $(".confetti", s);
      if (!box.children.length) {
        const colors = ["#ff4f9a", "#3b8bff", "#ff9f1a", "#22d07a", "#a66bff", "#f6c34a"];
        for (let k = 0; k < 90; k++) {
          const i = el("i");
          i.style.left = Math.random() * 1600 + "px"; i.style.background = colors[k % colors.length];
          i.style.animationDuration = 4 + Math.random() * 5 + "s"; i.style.animationDelay = -Math.random() * 8 + "s";
          i.style.transform = `rotate(${Math.random() * 360}deg)`;
          box.append(i);
        }
      }
    },
    step(s, k) {
      s.classList.toggle("finale", k >= 1);
      $(".deskbot", s).classList.toggle("party", k >= 1);
      $(".confetti", s).classList.toggle("burst", k >= 1);
      if (k >= 1) { window.DECK?.ctx.pulse(); fireworks.start(s); } else fireworks.stop(true);
    },
    leave(s) { s.classList.remove("finale"); $(".deskbot", s).classList.remove("party"); fireworks.stop(true); },
  };

  window.WIDGETS = {
    problem, solution, competitors,
    arch, "flow-msg": arch, "flow-pay": arch,
    "pipe-in": pipeline(), "pipe-out": pipeline(),
    llm, scaling, security, demo, end,
  };
})();
