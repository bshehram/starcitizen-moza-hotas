/* The dashboard page (stage 3): the status strip, the alerts, the view the service chose (or the
   one picked by hand), the event feed and the desk controls, fed by one event stream from the
   local service. Look: direction B, "Avionics". Everything the views show comes from the
   message's `board` (dashboard/STATE.md); the strip's joystick check and the feed come from its
   `state`, as in stage 2.

   - One event stream (/api/stream). The browser reconnects by itself after a network error,
     using the server's `retry:` value; after an HTTP error (the page cap, a restart) it gives up,
     so this script opens a new one a few seconds later. A stream that stays open but brings
     neither a state nor the service's keepalive event for over two keepalive intervals counts as
     lost too (a hung service): the banner goes up and the page connects again.
   - One one-second timer for every clock, countdown and count-up. Each tick computes the time
     from the system clock (and, in a replay, from the replay clock's anchor), so a page that was
     paused is right again at once. It writes only the texts that changed.
   - Views are built from blocks. A block is rebuilt only when its own data changed (compared as
     JSON); the rest of the view is left alone. Text from the game's log or the plan is only ever
     set as text (text nodes and textContent), never parsed as markup.
   - A view that does not fit its region drops its least important blocks (`data-cut`, the
     highest number first) until it does, measured after each change and each resize, never on
     the tick.
   - Changes (a view picked by hand, back to Live, a quick timer added or removed) go through
     `request()`, the same call as `window.scdash.post()`. Nothing on the page changes until the
     service's next message shows the change; a change that was refused is said so in the toast. */
"use strict";

(function () {
  const TOKEN = document.querySelector('meta[name="scdash-token"]').getAttribute("content");

  // ------------------------------------------------------------------ choices, kept in one place
  const SHOW_MINOR = false;            // minor lines (zones, menus, storage) stay out of the page feed
  const FULL_ALERTS = 1;               // alerts drawn in full; the rest one line each
  const TOAST_SECONDS = 7;             // how long a refused change is said
  const QUICK_MINUTES = [5, 10, 15, 30, 60, 120];   // the quick timer buttons
  const QUICK_LABEL = "Timer";         // a quick timer's name when none is typed
  const MAX_OTHER_TIMERS = 3;          // timers listed under the Now view's countdown
  const MAX_ORES = 3;                  // ores drawn on the Mining view (the rest are named)
  const CTL_KEEP = 6;                  // controls kept in a crowded view (the table's order); the rest go first
  const HIDE_ALERT_THE_VIEW_SHOWS = true;   // the Preflight view's failure is not repeated as an alert above it
  const ALERTS_SHOWN = 3;              // alerts drawn at most (the most severe first); the rest are a "+N more" line
  const REQUEST_SECONDS = 8;           // a change with no answer by then is given up and said so
  const CHANGE_HOLD_MS = 2500;         // the controls wait at most this long for the message that shows a change
  const MOVED_MS = 450;                // a click this soon after the list under it was redrawn is not taken
  const QUIET_INTERVALS = 2;           // no state and no keepalive for this many keepalive intervals...
  const QUIET_EXTRA_MS = 3000;         // ...plus this: the service counts as gone (a hung one included)
  const FAR_TIMER_HOURS = 3;           // Now: a countdown further out than this is drawn small, the next step leads
  // Every view the service can send, its label and icon. The picker lists all but "reference",
  // which has a switcher cell of its own. A renderer for each is in RENDERERS below.
  const VIEW_LIST = [
    ["now", "Now", "dot"], ["travel", "Travel", "jump"], ["mining", "Mining", "pick"],
    ["salvage", "Salvage", "salv"], ["combat", "Combat", "target"], ["cargo", "Cargo", "box"],
    ["mission", "Mission", "doc"], ["refinery", "Refinery", "flask"], ["selling", "Selling", "sell"],
    ["preflight", "Preflight", "stick"], ["idle", "Idle", "moon"], ["reference", "Rig reference", "stick"],
  ];
  const VIEW_LABEL = Object.fromEntries(VIEW_LIST.map((v) => [v[0], v[1]]));
  const VIEW_ICON = Object.fromEntries(VIEW_LIST.map((v) => [v[0], v[2]]));
  // Views drawn as an activity (a head, a hero, the controls): their feed is 3 lines in landscape.
  const SHORT_FEED = new Set(["travel", "mining", "salvage", "combat", "cargo", "mission", "refinery",
                              "selling", "preflight", "idle"]);

  const $ = (id) => document.getElementById(id);
  const ui = {
    app: $("app"), body: document.body,
    offline: $("offline"), offlineDetail: $("offline-detail"),
    clock: $("s-clock"), date: $("s-date"), replay: $("s-replay"),
    stateBox: $("b-state"), state: $("s-state"),
    sticksBox: $("b-sticks"), sticks: $("s-sticks"), sticksNote: $("s-sticks-note"),
    sessionK: $("s-session-k"), session: $("s-session"),
    loc: $("s-loc"), shipK: $("s-ship-k"), ship: $("s-ship"),
    swLive: $("sw-live"), swLiveT: $("sw-live-t"), swMore: $("sw-more"), swRig: $("sw-rig"),
    panel: $("panel"), panelAuto: $("panel-auto"), picks: $("picks"), panelLive: $("panel-live"),
    qlist: $("qlist"), qnone: $("qnone"), qlabel: $("q-label"), qmins: $("qmins"),
    toast: $("toast"),
    pickbar: $("pickbar"), pickbarView: $("pickbar-view"), pickbarWhy: $("pickbar-why"), pickbarLive: $("pickbar-live"),
    alerts: $("alerts"),
    view: $("view"), host: $("view-host"),
    planNote: $("plan-note"), planNoteT: $("plan-note-t"),
    feed: $("feed"), feedList: $("feed-list"), feedEmpty: $("feed-empty"),
  };

  let payload = null;                 // the last message the service sent
  let anchor = { rate: 1, real: 0, virtual: 0 };   // live: the system clock itself
  let source = null;                  // the EventSource
  let lastMessageAt = null;           // Date.now() of the last message
  let lostAt = Date.now();            // when the stream was lost (now: not connected yet)
  let reconnectTimer = null;
  let heardAt = null;                 // Date.now() of the last state or keepalive (or of connecting)
  let quietMs = 15000 * QUIET_INTERVALS + QUIET_EXTRA_MS;   // until the first keepalive gives the interval
  let lastTickAt = Date.now();
  // Which instance served this page (pid/start, from the HTML): compared from the first message on.
  const servedBy = document.querySelector('meta[name="scdash-instance"]').getAttribute("content");
  let serviceId = /^\d+\//.test(servedBy) ? servedBy : null;
  const feedItems = new Map();        // line id -> {li, rev, ...}
  const lives = { strip: [], alerts: [], panel: [] };   // tick functions outside the view's blocks
  let toastUntil = 0;
  let busy = false;                   // one change at a time
  let qlistAt = 0;                    // when the quick timers' list was last redrawn

  // Feed line kinds -> icon and tone (anything else: a dot).
  const ICONS = {
    quantum_target: "jump", quantum_arrived: "jump", quantum_obstructed: "warn",
    inventory_location: "pin", location_inventory: "pin", session_start: "dot", spawned: "flag",
    hangar_queue: "clock", hangar_ready: "check", ship_retrieved: "ship", seat_left: "ship",
    channel_joined: "ship", vehicle_destroyed: "ship", fatal_collision: "stop",
    contract_accepted: "doc", contract_complete: "check", objective_new: "doc", objective_complete: "check",
    mission_ended: "doc", refinery_done: "ok", refinery_sell: "flask", blueprint: "ok",
    shop_buy: "coin", shop_sell: "coin", commodity_buy: "coin", commodity_sell: "coin", rental: "coin",
    joystick: "stick", profile_loaded: "stick", incapacitated: "stop", emergency: "stop", injury: "warn",
  };
  const OK_KINDS = new Set(["refinery_done", "blueprint", "contract_complete", "hangar_ready"]);

  // ---------------------------------------------------------------- helpers

  function setText(node, text) {
    if (node.textContent !== text) node.textContent = text;
  }
  function setClass(node, cls) {
    if (node.className !== cls) node.className = cls;
  }
  function show(node, on) {
    if (node.hidden === on) node.hidden = !on;
  }
  function nowMs() {
    return anchor.virtual + (Date.now() - anchor.real) * anchor.rate;
  }
  function parseIso(text) {
    return text ? Date.parse(text) : null;
  }
  function num(x) {
    return typeof x === "number" && isFinite(x);
  }
  const TIME = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" });
  const DATE = new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric" });
  const two = (n) => String(n).padStart(2, "0");
  function hms(ms) {                   // 1:02:03, never negative
    const s = Math.max(0, Math.floor(ms / 1000));
    return Math.floor(s / 3600) + ":" + two(Math.floor((s % 3600) / 60)) + ":" + two(s % 60);
  }
  function hm(ms) {                    // 1:02
    const s = Math.max(0, Math.floor(ms / 1000));
    return Math.floor(s / 3600) + ":" + two(Math.floor((s % 3600) / 60));
  }
  function minSec(ms) {                // 13 min 05 s
    const s = Math.max(0, Math.floor(ms / 1000));
    return Math.floor(s / 60) + " min " + two(s % 60) + " s";
  }
  function dateWords(iso) {            // "2026-10-19" -> "Oct 19"
    const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || "");
    if (!m) return iso || "";
    return ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][+m[2] - 1] + " " + (+m[3]);
  }

  /* A node: h(tag, classes, ...children). A string child becomes a text node, never markup;
     null, false and "" are skipped; arrays are flattened. */
  function h(tag, cls, ...kids) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    add(n, kids);
    return n;
  }
  function add(n, kids) {
    for (const k of kids) {
      if (k === null || k === undefined || k === false || k === "") continue;
      if (Array.isArray(k)) add(n, k);
      else if (typeof k === "string" || typeof k === "number") n.appendChild(document.createTextNode(String(k)));
      else n.appendChild(k);
    }
    return n;
  }
  /* A text from data, bounded: one line with an ellipsis (`lines` 1) or clamped to `lines`;
     the whole text stays in the title for the mouse. */
  function t(tag, cls, text, lines) {
    const n = h(tag, (cls ? cls + " " : "") + "clamp" + (lines || 1), text === null || text === undefined ? "" : String(text));
    if (text) n.title = String(text);
    return n;
  }
  function icon(name, extra) {
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", "i" + (extra ? " " + extra : ""));
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS(NS, "use");
    use.setAttribute("href", "#i-" + name);
    svg.appendChild(use);
    return svg;
  }
  function cut(node, n) {              // a block the view may drop when it does not fit (higher first)
    node.dataset.cut = String(n);
    return node;
  }
  function meter(fill, cls) {
    const m = h("span", "meter" + (cls ? " " + cls : ""), h("i"));
    m.style.setProperty("--v", String(Math.max(0, Math.min(1, num(fill) ? fill : 0))));
    return m;
  }
  function cap(text, cls) {
    return h("h2", "cap" + (cls ? " " + cls : ""), text);
  }

  // ---------------------------------------------------------------- the clock (one timer)

  /* Nothing a message holds can stop the one-second timer: each part runs guarded, and the next
     tick is set first. */
  function tick() {
    setTimeout(tick, 1000 - (Date.now() % 1000) + 5);
    const now = nowMs();
    guarded("clock", () => renderClock(now));
    for (const list of [lives.strip, lives.alerts, lives.panel]) for (const f of list) guarded("tick", () => f(now));
    for (const blk of host.blocks.values()) for (const f of blk.live) guarded("tick", () => f(now));
    if (toastUntil && Date.now() > toastUntil) hideToast();
    const wall = Date.now();
    const slept = wall - lastTickAt > 5000;   // a frozen or throttled tab: let the stream catch up first
    lastTickAt = wall;
    if (!slept && heardAt !== null && wall - heardAt > quietMs) quiet();
    if (lostAt !== null && wall - lostAt > 2000) showOffline(true);
  }
  /* Neither a state nor a keepalive for over two keepalive intervals, with the stream still open:
     the service is hung, or the connection died without an error. Say so at once and connect
     again; the next state or keepalive takes the banner down. */
  function quiet() {
    if (lostAt === null) lostAt = heardAt;
    heardAt = null;
    if (source) source.close();
    if (reconnectTimer === null) reconnectTimer = setTimeout(connect, 5000);
  }
  /* A part that throws is noted once in the console (per part and message) and the rest go on. */
  const noted = new Set();
  function guarded(part, fn) {
    try {
      return fn();
    } catch (err) {
      const key = part + ": " + String(err && err.message || err);
      if (!noted.has(key) && noted.size < 200) {
        noted.add(key);
        console.warn("dashboard page: " + key, err);
      }
      return undefined;
    }
  }

  function renderClock(now) {
    const d = new Date(now);
    setText(ui.clock, TIME.format(d));
    setText(ui.date, DATE.format(d));
  }

  // ---------------------------------------------------------------- the stream

  function connect() {
    reconnectTimer = null;
    if (source) source.close();
    source = new EventSource("/api/stream");
    heardAt = Date.now();               // the quiet clock starts with the connection
    source.addEventListener("state", (e) => {
      let p;
      try { p = JSON.parse(e.data); } catch (err) { return; }
      lastMessageAt = heardAt = Date.now();
      lostAt = null;
      showOffline(false);
      render(p);
    });
    // The service's keepalive (data: its interval in seconds): proof of life, nothing to draw.
    source.addEventListener("keepalive", (e) => {
      const every = parseFloat(e.data);
      if (num(every) && every >= 0.1 && every <= 600) quietMs = Math.round(every * QUIET_INTERVALS * 1000) + QUIET_EXTRA_MS;
      heardAt = Date.now();
      if (lostAt !== null) { lostAt = null; showOffline(false); }
    });
    source.onerror = () => {
      if (lostAt === null) lostAt = Date.now();
      if (source.readyState === EventSource.CLOSED && reconnectTimer === null) {
        reconnectTimer = setTimeout(connect, 5000);
      }
    };
  }

  function showOffline(on) {
    if (on) {
      setText(ui.offlineDetail, lastMessageAt
        ? "Last update " + TIME.format(new Date(lastMessageAt)) + ". Retrying by itself"
        : "Nothing has arrived yet. Retrying by itself");
    }
    show(ui.offline, on);
    ui.body.classList.toggle("is-offline", on);
  }

  // ---------------------------------------------------------------- rendering

  /* One message: each part drawn guarded, so a part that cannot be drawn leaves the others, the
     tick and the next message working. A clock that is not usable keeps the last good one. */
  function render(p) {
    if (!p || typeof p !== "object") return;
    const svc = p.service && typeof p.service === "object" ? p.service : null;
    // A restarted service has a new token: this page's would be refused. Load the page again.
    if (svc && num(svc.pid)) {
      const id = svc.pid + "/" + svc.started;
      if (serviceId !== null && id !== serviceId) {
        if (source) source.close();
        window.location.reload();
        return;
      }
      serviceId = id;
    }
    payload = p;
    const c = p.clock || {};
    if (num(c.rate) && c.rate >= 0 && c.rate <= 10000 && num(c.real) && num(c.virtual) &&
        Math.abs(c.virtual) < 8e15 && Math.abs(c.real) < 8e15) {
      anchor = { rate: c.rate, real: c.real, virtual: c.virtual };
    }
    const b = p.board && typeof p.board === "object" ? p.board : null;
    const now = nowMs();
    const st = p.state && typeof p.state === "object" ? p.state : {};
    guarded("strip", () => renderStrip(Object.assign({}, p, { state: st, service: svc || {} }), b));
    guarded("switcher", () => renderSwitcher(b));
    guarded("alerts", () => renderAlerts(b));
    guarded("feed", () => renderFeed(Array.isArray(st.feed) ? st.feed : []));   // before the view: it is fitted to what is left
    guarded("plan note", () => renderPlanNote(b));
    guarded("view", () => renderView(b));
    guarded("panel", () => renderPanel(b));
    guarded("clock", () => renderClock(now));
    tick0(now);
    afterRedraw();
  }

  function tick0(now) {                // the live texts at once, not a second later
    for (const list of [lives.strip, lives.alerts, lives.panel]) for (const f of list) guarded("tick", () => f(now));
    for (const blk of host.blocks.values()) for (const f of blk.live) guarded("tick", () => f(now));
  }
  function timeText(ms) {              // "8:39 AM", or a dash for a time that cannot be shown
    return num(ms) && Math.abs(ms) < 8e15 ? TIME.format(new Date(ms)) : "–";
  }

  // ---------------------------------------------------------------- the strip

  function renderStrip(p, b) {
    const st = p.state, svc = p.service;
    const replay = svc.mode === "replay" && svc.replay;
    if (replay) setText(ui.replay, "Replay " + svc.replay.speed + "×" + (svc.replay.done ? ", ended" : ""));
    show(ui.replay, !!replay);

    const s = b && b.strip;
    lives.strip = [];
    if (s) {
      setText(ui.state, s.state);
      const tone = s.tone;
      setClass(ui.state, "state" + (tone === "live" ? " state--live" : tone === "quantum" ? " state--quantum" : tone === "off" ? " state--off" : ""));
      setClass(ui.stateBox, "si si--state" + (tone === "bad" ? " si--bad" : ""));
      const se = s.session || {};
      setText(ui.sessionK, se.label || "Session");
      if (num(se.since_ms)) {
        const since = se.since_ms;
        lives.strip.push((now) => setText(ui.session, hm(now - since)));
      } else {
        setText(ui.session, se.text || "–");
      }
      setText(ui.loc, (s.where && s.where.text) || "–");
      setText(ui.ship, (s.ship && s.ship.text) || "–");
    } else {
      setText(ui.state, "Connected");
      setClass(ui.state, "state");
      setClass(ui.stateBox, "si si--state");
      setText(ui.session, "–");
      setText(ui.loc, "–");
      setText(ui.ship, "–");
    }

    const pf = st.preflight || {};
    const ok = pf.ok;
    const differs = ok === true && pf.order === "differs";
    show(ui.sticksNote, differs);
    const sticksKey = String(ok);
    if (ui.sticks.dataset.key !== sticksKey) {
      ui.sticks.dataset.key = sticksKey;
      ui.sticks.textContent = "";
      if (ok === true) { ui.sticks.append(icon("check"), "Pass"); }
      else if (ok === false) { ui.sticks.append(icon("x"), "Fail"); }
      else { ui.sticks.append("–"); }
      setClass(ui.sticks, "sticks" + (ok === true ? " sticks--ok" : ok === false ? "" : " sticks--none"));
      setClass(ui.sticksBox, "si si--sticks" + (ok === false ? " si--bad" : ""));
    }
  }

  // ---------------------------------------------------------------- the switcher

  function renderSwitcher(b) {
    const v = b ? b.view : null;
    const ref = !!v && v.name === "reference";
    const picked = !!v && v.picked && !ref;
    ui.swLive.setAttribute("aria-pressed", String(!!v && !ref && !picked));
    ui.swRig.setAttribute("aria-pressed", String(ref));
    ui.swLive.title = picked ? "Back to Live: let the dashboard choose the view again" : ref ? "Back to the live views" : "The dashboard chooses the view";
    show(ui.pickbar, picked);
    if (picked) {
      setText(ui.pickbarView, VIEW_LABEL[v.name] || v.name);
      setText(ui.pickbarWhy, v.auto === v.name ? "Live would show the same view" : "Live would show " + (VIEW_LABEL[v.auto] || v.auto));
    }
  }

  // ---------------------------------------------------------------- alerts (board.alerts only)

  function renderAlerts(b) {
    let items = (b && b.alerts) || [];
    if (HIDE_ALERT_THE_VIEW_SHOWS && b && b.view.name === "preflight" && b.model && b.model.verdict === "fail") {
      // The Preflight view is that alert drawn in full: the same words twice would only push it down.
      items = items.filter((a) => a.kind !== "Preflight failed");
    }
    items = Array.isArray(items) ? items.filter((a) => a && typeof a === "object") : [];
    const key = JSON.stringify(items);
    if (ui.alerts.dataset.key === key) return;
    ui.alerts.dataset.key = key;
    ui.alerts.textContent = "";
    lives.alerts = [];
    // The band is capped (the board sends the most severe first): past ALERTS_SHOWN the rest are
    // one "+N more" line, so the view keeps the room its main figures need.
    const rest = items.length > ALERTS_SHOWN ? items.slice(ALERTS_SHOWN - 1) : [];
    if (rest.length) items = items.slice(0, ALERTS_SHOWN - 1);
    const kind = (a) => h("span", "alert__kind", a.kind || "", num(a.t_ms) ? h("span", "alert__at num", timeText(a.t_ms)) : null);
    items.forEach((a, i) => {
      const tone = a.level === "bad" ? "bad" : a.level === "ok" ? "ok" : "warn";
      const ic = tone === "bad" ? "stop" : tone === "ok" ? "ok" : "warn";
      if (i >= FULL_ALERTS) {
        const line = h("div", "alert alert--" + tone + " alert--line",
                       icon(ic, "alert__icon"), kind(a), t("b", "alert__title", a.title));
        line.setAttribute("role", "alert");
        line.dataset.id = a.id;
        ui.alerts.appendChild(line);
        return;
      }
      const text = t("span", "alert__text", a.text, 2);
      const body = h("div", "alert__body", kind(a), t("b", "alert__title", a.title, 2));
      if (num(a.since_ms)) {
        // The hangar queue: the page counts the wait up; the text has the estimate.
        const wait = h("span", "alert__text alert__wait num");
        const since = a.since_ms, rest = a.text;
        body.appendChild(wait);
        lives.alerts.push((now) => setText(wait, "Waiting " + minSec(now - since) + "." + (rest ? " " + rest : "")));
      } else if (a.text) {
        body.appendChild(text);
      }
      const box = h("div", "alert alert--" + tone, icon(ic, "alert__icon"), body, a.do ? t("p", "alert__do", a.do, 3) : null);
      box.setAttribute("role", "alert");
      box.dataset.id = a.id;
      ui.alerts.appendChild(box);
    });
    if (rest.length) {
      const tone = rest.some((a) => a.level === "bad") ? "bad" : rest.every((a) => a.level === "ok") ? "ok" : "warn";
      const kinds = Array.from(new Set(rest.map((a) => a.kind || a.title || ""))).filter(Boolean).join(" · ");
      const more = h("div", "alert alert--" + tone + " alert--line alert--more", icon(tone === "bad" ? "stop" : tone === "ok" ? "ok" : "warn", "alert__icon"),
                     h("span", "alert__kind", "+" + rest.length + " more"), t("b", "alert__title", kinds));
      more.setAttribute("role", "alert");
      ui.alerts.appendChild(more);
    }
    ui.app.classList.toggle("has-alerts", items.length + rest.length > 0);
  }

  // ---------------------------------------------------------------- the view host (blocks)

  const host = { name: null, blocks: new Map(), sig: "" };

  /* A block: key, classes, data (compared as JSON), and a builder `(data, live) -> node`; the
     builder pushes tick functions onto `live`. */
  function B(key, cls, data, build) {
    return { key: key, cls: cls, data: data, build: build };
  }

  function renderView(b) {
    if (!b) {
      return;
    }
    const v = b.view || { name: "now" };
    const name = RENDERERS[v.name] ? v.name : "now";
    const m = b.model && b.model.view === v.name ? b.model : { view: v.name, unavailable: true };
    if (host.name !== name) {
      host.name = name;
      host.blocks.clear();
      ui.host.textContent = "";
      ui.host.className = "v v--" + name;
      ui.app.dataset.view = name;
      ui.view.setAttribute("aria-label", VIEW_LABEL[name] || name);
      ui.feed.classList.toggle("feed--short", SHORT_FEED.has(name));
      rig.shown = false;               // the rig reference opens afresh the next time it is drawn
    }
    try {
      drawBlocks(m.unavailable && name !== "reference" ? frameOnly(name) : RENDERERS[name](m, b));
    } catch (err) {
      // A view that cannot be drawn says so, plainly, and the next message tries it afresh.
      guarded("view " + name, () => { throw err; });
      host.blocks.clear();
      ui.host.textContent = "";
      ui.host.appendChild(h("div", "blk vfail frame", h("p", "vfail__t", "This view could not be drawn"),
                            h("p", "vfail__sub", "The rest of the dashboard goes on. It tries again with the next update.")));
    }
    const wait = document.getElementById("view-wait");
    if (wait) wait.remove();
    ui.app.classList.toggle("is-fail", name === "preflight" && m.verdict === "fail");
    fit();
  }

  function drawBlocks(list) {
    const seen = new Set();
    let prev = null;
    for (const d of list) {
      if (!d) continue;
      seen.add(d.key);
      const json = JSON.stringify(d.data === undefined ? null : d.data) + "|" + d.cls;
      let blk = host.blocks.get(d.key);
      if (!blk || blk.json !== json) {
        const live = [];
        const node = d.build(d.data, live);
        node.classList.add("blk");
        if (d.cls) for (const c of d.cls.split(" ")) if (c) node.classList.add(c);
        node.dataset.key = d.key;
        if (blk) blk.node.replaceWith(node);
        blk = { node: node, json: json, live: live };
        host.blocks.set(d.key, blk);
      }
      const at = prev ? prev.nextSibling : ui.host.firstChild;
      if (at !== blk.node) ui.host.insertBefore(blk.node, at);
      prev = blk.node;
    }
    for (const [k, blk] of host.blocks) {
      if (!seen.has(k)) { blk.node.remove(); host.blocks.delete(k); }
    }
    const stray = ui.host.querySelector(":scope > .vfail");
    if (stray) stray.remove();
  }

  /* Drop the least important blocks until the view fits its region (never on the tick): the
     highest `data-cut` first, later ones before earlier ones; then put back, most important
     first, any dropped block the view has room for after all (dropping it did not help). */
  function fit() {
    fitFigures();
    const cuts = Array.from(ui.host.querySelectorAll("[data-cut]"));
    for (const n of cuts) n.classList.remove("is-cut");
    ui.view.classList.remove("is-over");
    if (host.name !== "reference" && overflows()) {            // the reference scrolls its own rows
      cuts.sort((a, b) => (+b.dataset.cut - +a.dataset.cut) ||
                          (a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? 1 : -1));
      const dropped = [];
      for (const n of cuts) {
        n.classList.add("is-cut");
        dropped.push(n);
        if (!overflows()) break;
      }
      for (let i = dropped.length - 2; i >= 0; i--) {
        dropped[i].classList.remove("is-cut");
        if (overflows()) dropped[i].classList.add("is-cut");
      }
      ui.view.classList.toggle("is-over", overflows());
    }
    // A key explains marks on screen: the controls' "not yet confirmed" shows only while a row
    // that carries the ring is still drawn (the cuts above can drop every one of them).
    for (const k of ui.host.querySelectorAll(".ctl__key")) {
      const pane = k.closest(".ctl");
      show(k, !!(pane && pane.querySelector(".ctl--unv:not(.is-cut)")));
    }
  }
  /* A row of large figures (the Mining view's scan readings) shares one size: the stylesheet's,
     or less when one of them is wider than its column, never under 18 px. */
  function fitFigures() {
    for (const row of ui.host.querySelectorAll(".reads")) {
      const figs = Array.from(row.querySelectorAll(".read__fig"));
      for (const n of figs) n.style.fontSize = "";
      let ratio = 1;
      for (const n of figs) if (n.clientWidth > 0 && n.scrollWidth > n.clientWidth) ratio = Math.min(ratio, n.clientWidth / n.scrollWidth);
      if (ratio < 1) {
        const fs = parseFloat(getComputedStyle(figs[0]).fontSize) || 18;
        for (const n of figs) n.style.fontSize = Math.max(18, Math.floor(fs * ratio)) + "px";
      }
    }
  }
  function overflows() {
    const v = ui.view;
    return v.scrollHeight > v.clientHeight + 1 || v.scrollWidth > v.clientWidth + 1;
  }
  let fitQueued = false;
  function queueFit() {                // a fit at the next frame, once however often it is asked for
    if (fitQueued) return;
    fitQueued = true;
    requestAnimationFrame(() => { fitQueued = false; fit(); });
  }
  if (window.ResizeObserver) new ResizeObserver(queueFit).observe(ui.view);

  // ---------------------------------------------------------------- shared pieces

  /* The head of an activity view: its name, where, and the next timer on the right (one the
     view does not already show: `shown` holds those timers' ids). */
  function headBlock(name, where, b, shown) {
    const tm = nextTimer(b, shown);
    return B("head", "act__head", { name: name, where: where, tm: tm }, (d, live) => {
      const n = h("header", "",
                  h("h1", "act__kind", icon(VIEW_ICON[d.name] || "dot"), VIEW_LABEL[d.name] || d.name),
                  d.where ? t("p", "act__where", d.where) : null);
      if (d.tm) n.appendChild(timerChip(d.tm, live));
      return n;
    });
  }

  /* The first timer to show beside a view's head: the soonest running, else the first ready. */
  function nextTimer(b, shown) {
    const ts = ((b && b.timers) || []).filter((x) => !shown || !shown.has(x.id));
    return ts.find((x) => x.state === "running") || ts.find((x) => x.state === "ready") || null;
  }

  function timerChip(tm, live) {
    const fig = h("b", "chip__fig num");
    const chip = h("p", "chip" + (tm.state === "ready" ? " chip--ok" : ""), icon(tm.kind === "refinery" ? "flask" : "clock"),
                   t("span", "chip__k", tm.label + (tm.where_short ? " · " + tm.where_short : "")), fig);
    if (tm.state === "running" && num(tm.ready_ms)) {
      live.push((now) => setText(fig, hms(tm.ready_ms - now)));
    } else {
      fig.textContent = "Ready";
    }
    return cut(chip, 6);
  }

  /* A timer's figure: a countdown while running, its words after. */
  function timerFig(tm, cls, live) {
    const n = h("b", cls + " num");
    if (tm.state === "running" && num(tm.ready_ms)) live.push((now) => setText(n, hms(tm.ready_ms - now)));
    else n.textContent = tm.state === "done" ? "Done" : "Ready";
    return n;
  }
  function timerMeter(tm, live) {
    if (tm.state !== "running" || !num(tm.started_ms) || !num(tm.ready_ms) || tm.ready_ms <= tm.started_ms) return null;
    const m = meter(0, "meter--live");
    let last = -1;
    live.push((now) => {
      const f = Math.round(Math.max(0, Math.min(1, (now - tm.started_ms) / (tm.ready_ms - tm.started_ms))) * 200) / 200;
      if (f !== last) { last = f; m.style.setProperty("--v", String(f)); }
    });
    return m;
  }

  /* A list of timers, one line each: name and place, then the countdown or the timer's words. */
  function timerRows(list, live) {
    return h("ul", "trows", list.map((tm) => {
      const right = tm.state === "running" ? timerFig(tm, "trow__fig", live) : h("span", "trow__state", tm.state === "done" ? "Done" : "Ready");
      return h("li", "trow trow--" + tm.state,
               icon(tm.state === "running" ? (tm.kind === "refinery" ? "flask" : "clock") : "ok"),
               h("span", "trow__name", t("b", "", tm.label), t("span", "trow__sub", tm.text + (tm.where_short ? " · " + tm.where_short : ""))),
               right);
    }));
  }

  /* The contract, as every view draws it. `kind`: "compact" (only the current objective),
     "normal" or "full" (Mission: the current one larger). `stops` replaces the objectives with
     a checklist of a haul's stops (Cargo). */
  function contractCard(c, kind, stops) {
    const head = h("header", "contract__head",
                   h("p", "contract__giver", h("span", "contract__from", "From"), t("b", "", c.giver || "Unknown giver")),
                   c.kind_name ? t("span", "contract__kind", c.kind_name) : null,
                   c.reward ? h("p", "contract__reward", h("b", "num", c.reward), h("span", "", "aUEC")) : null);
    const card = h("article", "contract contract--" + kind, head, t("h2", "contract__title", c.title, 2));
    if (stops && stops.length) {
      card.appendChild(stopList(stops));
    } else {
      const objs = c.objectives || [];
      const ol = h("ol", "objs");
      if (kind !== "compact" && c.before > 0) ol.appendChild(h("li", "obj obj--cut", c.before + " more above"));
      objs.forEach((o, i) => {
        if (kind === "compact" && o.state !== "now") return;
        const st = o.state === "now" ? "now" : o.state === "done" ? "done" : o.state === "failed" ? "failed" : o.state === "next" ? "next" : "later";
        const li = h("li", "obj obj--" + st,
                     h("span", "obj__n", st === "done" ? icon("check") : st === "failed" ? icon("x") : two(c.before + i + 1)),
                     t("span", "obj__t", o.text, st === "now" ? 3 : 2),
                     o.optional ? h("span", "obj__opt", "optional") : null);
        if (st !== "now" && kind !== "compact") cut(li, 2);
        ol.appendChild(li);
      });
      if (kind === "compact" && !objs.some((o) => o.state === "now") && c.current) {
        ol.appendChild(h("li", "obj obj--now", h("span", "obj__n", "•"), t("span", "obj__t", c.current, 3)));
      }
      if (kind !== "compact" && c.after > 0) ol.appendChild(h("li", "obj obj--cut", "+ " + c.after + " more"));
      card.appendChild(ol);
    }
    if (c.count || c.status !== "active") {
      card.appendChild(h("p", "contract__count", c.count || "",
                         c.status && c.status !== "active" ? h("span", "contract__status contract__status--" + c.status, c.status) : null));
    }
    return card;
  }

  function stopList(stops) {
    return h("ol", "stops", stops.map((s, i) => {
      const st = s.state === "done" ? "done" : s.state === "active" ? "now" : "later";
      const amount = num(s.scu) ? (num(s.delivered) && s.kind === "dropoff" ? s.delivered + "/" + s.scu : String(s.scu)) : null;
      return h("li", "stop stop--" + st,
               h("span", "obj__n", st === "done" ? icon("check") : two(i + 1)),
               h("span", "stop__kind", s.kind === "pickup" ? "Pick up" : "Drop off"),
               h("span", "stop__what", t("b", "stop__place", s.place || "A stop"), s.item ? t("span", "stop__item", s.item) : null),
               amount ? h("span", "stop__scu num", amount, h("small", "", " SCU")) : null,
               s.verified === false ? icon("ring", "unv") : null);
    }));
  }

  /* The controls strip: the handful of stick and throttle controls for this mode. A control not
     yet confirmed in a ship (unverified, trial) is marked quietly. */
  function controlsBlock(c, prio) {
    return B("ctl", "ctl frame", c, (d) => {
      const anyUnv = d.items.some((x) => x.status === "unverified" || x.status === "trial");
      const n = h("div", "",
                  h("h2", "ctl__title cap", icon("stick"), h("span", "", d.title),
                    anyUnv ? h("span", "ctl__key", icon("ring"), "not yet confirmed in a ship") : null),
                  h("dl", "ctl__list", d.items.map((x, i) => {
                    const item = h("div", "ctl__item" + (x.status === "unverified" || x.status === "trial" ? " ctl--unv" : ""),
                                   t("dt", "", x.where), t("dd", "", x.what, 2),
                                   x.status === "unverified" || x.status === "trial" ? icon("ring", "ctl__mark") : null);
                    // past the first CTL_KEEP, a control is the first thing a crowded view drops
                    return i >= CTL_KEEP ? cut(item, 7) : item;
                  })));
      return cut(n, prio || 3);
    });
  }

  function lawPane(law) {
    if (!law || (!law.jurisdiction && !(law.marks || []).length)) return null;
    return h("div", "ref law", cap("Law here"),
             law.jurisdiction ? t("p", "law__j", law.jurisdiction) : null,
             h("ul", "marks", (law.marks || []).map((mk) => h("li", "mark" + (mk.on ? " mark--on" : " mark--off"), icon(mk.icon === "noshield" ? "noshield" : "eye"), t("span", "", mk.text)))));
  }

  function needRows(items) {
    return h("div", "needs", items.map((x) => h("div", "need" + (x.ok ? " need--ok" : ""),
      t("span", "need__name", x.name),
      h("b", "num", x.held || "–"),
      h("span", "need__of", "of " + (x.need || "?") + " " + (x.unit || "")),
      meter(x.fill, x.ok ? "meter--ok" : ""),
      x.note ? h("span", "need__note", x.ok ? icon("check") : null, x.note) : null)));
  }

  function fig(capText, big, unit, sub, extra) {
    return h("div", "fig" + (extra && extra.cls ? " " + extra.cls : ""),
             h("h2", "cap", capText, extra && extra.mark ? icon("ring", "fig__mark") : null),
             h("p", "fig__line", h("b", "fig__num num", big), unit ? h("span", "fig__unit", unit) : null),
             extra && extra.meter !== undefined ? meter(extra.meter, extra.meterCls) : null,
             sub ? t("p", "fig__sub", sub, 2) : null,
             extra && extra.note ? h("p", "fig__note", extra.note) : null);
  }

  function frameOnly(name) {
    const label = VIEW_LABEL[name] || name;
    return [B("head", "act__head", { name: name }, (d) => h("header", "", h("h1", "act__kind", icon(VIEW_ICON[d.name] || "dot"), label))),
            B("empty", "empty", null, () => h("div", "", h("p", "empty__t", "Nothing to show here yet"),
              h("p", "empty__sub", "This view's part of the dashboard could not be built just now.")))];
  }

  function emptyBlock(text, sub) {
    return B("empty", "empty", { text: text, sub: sub }, (d) => h("div", "", t("p", "empty__t", d.text, 2), d.sub ? t("p", "empty__sub", d.sub, 3) : null));
  }

  // ---------------------------------------------------------------- the views

  function vNow(m, b) {
    const out = [];
    const timers = ((b && b.timers) || []).filter((x) => x.state !== "done" || x.source === "quick");
    const main = m.timer || null;
    const others = timers.filter((x) => !main || x.id !== main.id).slice(0, MAX_OTHER_TIMERS);
    const hasPlan = !!(m.next || (m.steps && m.steps.length));
    out.push(B("top", "now__top", { next: m.next, steps: m.steps || [], loc: m.location, where: b.strip && b.strip.where,
                                    timer: main, planned: hasPlan }, (d, live) => {
      const row = h("div", "");
      if (d.planned) {
        const left = h("div", "now__next", cap("Next step"), d.next ? t("p", "next", d.next, 3) : null);
        if (d.steps.length) {
          left.appendChild(h("ol", "steps", d.steps.map((s) => h("li", "step step--" + s.state,
            icon(s.state === "done" ? "check" : s.state === "now" ? "now" : "later"), t("span", "", s.text)))));
        }
        row.appendChild(left);
      } else {
        const where = d.loc ? (d.loc.name || d.loc.short) : (d.where && d.where.text);
        row.appendChild(h("div", "now__place", cap(d.loc ? "You are at" : "Where"),
                          t("p", "place__name", where || "Not known yet", 2),
                          d.loc && d.loc.body ? t("p", "place__sub", "Near " + d.loc.body) : null));
      }
      if (d.timer) {
        const tm = d.timer;
        row.appendChild(h("div", "now__count count frame",
                          cap(tm.kind === "refinery" ? "Refinery" : tm.source === "quick" ? "Timer" : "Timer"),
                          timerFig(tm, "count__fig", live), timerMeter(tm, live),
                          h("p", "count__sub", t("b", "", (tm.where || tm.where_short || tm.label), 1), t("span", "", tm.label + " · " + tm.text, 2))));
        // A countdown many hours out is nothing to act on yet: it steps back and the next step
        // (or the place) leads, until it comes within FAR_TIMER_HOURS (then the view refits once).
        if (tm.state === "running" && num(tm.ready_ms)) {
          const isFar = (now) => tm.ready_ms - now > FAR_TIMER_HOURS * 3600000;
          let far = isFar(nowMs());
          row.classList.toggle("now__top--far", far);
          live.push((now) => {
            const f = isFar(now);
            if (f !== far) { far = f; row.classList.toggle("now__top--far", f); queueFit(); }
          });
        }
      }
      return row;
    }));
    if (m.here) {
      out.push(B("here", "act__next", m.here, (d) => cut(h("p", "", h("span", "cap", "Here"), t("span", "", d.do, 2),
                                                      d.run ? h("span", "act__next-run", d.run) : null), 3)));
    }
    if (m.materials) out.push(B("mats", "now__mats frame", m.materials, (d) => cut(matsPane(d), 2)));
    if (m.contract) out.push(B("con", "now__contract", m.contract, (d) => cut(contractCard(d, "compact"), 3)));
    if (others.length || (m.notes && m.notes.length)) {
      out.push(B("more", "now__more", { others: others, notes: m.notes || [] }, (d, live) => {
        const row = h("div", "");
        if (d.others.length) row.appendChild(cut(h("div", "now__timers", cap("Other timers"), timerRows(d.others, live)), 4));
        if (d.notes.length) row.appendChild(cut(h("div", "now__notes", cap("Notes"), h("ul", "notes", d.notes.map((x) => t("li", "", x, 2)))), 5));
        return row;
      }));
    }
    if (!hasPlan && !main && !m.materials && !m.contract && !(b.plan && b.plan.loaded)) {
      out.push(emptyBlock("No plan loaded", "The plan's steps, materials and timers show here once there is one."));
    }
    return out;
  }

  function matsPane(d) {
    return h("div", "",
             h("h2", "label", h("span", "cap", "Materials"), t("span", "asof", d.asof)),
             h("div", "mats", d.items.map((x) => h("div", "mat" + (x.ok ? " mat--ok" : ""),
               t("p", "mat__name", x.name + (x.min_quality ? " · q" + x.min_quality + "+" : "")),
               h("p", "mat__fig", h("b", "mat__held num", x.held || "–"), h("span", "mat__need", "of " + (x.need || "?") + " " + (x.unit || ""))),
               meter(x.fill, x.ok ? "meter--ok" : ""),
               h("p", "mat__note", x.ok ? icon("check") : null, x.note || "")))),
             d.first ? t("p", "mats__first", d.first) : null);
  }

  function vTravel(m, b) {
    const out = [];
    out.push(B("dest", "dest frame", { dest: m.dest, since: m.since_ms, since_text: m.since_text, label: m.clock_label,
                                       from: m.from, fuel: m.fuel, obstructed: m.obstructed }, (d, live) => {
      const main = h("div", "dest__main", cap("Heading to"));
      if (d.dest) {
        main.appendChild(t("p", "dest__name", d.dest.short || d.dest.name));
        const subs = [d.dest.name && d.dest.name !== d.dest.short ? d.dest.name : null, d.dest.sub].filter(Boolean).join(" · ");
        if (subs) main.appendChild(t("p", "dest__sub", subs, 2));
      } else {
        main.appendChild(h("p", "dest__name dest__name--none", "No destination"));
        main.appendChild(h("p", "dest__sub", "No quantum target is set"));
      }
      const via = [d.from ? "From " + d.from : null, d.fuel ? "fuel estimate " + d.fuel : null].filter(Boolean).join(" · ");
      if (via) main.appendChild(t("p", "dest__via", via));
      if (d.obstructed) main.appendChild(h("p", "dest__warn", icon("warn"), "The game says the destination is obstructed"));
      const n = h("div", "", main);
      if (num(d.since)) {
        const fig = h("b", "dest__fig num");
        const since = d.since;
        live.push((now) => setText(fig, hms(now - since)));
        n.appendChild(h("div", "dest__clock", cap(d.label || "Since the target was set"), fig, d.since_text ? h("p", "dest__since", d.since_text) : null));
      }
      return n;
    }));
    const legs = m.legs || [], arrive = m.arrive || [];
    if (legs.length || arrive.length) {
      out.push(B("body", "travel__body", { legs: legs, arrive: arrive, run: m.run }, (d) => {
        const row = h("div", "");
        if (d.legs.length) {
          row.appendChild(cut(h("div", "legs frame", d.run ? cap(d.run) : null,
            h("ol", "", d.legs.map((g) => h("li", "leg leg--" + g.state,
              h("span", "leg__dot", g.state === "done" ? icon("check") : null),
              h("div", "leg__words", t("p", "leg__place", g.place + (g.gm ? " · " + g.gm + " Gm" : "")), g.why ? t("p", "leg__why", g.why) : null))))), 3));
        }
        if (d.arrive.length) {
          row.appendChild(cut(h("div", "arrive frame", cap("On arrival"), h("ol", "", d.arrive.map((x) => t("li", "", x, 2)))), 2));
        }
        return row;
      }));
    }
    if (m.timer) {
      out.push(B("timer", "timer-line", m.timer, (tm, live) => cut(h("div", "", icon(tm.kind === "refinery" ? "flask" : "clock"),
        t("span", "", (tm.kind === "refinery" ? "Refinery: " : "") + tm.label + (tm.where_short ? " at " + tm.where_short : "") + " · " + tm.text),
        timerFig(tm, "timer-line__fig", live)), 4)));
    }
    if (m.controls) out.push(controlsBlock(m.controls, 5));
    return out;
  }

  function vMining(m, b) {
    const out = [headBlock("mining", m.where, b)];
    const ores = m.ores || [];
    if (ores.length) {
      out.push(B("ores", "act__hero ores frame", { ores: ores, from: m.ores_from }, (d) => {
        const n = h("div", "");
        if (d.from === "spot") n.appendChild(h("p", "ores__from", "No plan targets: the most common ores at this spot"));
        d.ores.slice(0, MAX_ORES).forEach((o, i) => {
          const rule = h("div", "ore__rule",
            o.take ? h("span", "q q--take", icon("ok"), h("span", "q__k", "Take"), h("b", "num", o.take)) : null,
            o.skip ? h("span", "q q--skip", icon("x"), h("span", "q__k", "Skip below"), h("b", "num", o.skip)) : null);
          const reads = (o.reads || []).slice(0, 3);
          const ore = h("div", "ore",
            h("div", "ore__head", t("h2", "ore__name", o.name), o.tier_text ? t("span", "ore__tier", o.tier_text) : null, rule),
            reads.length
              ? h("div", "reads", reads.map((r) => h("div", "read" + (r.top ? " read--top" : ""),
                  h("p", "read__fig num", r.scan),
                  h("p", "read__sub", h("span", "", r.rocks_text), meter(r.chance), h("span", "num", r.chance_text)))))
              : h("p", "ore__none", o.known === false ? "Not in the ore table: no scan figures" : "No scan figures for this spot"));
          if (i > 0) cut(ore, 2);
          n.appendChild(ore);
        });
        if (d.ores.length > MAX_ORES) n.appendChild(t("p", "ores__more", "Also: " + d.ores.slice(MAX_ORES).map((o) => o.name).join(", ")));
        return n;
      }));
    } else {
      out.push(emptyBlock("No ores to show", "The plan names no target ores, and this spot is not in the ore table."));
    }
    const left = m.goal || m.contract;
    const right = m.alike || m.refine;
    if (left || right) {
      out.push(B("main", "act__main", { goal: m.goal, contract: m.contract, alike: m.alike, refine: m.refine }, (d) => {
        const row = h("div", "");
        if (d.goal) {
          row.appendChild(h("div", "goal frame",
            h("h2", "label", h("span", "cap", "Goal"), t("span", "asof", d.goal.asof)),
            needRows(d.goal.items), d.goal.first ? t("p", "goal__next", d.goal.first, 2) : null));
        }
        if (d.contract) row.appendChild(cut(contractCard(d.contract, "compact"), 3));
        if (d.alike || d.refine) {
          const ref = cut(h("div", "act__ref frame"), 4);
          if (d.alike) ref.appendChild(h("div", "ref", cap("Look-alikes here"), t("p", "", d.alike, 3)));
          if (d.refine) ref.appendChild(refinePane(d.refine));
          row.appendChild(ref);
        }
        return cut(row, 2);
      }));
    }
    if (m.controls) out.push(controlsBlock(m.controls, 3));
    return out;
  }

  function refinePane(r) {
    return h("div", "ref", cap("Refine" + (r.method ? " · " + r.method : "")),
             (r.rows || []).map((x) => h("p", "rrow", t("span", "rrow__k", x.ore), t("span", "rrow__at", x.at),
               x.bonus ? h("b", "num" + (x.positive ? " pos" : " neg"), x.bonus) : h("span", "rrow__nob", "no report"))),
             (r.rows || []).some((x) => x.date) ? h("p", "ref__foot", "Bonuses crowd-reported: " +
               Array.from(new Set(r.rows.filter((x) => x.date).map((x) => dateWords(x.date)))).join(", ")) : null);
  }

  function vSalvage(m, b) {
    const out = [headBlock("salvage", m.where, b)];
    if (m.goal || m.hold) {
      out.push(B("hero", "act__hero figs frame", { goal: m.goal, hold: m.hold }, (d) => {
        const n = h("div", "");
        if (d.goal) n.appendChild(fig(d.goal.title || "Goal", d.goal.held || "–", "of " + (d.goal.need || "?") + " " + (d.goal.unit || ""),
                                      d.goal.sub, { cls: "fig--main", meter: d.goal.fill }));
        if (d.hold) n.appendChild(fig(d.hold.title || "Hold", d.hold.scu || "–", "SCU", d.hold.sub));
        return n;
      }));
    }
    if (m.next) out.push(B("next", "act__next", m.next, (d) => h("p", "", h("span", "cap", "Next"), t("span", "", d, 2))));
    if (m.contract || m.sell) {
      out.push(B("main", "act__main", { contract: m.contract, sell: m.sell }, (d) => {
        const row = h("div", "");
        if (d.contract) row.appendChild(contractCard(d.contract, "normal"));
        if (d.sell) row.appendChild(cut(h("div", "act__ref frame", sellPane(d.sell)), 4));
        return cut(row, 2);
      }));
    }
    if (!m.goal && !m.hold && !m.contract && !m.sell) {
      out.push(emptyBlock("No salvage goal in the plan", "The log cannot see what is scraped: the goal, the hold and where to sell come from the plan and the ship."));
    }
    if (m.controls) out.push(controlsBlock(m.controls, 3));
    return out;
  }

  function sellPane(s) {
    return h("div", "ref", cap(s.title || "Sell"),
             (s.rows || []).map((x) => h("p", "rrow", t("span", "rrow__k", x.what), t("span", "rrow__at", x.note || ""),
               x.price ? h("b", "num", x.price) : h("span", "rrow__nob", "no price"))),
             s.foot ? t("p", "ref__foot", s.foot) : null);
  }

  function vCombat(m, b) {
    const out = [headBlock("combat", m.where, b)];
    if (m.on_foot) {
      const side = !!(m.ship_left || m.law || m.health);
      if (m.contract || side) {
        out.push(B("main", "act__main act__main--foot", { contract: m.contract, ship_left: m.ship_left, law: m.law, health: m.health }, (d) => {
          const row = h("div", "");
          row.appendChild(d.contract ? contractCard(d.contract, "full") : h("div", "empty", h("p", "empty__t", "No contract"), h("p", "empty__sub", "The log records no kills on foot.")));
          const ref = h("div", "act__ref frame");
          if (d.health) ref.appendChild(h("div", "ref ref--health", cap("Health"), h("p", "ref__big ref__big--warn", icon("warn"), t("span", "", d.health, 2))));
          if (d.ship_left) {
            ref.appendChild(h("div", "ref ref--ship", cap("Your ship"), h("p", "ref__big", icon("ship"), t("span", "", d.ship_left.name || "Your ship")),
              t("p", "", [d.ship_left.where || "Left in the world", d.ship_left.when].filter(Boolean).join(" · "), 2)));
          }
          const lp = lawPane(d.law);
          if (lp) ref.appendChild(cut(lp, 4));
          if (ref.childNodes.length) row.appendChild(ref);
          return row;
        }));
      }
      return out;
    }
    // With a contract its objective leads (the largest type on the view), and the session's tally
    // follows it in smaller figures; without one the tally is the view's hero.
    const lead = !!m.contract;
    const tallyAt = out.length;
    if (m.tally || m.ship) {
      out.push(B("hero", "act__hero figs tally frame" + (lead ? " tally--minor" : ""), { ship: m.ship, tally: m.tally, downed: m.downed }, (d) => {
        const n = h("div", "");
        if (d.downed) cut(n, 3);           // downed: the contract matters more than the tally
        else if (lead) cut(n, 4);          // under a contract: a crowded view drops the tally before the controls
        const tl = d.tally || {};
        if (d.ship && !d.downed) {
          n.appendChild(h("div", "fig fig--ship", cap("Ship"), t("p", "fig__name", d.ship.name, 2), d.ship.note ? t("p", "fig__sub", d.ship.note, 2) : null));
        }
        if (d.tally) {
          const crip = tl.crippled > 0 ? " · " + tl.crippled + " crippled" : "";
          n.appendChild(fig("Destroyed", String(tl.destroyed || 0), null, "ships this session" + crip,
                            { mark: tl.kills_verified === false }));
          n.appendChild(fig("Lost", String(tl.lost || 0), null, "ships", { cls: tl.lost > 0 ? "fig--bad" : "" }));
          n.appendChild(fig("Downed", String(tl.downed || 0), null, "times", { cls: tl.downed > 0 ? "fig--bad" : "" }));
        }
        return n;
      }));
    }
    // "Downed" and "Dead" are the red alert's already
    if (m.health && !(m.downed && /^(Downed|Dead)$/.test(m.health))) {
      out.splice(tallyAt, 0, B("health", "act__next act__next--warn", m.health, (d) => h("p", "", icon("warn"), h("span", "cap", "Health"), t("span", "", d, 2))));
    }
    const lp = m.law && (m.law.jurisdiction || (m.law.marks || []).length);
    const mainAt = out.length - (m.tally || m.ship ? 1 : 0);   // just before the tally
    if (m.contract || lp) {
      const main = B("main", "act__main" + (lead ? " combat__lead" : ""), { contract: m.contract, law: m.law }, (d) => {
        const row = h("div", "");
        if (d.contract) row.appendChild(contractCard(d.contract, "normal"));
        const law = lawPane(d.law);
        if (law) row.appendChild(cut(h("div", "act__ref frame", law), 4));
        return lead ? row : cut(row, 2);
      });
      if (lead) out.splice(mainAt, 0, main);
      else out.push(main);
    }
    if (m.controls && !m.downed) out.push(controlsBlock(m.controls, 3));
    return out;
  }

  function vCargo(m, b) {
    const out = [headBlock("cargo", m.head, b)];
    // No stop under way: the next step leads (the model's `next` when it has one, else the trade's
    // sentences), and the grid's size is a plain figure beside it, not the hero.
    const tr = m.trade || {};
    const lead = m.this_stop ? null : (m.next || tr.sell || tr.bought || null);
    if (!m.this_stop && (lead || m.grid || m.contract_total)) {
      out.push(B("lead", "act__hero cargo__lead frame", { lead: lead, total: m.contract_total, grid: m.grid }, (d) => h("div", "",
        h("div", "cargo__next", cap(d.lead ? "Next step" : "No stop under way"),
          d.lead ? t("p", "next", d.lead, 3) : h("p", "cargo__none", "No pickup or drop-off is under way.")),
        d.total || d.grid ? h("div", "figs cargo__figs",
          d.total ? fig("Contract", d.total.big, d.total.unit, d.total.sub) : null,
          d.grid ? fig(d.grid.title || "Cargo grid", d.grid.big, d.grid.unit, d.grid.sub) : null) : null)));
    } else if (m.this_stop) {
      out.push(B("hero", "act__hero figs frame", { stop: m.this_stop, total: m.contract_total, grid: m.grid }, (d) => {
        const n = h("div", "");
        if (d.stop) {
          n.appendChild(fig(d.stop.here ? "This stop · you are here" : "This stop", d.stop.big, d.stop.unit, d.stop.sub,
                            { cls: "fig--main" + (d.stop.here ? " fig--here" : "") + (/[^\d.,]/.test(d.stop.big || "") ? " fig--word" : ""),
                              mark: d.stop.verified === false }));
        }
        if (d.total) n.appendChild(fig("Contract", d.total.big, d.total.unit, d.total.sub));
        if (d.grid) n.appendChild(fig(d.grid.title || "Cargo grid", d.grid.big, d.grid.unit, d.grid.sub));
        return n;
      }));
    }
    if (m.keys && m.keys.length) {
      out.push(B("keys", "act__next", m.keys, (d) => cut(h("p", "", h("span", "cap", "At a stop"),
        h("span", "keys", d.map((k) => h("span", "key", t("kbd", "", k.where), t("span", "", k.what))))), 4)));
    }
    if (m.contract || m.trade || m.earned) {
      out.push(B("main", "act__main", { contract: m.contract, stops: m.stops || [], trade: m.trade, earned: m.earned, used: lead }, (d) => {
        const row = h("div", "");
        if (d.contract) row.appendChild(contractCard(d.contract, "normal", d.stops));
        const said = d.trade ? [d.trade.bought, d.trade.sell].filter((x) => x && x !== d.used) : [];   // the lead's sentence is not said twice
        if (said.length || d.earned) {
          const ref = cut(h("div", "act__ref frame"), 4);
          if (said.length) ref.appendChild(h("div", "ref", cap("Trade"), said.map((x) => t("p", "", x, 3))));
          if (d.earned) ref.appendChild(h("div", "earn", cap("Earned this session"), h("b", "num", d.earned.big), h("span", "earn__u", d.earned.unit || "aUEC")));
          row.appendChild(ref);
        }
        return cut(row, 2);
      }));
    }
    if (!m.this_stop && !lead && !m.contract && !m.trade && !m.grid) {
      out.push(emptyBlock("No haul or trade under way", "The log cannot see what is aboard: stops come from a contract, trades from the plan."));
    }
    if (m.controls) {
      const keys = new Set((m.keys || []).map((k) => k.where + "|" + k.what));
      out.push(controlsBlock(Object.assign({}, m.controls, { items: m.controls.items.filter((x) => !keys.has(x.where + "|" + x.what)) }), 3));
    }
    if (m.unverified && m.unverified.length) {
      out.push(B("unv", "unverified", m.unverified, (d) => cut(h("div", "", d.map((x) => h("p", "", icon("ring"), t("span", "", x, 2)))), 6)));
    }
    return out;
  }

  function vMission(m, b) {
    const c = m.contract;
    const out = [headBlock("mission", c ? [c.kind_name, c.unmapped ? "not in the contract table" : null].filter(Boolean).join(" · ") : null, b)];
    if (!c) {
      out.push(emptyBlock("No contract active", "Accepted contracts show here with their objectives."));
      return out;
    }
    out.push(B("main", "mission", { c: c, go: m.go_next, others: m.others }, (d) => {
      const row = h("div", "", contractCard(d.c, "full"));
      const side = h("div", "mission__side");
      if (d.go) {
        side.appendChild(h("div", "mission__where frame", cap("Go next"),
          h("p", "where__place", icon("pin"), t("span", "", d.go.place || "Follow the contract's marker", 2)),
          d.go.sub ? t("p", "where__sub", d.go.sub, 2) : null));
      }
      const o = d.others || { count: 0, items: [] };
      if (o.count > 0) {
        side.appendChild(cut(h("div", "mission__others frame",
          h("h2", "label", h("span", "cap", "Also accepted"), h("span", "asof", o.count + " more")),
          h("ul", "others", (o.items || []).map((x, i) => cut(h("li", "other", t("b", "other__title", x.title), t("span", "other__giver", x.giver || ""),
            x.objective ? t("span", "other__obj", x.objective, 2) : null), 5 + i)))), 4));
      }
      if (side.childNodes.length) row.appendChild(side);
      return row;
    }));
    return out;
  }

  function vRefinery(m, b) {
    const st = m.station || {};
    const out = [headBlock("refinery", st.name, b, new Set((m.timers || []).map((x) => x.id)))];
    const mine = (m.timers || []).find((x) => x.state === "running") || null;
    out.push(B("hero", "act__hero refhero frame", { st: st, method: m.method, timer: mine }, (d, live) => {
      const n = h("div", "", h("div", "refhero__main", cap("Station"),
        t("p", "refhero__name", d.st.short || d.st.name || "Unknown station"),
        d.st.name && d.st.name !== d.st.short ? t("p", "refhero__sub", d.st.name) : null,
        d.method ? h("p", "refhero__method", h("span", "cap", "Method"), t("b", "", d.method.name), d.method.detail ? t("span", "refhero__detail", d.method.detail) : null) : null));
      if (d.timer) {
        n.appendChild(h("div", "refhero__count", cap("Order here"), timerFig(d.timer, "count__fig", live), timerMeter(d.timer, live),
                        t("p", "count__sub", d.timer.label + " · " + d.timer.text, 2)));
      }
      return n;
    }));
    const refine = m.refine || [], leave = m.leave || [];
    const ts = (m.timers || []).filter((x) => !mine || x.id !== mine.id);
    const done = m.done_here || [];
    if (refine.length || leave.length || ts.length || done.length || m.sold_ore || m.note) {
      out.push(B("panes", "refpanes", { refine: refine, leave: leave, ts: ts, done: done, sold: m.sold_ore, note: m.note, mine: !!mine }, (d, live) => {
        const row = h("div", "");
        if (d.refine.length) {
          row.appendChild(h("div", "act__ref frame", h("div", "ref", cap("Refine here"),
            d.refine.map((x) => h("p", "rrow rrow--big", t("span", "rrow__k", x.ore), t("span", "rrow__at", x.date ? "reported " + dateWords(x.date) : "no report"),
              x.bonus ? h("b", "num" + (x.positive ? " pos" : " neg"), x.bonus) : h("span", "rrow__nob", "–"))))));
        }
        if (d.leave.length) {
          row.appendChild(cut(h("div", "act__ref frame", h("div", "ref", cap("Leave out"),
            d.leave.map((x) => h("p", "rrow rrow--big", t("span", "rrow__k", x.ore), t("span", "rrow__at", x.why || ""), h("span", "rrow__nob", icon("x")))))), 3));
        }
        if (d.ts.length) row.appendChild(cut(h("div", "act__ref frame", cap(d.mine ? "Other orders here" : "Orders at this station"), timerRows(d.ts, live)), 4));
        const side = h("div", "act__ref frame");
        if (d.note) side.appendChild(h("div", "ref", cap("The plan says"), t("p", "", d.note, 3)));
        if (d.done.length) side.appendChild(h("div", "ref", cap("Completed here this session"), d.done.map((x) => t("p", "", x.text + (x.count > 1 ? " (" + x.count + ")" : ""), 2))));
        if (d.sold) side.appendChild(h("div", "ref", cap("Sold here"), h("p", "", "Ore was sold to this refinery this session (the log does not say what).")));
        if (side.childNodes.length) row.appendChild(cut(side, 5));
        return row;
      }));
    }
    return out;
  }

  function vSelling(m, b) {
    const out = [headBlock("selling", m.where, b)];
    const rows = m.rows || [];
    if (m.total || rows.length) {
      out.push(B("hero", "act__hero sellhero frame", { total: m.total, n: rows.length, from: m.prices_from }, (d) => {
        const parts = (d.total || "").split(" ");
        return h("div", "", h("div", "fig fig--main", cap("The plan's sell list here"),
          h("p", "fig__line", h("b", "fig__num num", parts[0] || "–"), parts.length > 1 ? h("span", "fig__unit", parts.slice(1).join(" ")) : null),
          h("p", "fig__sub", d.n + (d.n === 1 ? " line" : " lines") + " at the plan's prices" + (d.from ? " · terminal prices " + d.from : ""))));
      }));
      out.push(B("rows", "selltab frame", rows, (d) => {
        const head = h("div", "sr sr--head", h("span", "cap", "Commodity"), h("span", "cap sr__n", "SCU"), h("span", "cap sr__n", "Plan price"),
                       h("span", "cap sr__n", "Terminal"), h("span", "cap sr__n", "Value"));
        return h("div", "", head, d.map((x, i) => {
          const r = h("div", "sr",
            h("span", "sr__what", t("b", "", x.what), [x.quality ? "q" + x.quality : null, x.note].filter(Boolean).length
              ? t("span", "sr__note", [x.quality ? "quality " + x.quality : null, x.note].filter(Boolean).join(" · ")) : null),
            h("span", "sr__n num", x.scu || "–"), h("b", "sr__n sr__price num", x.price || "–"), h("span", "sr__n num", x.uex || "–"),
            h("span", "sr__n num", x.value || "–"));
          return i > 3 ? cut(r, 3 + i) : r;
        }));
      }));
    } else {
      out.push(emptyBlock("Nothing to sell here", "The plan has no sell list for this place."));
    }
    const sold = m.sold || [];
    if (sold.length) {
      out.push(B("sold", "act__ref frame", { sold: sold, unv: m.unverified || [] }, (d) => cut(h("div", "", h("div", "ref", cap("Sold here this session"),
        d.sold.map((x) => h("p", "rrow", t("span", "rrow__at", x.text), h("span", "num", x.time || "")))),
        d.unv.map((x) => t("p", "ref__foot", x, 2))), 4)));
    }
    return out;
  }

  function vPreflight(m) {
    const out = [];
    const verdict = m.verdict === "fail" ? "fail" : m.verdict === "pass" ? "pass" : "waiting";
    out.push(B("head", "fail__head fail__head--" + verdict, { k: m.kicker, t: m.title, w: m.why, v: verdict }, (d) => h("div", "",
      icon(d.v === "fail" ? "stop" : d.v === "pass" ? "ok" : "clock", "fail__icon"),
      h("div", "fail__words", t("p", "fail__kicker", d.k || "Preflight"), t("h1", "fail__title", d.t || "", 2), d.w ? t("p", "fail__why", d.w, 3) : null))));
    if (m.note) out.push(B("note", "pfnote", m.note, (d) => h("p", "", icon("check"), t("span", "", d, 2))));
    const devs = m.devices || [];
    if (devs.length) {
      out.push(B("devs", "devs frame devs--" + verdict, devs, (d) => h("ol", "", d.map((x) => h("li", "dev dev--" + (x.mark === "bad" ? "bad" : x.mark === "ok" ? "ok" : "info"),
        t("span", "dev__slot", x.slot), h("span", "dev__name", t("b", "", x.name), t("small", "", x.role)),
        x.mark === "info" ? h("span", "dev__mark dev__mark--info", "Listed") : h("span", "dev__mark", icon(x.mark === "ok" ? "check" : "x"), x.mark_text || (x.mark === "ok" ? "Found" : "Missing")))))));
    }
    if (m.do) out.push(B("do", "do", m.do, (d) => h("div", "", h("span", "do__k", "Do this"), t("p", "do__text", d, 3))));
    const notes = m.plan_notes || [];
    if (notes.length || m.profile) {
      out.push(B("notes", "pfnotes", { notes: notes, profile: m.profile }, (d) => cut(h("div", "",
        d.notes.length ? h("div", "pfnotes__list", cap("Before you fly"), d.notes.map((x) => h("p", "note", icon("warn"), t("span", "", x, 2)))) : null,
        d.profile ? h("p", "pfnotes__profile", icon("stick"), t("span", "", d.profile)) : null), 3)));
    }
    return out;
  }

  function vIdle(m) {
    const out = [];
    out.push(B("hello", "idle__hello", { t: m.title, l: m.last }, (d) => h("div", "", t("h1", "idle__state", d.t || "Nothing running"), d.l ? t("p", "idle__since", d.l) : null)));
    const facts = m.facts || [];
    if (facts.length) {
      out.push(B("facts", "facts figs frame", facts, (d) => h("div", "", d.map((x) => h("div", "fig", h("p", "fig__line", h("b", "fig__num num", x.value)), t("p", "fig__sub", x.label))))));
    }
    const lists = m.lists || [];
    if (m.next || (m.notes || []).length || lists.length) {
      out.push(B("bottom", "idle__bottom", { next: m.next, notes: m.notes || [], lists: lists }, (d) => {
        const row = h("div", "");
        if (d.next || d.notes.length) {
          row.appendChild(h("div", "idle__next", cap("The plan's next step"), d.next ? t("p", "next", d.next, 3) : h("p", "idle__none", "The plan names no next step."),
            d.notes.map((x) => cut(h("p", "note", icon("warn"), t("span", "", x, 2)), 4))));
        }
        if (d.lists.length) {
          row.appendChild(cut(h("div", "idle__last frame", cap("Last session"), h("ul", "list", d.lists.map((x) => h("li", x.ok ? "list--ok" : "",
            h("b", "", x.label), h("span", "", x.ok ? icon("ok") : null, t("span", "", x.text, 3)))))), 3));
        }
        return row;
      }));
    }
    return out;
  }

  // ================================================================ the rig reference
  /* The MOZA stick and throttle, every control with its job beside the manufacturer's numbered
     diagrams (PLAN §4 item 18), read from /rig/rig.json: schema 2, written with the diagram PNGs
     by tools/regen_cards.py (dashboard/web/rig/). Eight pages, one per piece of hardware, plus
     Find; a mode filter (all, flight, mining, salvage) decides which job each control shows.

     It is operated with the mouse, so it lives outside the block system: one block whose node is
     built once and kept, so the page, the filter and the open row survive a trip back to Live.
     Nothing here runs on the one-second tick or before the section is first opened: rig.json is
     fetched then, and a diagram's image only when a page that shows it is drawn. A click or a
     typed letter redraws the section's head and body; pointing only toggles classes; one
     ResizeObserver refits the diagram (an arriving alert shrinks it). Every text from the file is
     set as text. The page draws its own numbers over the art's marks, where `discs` puts them. */

  // choices, one line each
  const RIG_FILTERS = [["all", "All"], ["flight", "Flight"], ["mining", "Mining"], ["salvage", "Salvage"]];
  const RIG_MODE_ON_OPEN = "every";    // the filter takes the live views' mode every time the reference opens ("first": the first time only)
  const RIG_UNKNOWN = "keep";          // a control the docs say nothing about in a mode is drawn as keeping its job ("none": as doing nothing)
  const RIG_FEED_LINES = "1";          // event lines kept under the open reference: "0", "1" or "all"
  const RIG_SHOW_UNBOUND = true;       // unbound controls drawn dim on the diagram (false: left off it)
  const RIG_WHEN = true;               // when a flight report was made, small beside its mark
  const RIG_ARROWS = true;             // "Right hat up" written "Right hat ↑"
  const RIG_NOTES = true;              // a page's notes, under the diagram or the rows, where they fit
  const RIG_FIND_BOX = true;           // Find has a text box (every control is reachable by clicks too)
  const RIG_FIND_LEAD = true;          // Find opens with the controls the current filter changes
  const RIG_TAB_NAMES = { dials: "Dials" };   // tab names shorter than the file's title
  const RIG_ROWS_GROW = 160;           // px the rows column may take from the diagram beside it when its rows do not fit (0: never)
  const RIG_ART_MIN = 1;               // ...but the diagram stays at this scale or more, at the file's scale_18,
  const RIG_DISC_GAP = 14;             // ...and where two round numbers keep this many px between them (the art's arrows stay in sight)
  const RIG_DISC_MIN = 30;             // px: a number the page draws is never in a smaller disc (18 px digits)
  const RIG_BOX_MIN = 28;              // px: the same for a switch position, which the art draws as a box
  const RIG_MARKS = {                  // status -> icon, word, what it means (rig.json's own meaning replaces the third when it has one)
    flown: ["check", "Flown", "Confirmed in a ship"],
    unverified: ["ring", "Unverified", "Bound, not yet confirmed in a ship"],
    trial: ["tri", "Trial", "The docs call this binding a trial"],
  };
  const rigMeaning = {};               // status -> the file's meaning (`_meta.status`), its first clause

  const RIG_ARROW = { up: "↑", down: "↓", left: "←", right: "→" };
  const RIG_IMAGE = /^[a-z0-9_]{1,48}\.png$/;     // the names the service serves under /rig/
  // root: the section's node; api: the mounted section; shown: drawn since the view last changed;
  // opened: opened once; mode: the filter to start on when the file arrives
  const rig = { root: null, api: null, loading: null, shown: false, opened: false, mode: null };

  function vReference(m) {
    const root = rig.root || (rig.root = h("div", "rig"));
    if (!rig.shown) {
      rig.shown = true;
      rigOpen(m && m.mode);
    }
    return [B("ref", "", null, () => root)];
  }

  function rigOpen(mode) {
    const want = (RIG_MODE_ON_OPEN === "every" || !rig.opened) && RIG_FILTERS.some((f) => f[0] === mode) ? mode : null;
    rig.opened = true;
    if (rig.api) {
      if (want) rig.api.set({ mode: want });
      return;
    }
    if (want) rig.mode = want;
    if (!rig.loading) rigLoad();
  }

  function rigLoad() {
    const root = rig.root;
    root.textContent = "";
    root.appendChild(h("p", "rig__wait", "Loading the rig reference…"));
    rig.loading = fetch("/rig/rig.json", { cache: "no-cache" })
      .then((r) => {
        if (!r.ok) throw new Error("the service answered " + r.status);
        return r.json();
      })
      .then((json) => {
        rig.api = rigMount(root, rigModel(json), rig.mode || "flight");
      })
      .catch((err) => {
        rig.loading = null;
        root.textContent = "";
        const again = h("button", "pbtn", "Try again");
        again.type = "button";
        again.addEventListener("click", rigLoad);
        root.appendChild(h("div", "rig__fail frame", h("p", "rig__fail-t", "The rig reference could not be loaded"),
                           h("p", "rig__fail-sub", String((err && err.message) || err)), again));
      });
  }

  /* rig.json -> the model the section draws. A plain read of schema 2 (dashboard/RIG.md):
       model  {modes [{id, name, detent}], modeName {id: name}, live {filter: [mode id]},
               pages [page], rows [row] (in card order), total, lost (rows no page holds)}
       page   {id, device, devName, title, tab, caption, image, w, h, notes, numbers,
               rows [row with buttons], axes [row without]}
       row    {id, label, nums, text, where, group, unbound, status, when, modes {mode: primary |
               variant | none | unknown}, variants [{mode, text, status, when}], jobs [{press, text,
               modes {mode: live | none | unknown}, status, when}], discs [{n, word, x, y, w, h, box}],
               page, brk (a new control starts here)} */
  function rigModel(json) {
    const meta = json && json._meta;
    if (!meta || meta.schema !== 2) {
      throw new Error("this page reads rig.json schema 2, and the file is schema " + (meta && num(meta.schema) ? meta.schema : "unknown"));
    }
    const str = (x) => (typeof x === "string" ? x : "");
    const list = (x) => (Array.isArray(x) ? x : []);
    const mark = (s) => (RIG_MARKS[s] ? s : null);
    // What each mark means, in the file's own words: the clause before its first ":" or ";"
    // (the rest says where the docs record it), at most 160 characters; else the page's own.
    const said = meta.status && typeof meta.status === "object" ? meta.status : {};
    for (const k of Object.keys(RIG_MARKS)) {
      const first = str(said[k]).split(/[:;]/)[0].trim();
      if (first && first.length <= 160) rigMeaning[k] = first;
      else delete rigMeaning[k];
    }
    const modes = list(json.modes).map((m) => ({ id: str(m.id), name: str(m.name),
                                                 detent: m.knob && num(m.knob.detent) ? m.knob.detent : null }));
    const modeName = {};
    for (const m of modes) modeName[m.id] = m.name;
    const live = {};
    for (const [f] of RIG_FILTERS) {
      if (f !== "all") live[f] = list(json.live_modes && json.live_modes[f]).filter((id) => modeName[id]);
    }
    const byId = new Map();
    for (const r of list(json.rows)) {
      byId.set(str(r.id), {
        id: str(r.id), label: str(r.label), nums: list(r.buttons).filter(num), text: str(r.text), where: str(r.where),
        group: str(r.group), unbound: r.unbound === true, status: mark(r.status), when: str(r.status_when) || null,
        modes: r.modes && typeof r.modes === "object" ? r.modes : {},
        variants: list(r.variants).map((v) => ({ mode: str(v.mode), text: str(v.text), status: mark(v.status), when: str(v.status_when) || null })),
        jobs: list(r.jobs).map((j) => ({ press: str(j.press), text: str(j.text), modes: j.modes && typeof j.modes === "object" ? j.modes : {},
                                         status: mark(j.status), when: str(j.status_when) || null })),
        discs: list(r.discs).filter((d) => num(d.x) && num(d.y)).map((d) => ({
          n: num(d.n) ? d.n : null, word: str(d.word), x: d.x, y: d.y, w: num(d.w) ? d.w : 16, h: num(d.h) ? d.h : 16, box: d.box === true })),
        view: str(r.view), page: null, brk: false,
      });
    }
    const devName = {};
    for (const d of list(json.devices)) devName[str(d.id)] = str(d.name);
    const pages = list(json.views).map((v) => {
      const own = list(v.rows).map((id) => byId.get(id)).filter((r) => r && r.view === v.id && !r.page);
      const p = { id: str(v.id), device: str(v.device), devName: devName[v.device] || str(v.device), title: str(v.title),
                  tab: RIG_TAB_NAMES[v.id] || str(v.title), caption: str(v.caption),
                  image: RIG_IMAGE.test(str(v.image)) ? v.image : null, w: num(v.w) ? v.w : 0, h: num(v.h) ? v.h : 0,
                  scale18: num(v.scale_18) ? v.scale_18 : 1,
                  notes: list(v.notes).map(str).filter(Boolean),
                  rows: own.filter((r) => r.nums.length), axes: own.filter((r) => !r.nums.length) };
      for (const r of own) r.page = p;
      for (const rows of [p.rows, p.axes]) rows.forEach((r, i) => { r.brk = i > 0 && r.group !== rows[i - 1].group; });
      const round = [];                  // the closest two round numbers, for the smallest scale that keeps them apart
      for (const r of own) for (const d of r.discs) if (d.n !== null && !d.box) round.push(d);
      let close = Infinity;
      round.forEach((a, i) => { for (const b of round.slice(i + 1)) close = Math.min(close, Math.hypot(a.x - b.x, a.y - b.y)); });
      p.floor = Math.max(RIG_ART_MIN, p.scale18, isFinite(close) && close > 0 ? (RIG_DISC_MIN + RIG_DISC_GAP) / close : 0);
      const nums = rigRanges(list(v.buttons));
      p.numbers = p.axes.length ? (nums ? nums + " + axes" : "axes") : nums;
      return p;
    }).filter((p) => p.id);
    const rows = [];
    for (const r of byId.values()) if (r.page) rows.push(r);
    return { modes: modes, modeName: modeName, live: live, pages: pages, rows: rows, total: rows.length,
             lost: byId.size - rows.length };
  }

  function rigRanges(nums) {             // [1, 3, 4, 6, 22, 23, 24] -> "1 · 3–4 · 6 · 22–24"
    const xs = nums.filter(num).sort((a, b) => a - b);
    const out = [];
    for (let i = 0; i < xs.length;) {
      let j = i;
      while (j + 1 < xs.length && xs[j + 1] === xs[j] + 1) j++;
      out.push(j > i ? xs[i] + "–" + xs[j] : String(xs[i]));
      i = j + 1;
    }
    return out.join(" · ");
  }
  const rigDashes = (s) => s.replace(/(\d)-(\d)/g, "$1–$2");
  const rigWhere = (s) => (RIG_ARROWS && s.indexOf("/") < 0 ? s.replace(/ (up|down|left|right)$/i, (x, d) => " " + RIG_ARROW[d.toLowerCase()]) : s);
  const rigActs = (state) => state === "primary" || state === "variant";
  const rigNames = (ids, M) => ids.map((id) => M.modeName[id] || id).join(", ");
  function rigWhen(when) {               // "2026-11-26" -> "Nov 26"; other wording as it is
    return /^\d{4}-\d{2}-\d{2}$/.test(when) ? dateWords(when) : when;
  }

  /* What one control does under a filter (the reading rule in RIG.md, "Reading a page filter").
       kind  change   the filter's mode gives it another job (cyan)
             own      a job of the filter's mode only, such as the jettison key under Mining (cyan)
             keep     it keeps its job (white); also a control whose mode the docs do not know
             none     nothing on it acts there (gray)
             all      the All filter: the printed card
             unbound  nothing is bound to it
       text, status, when: the job shown; tag: a mode's name beside it (under Flight, a control
       live in missile or scan mode only; a gray control's own modes); subs: more lines (the
       filter's other modes' jobs, a tap or hold half that does nothing there). */
  function rigJob(r, f, M) {
    const o = { kind: "all", text: r.text, status: r.status, when: r.when, tag: null, subs: [] };
    if (r.unbound) {
      o.kind = "unbound";
      return o;
    }
    const home = r.modes.combat === "primary";
    const primaries = M.modes.filter((m) => r.modes[m.id] === "primary").map((m) => m.id);
    if (f === "all") {
      if (!home && primaries.length) o.tag = rigNames(primaries, M);
      for (const v of r.variants) o.subs.push({ tag: M.modeName[v.mode] || v.mode, text: v.text, status: v.status, when: v.when });
      return o;
    }
    const L = M.live[f] || [];
    const m = L.find((id) => rigActs(r.modes[id]));
    if (m) {
      const v = r.modes[m] === "variant" ? r.variants.find((x) => x.mode === m) : null;
      if (v) Object.assign(o, { kind: "change", text: v.text, status: v.status, when: v.when });
      else o.kind = home || f === "flight" ? "keep" : "own";
      if (m !== L[0]) o.tag = M.modeName[m] || m;
      for (const x of r.variants) {
        if (x.mode !== m && L.indexOf(x.mode) >= 0) o.subs.push({ tag: M.modeName[x.mode] || x.mode, text: x.text, status: x.status, when: x.when });
      }
    } else if (L.some((id) => r.modes[id] === "unknown")) {
      o.kind = RIG_UNKNOWN === "none" ? "none" : "keep";
    } else {
      o.kind = "none";
      const acts = M.modes.filter((x) => rigActs(r.modes[x.id])).map((x) => x.id);
      if (!home && acts.length) o.tag = rigNames(acts, M) + (acts.length === 1 ? " only" : "");
    }
    if (o.kind !== "none") {
      const name = (RIG_FILTERS.find((x) => x[0] === f) || [f, f])[1].toLowerCase();
      for (const j of r.jobs) {
        if (L.length && L.every((id) => j.modes[id] === "none")) {
          o.subs.push({ tag: j.press, text: j.text, off: "not in " + name + " mode" });
        }
      }
    }
    return o;
  }

  /* An opened row: its job in every mode, modes with the same job on one line, then each half of a
     tap / hold key. */
  function rigEvery(r, M) {
    if (r.unbound) return [{ tag: "Every mode", text: "Nothing is bound to it", quiet: true }];
    const groups = [];
    for (const m of M.modes) {
      const s = r.modes[m.id];
      const v = s === "variant" ? r.variants.find((x) => x.mode === m.id) : null;
      const key = v ? "v:" + v.text : s === "primary" ? "p" : s === "none" ? "none" : "unknown";
      let g = groups.find((x) => x.key === key);
      if (!g) {
        g = { key: key, ids: [] };
        if (v) Object.assign(g, { text: v.text, status: v.status, when: v.when });
        else if (key === "p") Object.assign(g, { text: r.text, status: r.jobs.length ? null : r.status, when: r.jobs.length ? null : r.when });
        else Object.assign(g, { text: key === "none" ? "Nothing" : "Not known: the docs do not say", quiet: true });
        groups.push(g);
      }
      g.ids.push(m.id);
    }
    const lines = groups.map((g) => ({ tag: g.ids.length === M.modes.length ? "Every mode" : rigNames(g.ids, M),
                                       text: g.text, status: g.status, when: g.when, quiet: !!g.quiet }));
    for (const j of r.jobs) {
      const none = M.modes.filter((m) => j.modes[m.id] === "none").map((m) => m.id);
      const unknown = M.modes.filter((m) => j.modes[m.id] === "unknown").map((m) => m.id);
      const note = [none.length ? "not in " + rigNames(none, M) : "",
                    unknown.length ? (unknown.length === M.modes.length ? "modes not known" : rigNames(unknown, M) + " not known") : ""]
        .filter(Boolean).join("; ");
      lines.push({ tag: j.press, text: j.text, status: j.status, when: j.when, off: note });
    }
    return lines;
  }

  /* A status mark: the icon (with its word in the key). `when` beside it: a date in a row's own
     line ("Nov 26"), longer wording ("June 2026, Alpha 4.8") only in an opened row (`full`). */
  function rigMark(status, when, word, full) {
    const m = RIG_MARKS[status];
    if (!m) return null;
    const s = h("span", "rmk rmk--" + status + (word ? "" : " rmk--bare"), icon(m[0]));
    s.title = (rigMeaning[status] || m[2]) + (when ? " (" + when + ")" : "");
    if (word) s.append(m[1]);
    else s.appendChild(h("span", "sw__sr", m[1]));
    if (when && RIG_WHEN && !word && (full || /^\d{4}-\d{2}-\d{2}$/.test(when))) s.appendChild(h("span", "rmk__when num", rigWhen(when)));
    return s;
  }
  function rigButton(cls, text) {
    const b = h("button", cls, text);
    b.type = "button";
    return b;
  }

  /* One row: the number as the diagram prints it, the job, where the control is, a mark; then
     more lines (other modes, every mode when opened). */
  function rigRow(r, f, M, opened, every) {
    const o = rigJob(r, f, M);
    const kind = o.kind === "change" || o.kind === "own" ? " rr--em" : o.kind === "none" ? " rr--quiet" : "";
    const li = h("li", "rr" + kind + (r.unbound ? " rr--unbound" : "") + (opened ? " rr--sel" : "") + (r.brk ? " rr--brk" : ""));
    li.dataset.key = r.id;
    li.appendChild(h("b", "rr__n" + (/^\d{1,2}$/.test(r.label) ? "" : " rr__n--wide"), rigDashes(r.label)));
    const shown = rigWhere(r.where);
    const where = r.where ? h("span", "rr__h" + (/[↑↓←→]$/.test(shown) ? " rr__h--dir" : ""), shown) : null;   // a direction is never cut off
    if (where) where.title = r.where;                  // whole, when the row cuts it short
    li.appendChild(h("div", "rr__l", h("span", "rr__f", o.text), o.tag ? h("span", "rr__tag", o.tag) : null, where));
    const all = opened || every;
    const mk = rigMark(o.status, o.when, false, false);
    if (mk) li.appendChild(mk);
    const subs = all ? rigEvery(r, M) : o.subs;
    for (const [i, s] of subs.entries()) {
      li.appendChild(h("div", "rr__v" + (s.quiet ? " rr__v--quiet" : "") + (all && i === 0 ? " rr__v--first" : ""),
                       h("span", "rr__t", s.tag), h("span", "rr__vt", s.text), s.off ? h("span", "rr__off", s.off) : null));
      const vm = rigMark(s.status, s.when, false, all);
      if (vm) li.appendChild(vm);
    }
    return li;
  }
  function rigList(rows, f, M, sel, every) {
    const ol = h("ol", "rr-list" + (rows.length > 11 ? " rr-list--long" : "") +
                       (rows.some((r) => !/^\d{1,2}$/.test(r.label)) ? " rr-list--wide" : ""));
    for (const r of rows) ol.appendChild(rigRow(r, f, M, sel === r.id, every));
    return ol;
  }

  /* Find: every row a phrase or every word matches. A number is a button number (58 finds 57-59);
     words match the job, where, the control, the page and every mode's wording. */
  function rigHay(r, M) {
    return [r.label, r.text, r.where, r.group, r.page.title, r.page.tab, r.page.devName]
      .concat(r.variants.map((v) => (M.modeName[v.mode] || v.mode) + " " + v.text), r.jobs.map((j) => j.press + " " + j.text))
      .join(" ").toLowerCase();
  }
  function rigSearch(rows, q, M) {
    const tokens = q.toLowerCase().split(/\s+/).filter(Boolean);
    if (!tokens.length) return rows;
    const phrase = tokens.join(" ");
    if (tokens.length > 1) {
      const exact = rows.filter((r) => rigHay(r, M).indexOf(phrase) >= 0);
      if (exact.length) return exact;
    }
    return rows.filter((r) => {
      const hay = rigHay(r, M);
      return tokens.every((x) => (/^\d+$/.test(x) ? r.nums.indexOf(parseInt(x, 10)) >= 0 : hay.indexOf(x) >= 0));
    });
  }
  /* The rows a filter brings to the front: those it changes; under Flight, those that act in
     missile or scan mode only or change job there. */
  function rigLeads(r, f, M) {
    const o = rigJob(r, f, M);
    if (f === "flight") return !!o.tag && o.kind !== "none" || o.subs.some((s) => !s.off);
    return o.kind === "change" || o.kind === "own";
  }

  function rigMount(root, M, mode) {
    const st = { page: M.pages.length ? M.pages[0].id : "find", mode: mode, q: "", sel: null };
    let hot = null, fitWatch = null, moreWatch = null;
    root.textContent = "";
    const head = h("header", "rig__head");
    const body = h("div", "rig__main");
    root.append(head, body);
    const rowById = new Map(M.rows.map((r) => [r.id, r]));
    const filterName = (f) => (RIG_FILTERS.find((x) => x[0] === f) || [f, f])[1];

    function change(patch, keepFind) {
      Object.assign(st, patch);
      draw(keepFind);
    }

    // ---- the head: the pages (by device), the marks' key, the mode filter
    function drawHead() {
      head.textContent = "";
      const tabs = h("nav", "tabs");
      tabs.setAttribute("aria-label", "Rig part");
      const group = (label) => {
        const row = h("div", "tabs__row");
        row.setAttribute("role", "tablist");
        tabs.appendChild(h("div", "tabs__g", label ? h("span", "cap tabs__k", label) : null, row));
        return row;
      };
      const tab = (id, name, numbers, count, ico) => {
        const b = rigButton("tab" + (count ? " tab--em" : ""));
        b.setAttribute("role", "tab");
        b.setAttribute("aria-selected", String(st.page === id));
        b.dataset.page = id;
        b.append(h("span", "tab__name", ico ? icon(ico) : null, name),
                 h("span", "tab__n num", count ? count + " " + st.mode : numbers));
        if (count) b.title = count + " of these controls change in " + st.mode + " mode";
        b.addEventListener("click", () => { if (st.page !== id) change({ page: id, sel: null }); });
        return b;
      };
      const counted = st.mode === "mining" || st.mode === "salvage";
      let lead = 0, row = null, dev = null;
      for (const p of M.pages) {
        if (p.device !== dev) {
          dev = p.device;
          row = group(p.devName);
        }
        const n = counted ? p.rows.concat(p.axes).filter((r) => rigLeads(r, st.mode, M)).length : 0;
        lead += n;
        row.appendChild(tab(p.id, p.tab, p.numbers, n, null));
      }
      group("").appendChild(tab("find", "Find", "all " + M.total, lead, "find"));
      head.appendChild(tabs);

      // The key and the filter travel together (`rig__tools`): beside the tabs when the row has
      // room for all three, on a row of their own when it does not (style.css), never on top.
      const legend = h("div", "legend");
      legend.setAttribute("aria-label", "Marks");
      for (const k of Object.keys(RIG_MARKS)) legend.appendChild(rigMark(k, null, true, false));
      const tools = h("div", "rig__tools", legend);
      head.appendChild(tools);

      const detents = (M.live[st.mode] || []).map((id) => (M.modes.find((x) => x.id === id) || {}).detent).filter(num);
      const modes = h("div", "modes", h("span", "cap modes__k", detents.length ? "Mode · knob " + rigRanges(detents) : "Mode"));
      const mrow = h("div", "modes__row");
      for (const [id, label] of RIG_FILTERS) {
        const b = rigButton("mode", label);
        b.dataset.mode = id;
        b.setAttribute("aria-pressed", String(st.mode === id));
        b.addEventListener("click", () => { if (st.mode !== id) change({ mode: id }, true); });
        mrow.appendChild(b);
      }
      modes.appendChild(mrow);
      tools.appendChild(modes);
    }

    // ---- a page: the diagram and its rows
    function drawPage(p) {
      const wrap = h("div", "rig__body" + (p.image ? "" : " rig__body--bare"));
      wrap.dataset.page = p.id;
      const all = p.rows.concat(p.axes);
      const pane = h("div", "rows");
      const scroll = h("div", "rows__scroll");
      scroll.appendChild(rigList(p.rows, st.mode, M, st.sel, false));
      if (p.axes.length) {
        scroll.appendChild(h("h3", "cap rows__k", "Axes"));
        scroll.appendChild(rigList(p.axes, st.mode, M, st.sel, false));
      }
      pane.appendChild(scroll);
      const notes = RIG_NOTES && p.notes.length ? pane.appendChild(rigNotes(p, "rnote rnote--rows")) : null;
      pane.appendChild(more(scroll, pane, notes));
      if (p.image) {
        const fig = h("figure", "dg frame", h("figcaption", "dg__cap", h("span", "cap", p.devName + " · " + p.title)));
        const stage = h("div", "dg__stage");
        const art = h("div", "dg__art");
        const img = h("img", "dg__img");
        img.alt = (p.caption || p.title) + ": the manufacturer's diagram";
        img.draggable = false;
        img.decoding = "async";
        img.src = "/rig/" + p.image;                   // requested now, not before
        art.appendChild(img);
        const discs = [];
        for (const r of all) {
          if (r.unbound && !RIG_SHOW_UNBOUND) continue;
          const o = rigJob(r, st.mode, M);
          const kind = o.kind === "change" || o.kind === "own" ? " dn--em" : o.kind === "none" ? " dn--quiet" : o.kind === "unbound" ? " dn--off" : "";
          for (const d of r.discs) {
            const b = rigButton("dn" + (d.n === null ? " dn--axis" : d.box ? " dn--box" : "") + kind + (st.sel === r.id ? " is-sel" : ""),
                                d.n === null ? "" : String(d.n));
            b.dataset.key = r.id;
            b.title = (d.n === null ? d.word || r.label : d.n) + ": " + o.text;
            if (d.n === null) b.setAttribute("aria-label", rigDashes(r.label));
            art.appendChild(b);
            discs.push({ d: d, b: b });
          }
        }
        stage.appendChild(art);
        fig.appendChild(stage);
        const dnotes = RIG_NOTES && p.notes.length ? fig.appendChild(rigNotes(p, "rnote rnote--dg")) : null;
        wrap.appendChild(fig);

        /* The diagram at the largest scale its pane allows (up to --dg-max), the numbers over it.
           A page note under the diagram never costs the diagram its size. Beside the diagram, rows
           that would scroll first take width from it (RIG_ROWS_GROW), down to the page's floor
           (RIG_ART_MIN, scale_18, RIG_DISC_GAP). Run when the page's region changes size, never on
           the tick. */
        const max = () => parseFloat(getComputedStyle(fig).getPropertyValue("--dg-max")) || 2.4;
        const room = discs.length ? 16 : 0;            // a number at the art's edge overhangs it a little
        const widthScale = () => Math.min((stage.clientWidth - room) / p.w, max());
        const grow = () => {
          wrap.style.removeProperty("--rows-w");
          if (!RIG_ROWS_GROW || getComputedStyle(wrap).gridTemplateColumns.split(" ").length !== 2) return;
          const base = pane.offsetWidth, floor = p.floor;
          for (let w = base + 20; w <= base + RIG_ROWS_GROW && scroll.scrollHeight > scroll.clientHeight + 1; w += 20) {
            wrap.style.setProperty("--rows-w", w + "px");
            if (pane.offsetWidth !== w || widthScale() < floor) {   // not a column that takes it, or the diagram too small
              if (w === base + 20) wrap.style.removeProperty("--rows-w");
              else wrap.style.setProperty("--rows-w", (w - 20) + "px");
              break;
            }
          }
        };
        const fit = () => {
          if (!wrap.isConnected || !wrap.clientWidth) return;
          grow();
          const byWidth = widthScale();
          const scale = () => Math.max(0.25, Math.min(byWidth, (stage.clientHeight - room) / p.h));
          if (dnotes) {
            dnotes.hidden = false;
            if (scale() < byWidth - 0.004) dnotes.hidden = true;
          }
          const s = scale();
          const px = (v) => (Math.round(v * s * 100) / 100) + "px";
          art.style.width = px(p.w);
          art.style.height = px(p.h);
          for (const x of discs) {
            const d = x.d, k = x.b.style;
            k.left = px(d.x);
            k.top = px(d.y);
            if (d.n === null) {                        // an axis word: a box around the art's own word
              k.width = (Math.round(d.w * s) + 14) + "px";
              k.height = (Math.round(d.h * s) + 12) + "px";
            } else {                                   // the page's mark covers the art's own, in its shape
              const side = (v, min) => Math.max(min, Math.round(v * s) + 2);
              const w = d.box ? side(d.w, RIG_BOX_MIN) : side(Math.max(d.w, d.h), RIG_DISC_MIN);
              const hh = d.box ? side(d.h, RIG_BOX_MIN) : w;
              k.width = w + "px";
              k.height = hh + "px";
              k.fontSize = Math.max(18, Math.round(Math.min(w, hh) * 0.58)) + "px";
            }
          }
          art.dataset.scale = s.toFixed(3);
        };
        let seen = "";
        fitWatch = new ResizeObserver(() => {          // the region's size, not what fit() itself moves
          const size = wrap.clientWidth + "x" + wrap.clientHeight;
          if (size !== seen) { seen = size; fit(); }
        });
        fitWatch.observe(wrap);
      }
      wrap.appendChild(pane);
      return wrap;
    }

    function rigNotes(p, cls) {
      return h("aside", cls, p.notes.map((x) => h("p", "", x)));
    }

    /* "More below" while rows are out of sight. The notes under the rows are shown when they fit
       and left out when they do not: they never push a row out of view. */
    function more(scroll, pane, notes) {
      const tag = h("p", "rows__more", icon("down"), "More below");
      tag.hidden = true;
      const upd = () => {
        if (notes) {
          notes.hidden = false;
          notes.hidden = scroll.scrollHeight > scroll.clientHeight + 1;
        }
        tag.hidden = scroll.scrollTop + scroll.clientHeight >= scroll.scrollHeight - 6;
      };
      scroll.addEventListener("scroll", upd, { passive: true });
      if (moreWatch) moreWatch.disconnect();
      moreWatch = new ResizeObserver(upd);
      moreWatch.observe(pane);
      if (scroll.firstElementChild) moreWatch.observe(scroll.firstElementChild);
      return tag;
    }

    // ---- Find: the whole rig, narrowed by the filter and by what is typed
    let findInput = null;
    function drawFind(keep) {
      let wrap = keep ? body.querySelector(".find") : null;
      let list;
      if (wrap) {
        list = wrap.querySelector(".find__list");
        list.textContent = "";
      } else {
        wrap = h("div", "find");
        const bar = h("div", "find__bar");
        if (RIG_FIND_BOX) {
          findInput = h("input", "find__in");
          findInput.type = "search";
          findInput.placeholder = "A number or a word";
          findInput.autocomplete = "off";
          findInput.spellcheck = false;
          findInput.maxLength = 60;
          findInput.setAttribute("aria-label", "Find a control");
          findInput.value = st.q;
          findInput.addEventListener("input", () => change({ q: findInput.value, sel: null }, true));
          findInput.addEventListener("keydown", (e) => {
            if (e.key === "Escape" && findInput.value) { findInput.value = ""; change({ q: "", sel: null }, true); }
          });
          bar.appendChild(h("label", "find__box", icon("find"), findInput));
        }
        bar.append(h("span", "cap find__count", ""), h("span", "find__hint", "Click a row to see it on its diagram"));
        const pane = h("div", "rows");
        const scroll = h("div", "rows__scroll");
        list = h("div", "find__list");
        scroll.appendChild(list);
        pane.append(scroll, more(scroll, pane, null));
        wrap.append(bar, pane);
      }
      const q = st.q.trim();
      const hits = rigSearch(M.rows, q, M);
      const section = (title, rows, isLead) => {
        if (!rows.length) return;
        if (title) list.appendChild(h("h3", "cap find__sec" + (isLead ? " find__sec--lead" : ""), title));
        for (const p of M.pages) {
          const mine = rows.filter((r) => r.page === p);
          if (!mine.length) continue;
          list.appendChild(h("section", "fg", h("h4", "cap fg__k", p.devName + " · " + p.title), rigList(mine, st.mode, M, null, !!q)));
        }
      };
      if (RIG_FIND_LEAD && st.mode !== "all") {
        const first = hits.filter((r) => rigLeads(r, st.mode, M));
        const title = st.mode === "flight" ? "Jobs of missile and scan mode" : "Changes in " + st.mode + " mode";
        section(title + " · " + first.length, first, true);
        section(first.length ? "Everything else" : null, hits.filter((r) => first.indexOf(r) < 0), false);
      } else {
        section(null, hits, false);
      }
      if (!hits.length) list.appendChild(h("p", "find__none", "Nothing on the rig matches “" + q + "”"));
      wrap.querySelector(".find__count").textContent = q ? hits.length + " of " + M.total : M.total + " controls";
      return wrap;
    }

    let drawnAt = 0;
    function draw(keepFind) {
      drawnAt = Date.now();
      if (fitWatch) { fitWatch.disconnect(); fitWatch = null; }
      drawHead();
      root.dataset.page = st.page === "find" ? "find" : "part";
      root.dataset.mode = st.mode;
      if (st.page === "find") {
        const page = drawFind(keepFind);
        if (!page.isConnected) { body.textContent = ""; body.appendChild(page); }
      } else {
        const p = M.pages.find((x) => x.id === st.page) || M.pages[0];
        st.page = p.id;
        body.textContent = "";
        body.appendChild(drawPage(p));
      }
      const sel = st.sel && body.querySelector(".rr--sel");
      if (sel) {                                       // the opened row in sight, without moving the page
        const sc = sel.closest(".rows__scroll");
        if (sc) {
          const z = zoom(), a = sel.getBoundingClientRect(), b = sc.getBoundingClientRect();
          if (a.bottom > b.bottom) sc.scrollTop += Math.min(a.bottom - b.bottom, a.top - b.top) / z;
          else if (a.top < b.top) sc.scrollTop -= (b.top - a.top) / z;
        }
      }
      const was = hot;
      hot = null;
      setHot(was);
    }

    /* Pointing at a row or at a number marks both, with no redraw. */
    function setHot(key) {
      if (key === hot) return;
      for (const n of body.querySelectorAll(".is-hot")) n.classList.remove("is-hot");
      hot = key;
      if (!key) return;
      for (const n of body.querySelectorAll(".rr, .dn")) if (n.dataset.key === key) n.classList.add("is-hot");
    }
    body.addEventListener("mouseover", (e) => {
      const n = e.target.closest(".rr, .dn");
      setHot(n ? n.dataset.key : null);
    });
    body.addEventListener("mouseleave", () => setHot(null));

    /* A click on a number or a row opens the row (its job in every mode), a second one closes it.
       On Find it opens the row's own page with the row open. */
    body.addEventListener("click", (e) => {
      const n = e.target.closest(".rr, .dn");
      const r = n && rowById.get(n.dataset.key);
      if (!r || notTaken(e, drawnAt)) return;           // a double click, or a row that just slid under the pointer
      if (st.page === "find") change({ page: r.page.id, sel: r.id });
      else change({ sel: st.sel === r.id ? null : r.id });
    });

    draw(false);
    return {
      set: (patch) => {
        if (patch.mode && RIG_FILTERS.some((f) => f[0] === patch.mode) && patch.mode !== st.mode) change({ mode: patch.mode }, true);
      },
      // for the page's own tests: what was read, and what is shown (a copy; nothing here changes anything)
      summary: () => ({
        total: M.total, lost: M.lost, state: Object.assign({}, st),
        pages: M.pages.map((p) => ({ id: p.id, device: p.device, rows: p.rows.map((r) => r.id), axes: p.axes.map((r) => r.id),
                                     discs: p.rows.concat(p.axes).reduce((n, r) => n + r.discs.length, 0) })),
      }),
    };
  }

  const RENDERERS = {
    now: vNow, travel: vTravel, mining: vMining, salvage: vSalvage, combat: vCombat, cargo: vCargo,
    mission: vMission, refinery: vRefinery, selling: vSelling, preflight: vPreflight, idle: vIdle,
    reference: vReference,
  };

  // ---------------------------------------------------------------- the feed and the plan notice

  function renderFeed(lines) {
    const want = lines.filter((x) => SHOW_MINOR || x.level !== "minor").reverse();   // newest first
    const keep = new Set(want.map((x) => x.id));
    for (const [id, item] of feedItems) {
      if (!keep.has(id)) { item.li.remove(); feedItems.delete(id); }
    }
    let prev = null;
    for (const line of want) {
      let item = feedItems.get(line.id);
      if (!item) {
        const li = h("li", "ev");
        const time = h("time", "num");
        const text = h("span");
        li.append(time, icon("dot"), text);
        item = { li: li, rev: -1, time: time, text: text };
        feedItems.set(line.id, item);
      }
      if (item.rev !== line.rev) {
        item.rev = line.rev;
        const tone = line.level === "alert" ? " ev--bad" : OK_KINDS.has(line.kind) ? " ev--ok" : "";
        setClass(item.li, "ev" + tone);
        const ic = icon(line.level === "alert" ? "stop" : ICONS[line.kind] || "dot");
        item.li.replaceChild(ic, item.li.children[1]);
        setText(item.time, timeText(parseIso(line.t)));
        setText(item.text, line.text);
      }
      const at = prev ? prev.nextSibling : ui.feedList.firstChild;
      if (at !== item.li) ui.feedList.insertBefore(item.li, at);
      prev = item.li;
    }
    show(ui.feedEmpty, want.length === 0);
  }

  function renderPlanNote(b) {
    const note = b && b.plan && b.plan.notice;
    show(ui.planNote, !!note);
    if (note) {
      setText(ui.planNoteT, note);
      ui.planNote.title = note;
    }
  }

  // ---------------------------------------------------------------- the desk panel

  function buildPanel() {
    for (const [name, label, ic] of VIEW_LIST) {
      if (name === "reference") continue;
      const btn = h("button", "pick", icon(ic), h("span", "pick__t", label), h("span", "pick__auto", "auto"));
      btn.type = "button";
      btn.dataset.view = name;
      btn.setAttribute("aria-pressed", "false");
      btn.addEventListener("click", (e) => {
        if (btn.getAttribute("aria-pressed") === "true") { if (e.detail < 2) closePanel(); return; }
        change("/api/view", { view: name }, btn, "The view", closePanel, e);
      });
      ui.picks.appendChild(btn);
    }
    for (const mins of QUICK_MINUTES) {
      const btn = h("button", "qmin", icon("plus"), mins < 60 ? mins + " min" : (mins / 60) + " h");
      btn.type = "button";
      btn.addEventListener("click", (e) => {
        const label = ui.qlabel.value.trim() || QUICK_LABEL;
        change("/api/timers/add", { label: label.slice(0, 60), minutes: mins }, btn, "The timer", () => { ui.qlabel.value = ""; }, e);
      });
      ui.qmins.appendChild(btn);
    }
  }

  function renderPanel(b) {
    if (!b) return;
    const v = b.view;
    const picked = v.picked;
    for (const btn of ui.picks.children) {
      const name = btn.dataset.view;
      btn.setAttribute("aria-pressed", String(name === v.name));
      btn.classList.toggle("pick--auto", name === v.auto);
    }
    setText(ui.panelAuto, "Live: " + (VIEW_LABEL[v.auto] || v.auto));
    ui.panelAuto.title = v.why || "";
    show(ui.panelLive, !!picked);
    const quick = (b.timers || []).filter((x) => x.source === "quick");
    const key = JSON.stringify(quick);
    if (ui.qlist.dataset.key !== key) {
      ui.qlist.dataset.key = key;
      ui.qlist.textContent = "";
      qlistAt = Date.now();
      lives.panel = [];
      for (const tm of quick) {
        const del = h("button", "qdel", icon("x"), h("span", "sw__sr", "Remove"));
        del.type = "button";
        del.title = "Remove this timer";
        del.addEventListener("click", (e) => { if (!notTaken(e, qlistAt)) change("/api/timers/remove", { id: tm.id }, del, "The timer", null, e); });
        ui.qlist.appendChild(h("li", "qrow qrow--" + tm.state, t("b", "qrow__name", tm.label),
          tm.state === "running" ? timerFig(tm, "qrow__fig", lives.panel) : t("span", "qrow__state", tm.text), del));
      }
    }
    show(ui.qnone, quick.length === 0);
  }

  /* The page's own zoom (style.css zooms a very large window): positions measured on the screen
     are divided by it before they are set as lengths. */
  function zoom() {
    const z = parseFloat(getComputedStyle(document.documentElement).zoom);
    return z > 0 ? z : 1;
  }
  function openPanel() {
    const r = ui.swMore.getBoundingClientRect(), z = zoom();
    const vw = document.documentElement.clientWidth;
    ui.panel.style.setProperty("--top", Math.round(r.bottom / z + 6) + "px");
    ui.panel.style.setProperty("--right", Math.max(8, Math.round((vw - r.right) / z)) + "px");
    show(ui.panel, true);
    ui.swMore.setAttribute("aria-expanded", "true");
  }
  function closePanel() {
    show(ui.panel, false);
    ui.swMore.setAttribute("aria-expanded", "false");
  }

  function toast(text) {
    const r = ui.swMore.getBoundingClientRect(), z = zoom();
    ui.toast.style.setProperty("--right", Math.max(8, Math.round((document.documentElement.clientWidth - r.right) / z)) + "px");
    ui.toast.textContent = "";
    ui.toast.append(icon("warn"), h("span", "", text));
    show(ui.toast, true);
    toastUntil = Date.now() + TOAST_SECONDS * 1000;
  }
  function hideToast() {
    toastUntil = 0;
    show(ui.toast, false);
  }

  /* A change through the service. Nothing on the page changes until the next message carries
     it; a refusal, or no answer at all, is said in the toast. The controls stay busy until a
     message has redrawn what the change moved (CHANGE_HOLD_MS at most), so a second click lands
     on what the user then sees; the second click of a double click (`detail` 2) is ignored. */
  async function change(path, body, btn, what, onOk, ev) {
    if (busy || (ev && ev.detail > 1)) return;
    busy = true;
    if (btn) btn.setAttribute("aria-busy", "true");
    const sentAt = Date.now();
    let taken = false;
    try {
      const res = await request(path, body);
      const a = res.answer;
      if (a && a.ok === true) {
        hideToast();
        taken = true;
        if (onOk) onOk(a);
      } else {
        toast(refusal(res.status, a, what));
      }
    } catch (err) {
      toast(err && err.name === "TimeoutError"
        ? "Not taken: the dashboard service did not answer within " + REQUEST_SECONDS + " s. " + what + " may be unchanged."
        : "Not taken: the dashboard service did not answer. " + what + " is unchanged.");
    } finally {
      if (taken) holdUntilRedrawn(btn, sentAt);
      else releaseControls(btn);
    }
  }
  let held = null;                    // {btn, timer}: a change answered, waiting for its message
  let lastRenderAt = 0;
  function holdUntilRedrawn(btn, sentAt) {
    // the message may have come before the answer: then the page shows it already
    const wait = lastRenderAt >= sentAt ? MOVED_MS : CHANGE_HOLD_MS;
    held = { btn: btn, timer: setTimeout(() => { if (held) releaseControls(held.btn); }, wait) };
  }
  function releaseControls(btn) {
    if (held) { clearTimeout(held.timer); held = null; }
    busy = false;
    if (btn) btn.removeAttribute("aria-busy");
  }
  function afterRedraw() {            // a message was drawn: a held change is shown, after a moment to settle
    lastRenderAt = Date.now();
    if (held) {
      clearTimeout(held.timer);
      const b = held.btn;
      held.timer = setTimeout(() => releaseControls(b), MOVED_MS);
    }
  }
  /* A pointer click that is not taken: the second of a double click, or one at the place of the
     click before it less than MOVED_MS after the list under it was redrawn (the pointer did not
     move: what is under it slid there). A click from the keyboard (`detail` 0) is always taken. */
  const moved = (at) => Date.now() - at < MOVED_MS;
  let clickPrev = null, clickNow = null;
  document.addEventListener("click", (e) => {
    if (e.detail >= 1) { clickPrev = clickNow; clickNow = [e.clientX, e.clientY]; }
  }, true);
  function notTaken(e, at) {
    if (!e || e.detail === 0) return false;
    if (e.detail > 1) return true;
    return moved(at) && !!clickPrev && Math.abs(clickNow[0] - clickPrev[0]) < 6 && Math.abs(clickNow[1] - clickPrev[1]) < 6;
  }
  function refusal(status, a, what) {
    const why = a && typeof a.error === "string" ? a.error : "";
    if (status === 503) return "Not taken: the service is busy reading the game log. Try again in a moment.";
    if (status === 403) return "Not taken: this page is out of date. Reload it.";
    if (status === 400) return "Not taken: " + (why || "the service refused it") + ".";
    return "Not taken (" + (status || "no answer") + ")" + (why ? ": " + why : "") + ". " + what + " is unchanged.";
  }

  function wire() {
    buildPanel();
    ui.app.dataset.rigFeed = RIG_FEED_LINES;
    ui.swLive.addEventListener("click", (e) => {
      if (ui.swLive.getAttribute("aria-pressed") === "true") return;
      change("/api/view/live", {}, ui.swLive, "The view", null, e);
    });
    ui.swRig.addEventListener("click", (e) => {
      if (ui.swRig.getAttribute("aria-pressed") === "true") return;
      change("/api/view", { view: "reference" }, ui.swRig, "The view", closePanel, e);
    });
    ui.swMore.addEventListener("click", (e) => { if (e.detail > 1) return; if (ui.panel.hidden) openPanel(); else closePanel(); });
    ui.pickbarLive.addEventListener("click", (e) => change("/api/view/live", {}, ui.pickbarLive, "The view", null, e));
    ui.panelLive.addEventListener("click", (e) => change("/api/view/live", {}, ui.panelLive, "The view", closePanel, e));
    document.addEventListener("pointerdown", (e) => {
      if (!ui.panel.hidden && !ui.panel.contains(e.target) && !ui.swMore.contains(e.target)) closePanel();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { closePanel(); hideToast(); }
    });
    ui.toast.addEventListener("click", hideToast);
    window.addEventListener("resize", () => { if (!ui.panel.hidden) openPanel(); });
  }

  // ---------------------------------------------------------------- requests

  /* A changing request: the token in its header, a JSON body. Resolves to {status, answer};
     rejects only when no answer came. */
  async function request(path, body) {
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-SCDash-Token": TOKEN },
      body: JSON.stringify(body || {}),
      cache: "no-store",
      signal: AbortSignal.timeout(REQUEST_SECONDS * 1000),
    });
    let answer = null;
    try { answer = await r.json(); } catch (err) { answer = null; }
    return { status: r.status, answer: answer };
  }
  /* The documented hook: resolves to the parsed answer whatever the status. */
  async function post(path, body) {
    const res = await request(path, body);
    if (res.answer === null) throw new Error("no JSON answer (" + res.status + ")");
    return res.answer;
  }
  /* A private stream (a route behind the server's PRIVATE guard, such as stage 4b's terminal
     output): fetch() sends the token header and the browser's Sec-Fetch-Site, which an
     EventSource cannot. The response is close-delimited HTTP/1.0 in the event-stream format;
     each `data:` line goes to onData(text, event), the service's keepalives excepted.
     Reconnects by itself after `retryMs` (or the
     server's `retry:`) until the returned function is called. */
  function openPrivateStream(path, onData, retryMs) {
    let stopped = false, controller = null, retry = retryMs || 3000;
    async function run() {
      while (!stopped) {
        controller = new AbortController();
        try {
          const r = await fetch(path, { headers: { "X-SCDash-Token": TOKEN }, cache: "no-store",
                                        signal: controller.signal });
          if (r.ok && r.body) {
            const reader = r.body.getReader(), dec = new TextDecoder();
            let buf = "";
            for (;;) {
              const { value, done } = await reader.read();
              if (done) break;
              buf += dec.decode(value, { stream: true });
              let cutAt;
              while ((cutAt = buf.indexOf("\n\n")) >= 0) {
                const block = buf.slice(0, cutAt);
                buf = buf.slice(cutAt + 2);
                let event = "message";
                const data = [];
                for (const line of block.split("\n")) {
                  if (line.startsWith("data: ")) data.push(line.slice(6));
                  else if (line.startsWith("event: ")) event = line.slice(7);
                  else if (line.startsWith("retry: ")) retry = parseInt(line.slice(7), 10) || retry;
                }
                if (data.length && event !== "keepalive") onData(data.join("\n"), event);
              }
            }
          }
        } catch (err) { /* dropped or aborted: try again below */ }
        if (!stopped) await new Promise((res) => setTimeout(res, retry));
      }
    }
    run();
    return function stop() { stopped = true; if (controller) controller.abort(); };
  }

  // For the page's own tests: the names it can draw. Not a way in: nothing here changes anything.
  window.scdash = Object.freeze({ post: post, openPrivateStream: openPrivateStream, views: Object.freeze(Object.keys(RENDERERS)),
                                  rig: () => (rig.api ? rig.api.summary() : null) });

  wire();
  connect();
  tick();
})();
