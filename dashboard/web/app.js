/* The dashboard page (stage 2): the status strip, the alerts, a "Now" placeholder and the event
   feed, fed by one event stream from the local service. Look: direction B, "Avionics".

   - One event stream (/api/stream). The browser reconnects by itself after a network error,
     using the server's `retry:` value; after an HTTP error (the page cap, a restart) it gives up,
     so this script opens a new one a few seconds later.
   - One one-second timer for the clocks. Each tick computes the time from the system clock (and,
     in a replay, from the replay clock's anchor), so a page that was paused is right again at
     once. It also raises the banner when the stream has been gone for two seconds.
   - Only what changed is redrawn: text and classes are written only when they differ, feed
     lines are kept by id and rewritten only when their `rev` changes, and the alerts are rebuilt
     only when their content changes.

   Stage 3 replaces renderView() with the views and computes the alerts in the service; `post()`
   is how its changing requests carry the token (the browser adds the Origin by itself). */
"use strict";

(function () {
  const TOKEN = document.querySelector('meta[name="scdash-token"]').getAttribute("content");
  const SHOW_MINOR = false;            // minor lines (zones, menus, storage) stay out of the page feed
  const $ = (id) => document.getElementById(id);
  const ui = {
    body: document.body,
    offline: $("offline"), offlineDetail: $("offline-detail"),
    clock: $("s-clock"), date: $("s-date"), replay: $("s-replay"),
    stateBox: $("b-state"), state: $("s-state"),
    sticksBox: $("b-sticks"), sticks: $("s-sticks"), sticksNote: $("s-sticks-note"),
    sessionK: $("s-session-k"), session: $("s-session"),
    loc: $("s-loc"), ship: $("s-ship"),
    alerts: $("alerts"),
    vKicker: $("v-kicker"), vTitle: $("v-title"), vLine1: $("v-line1"), vLine2: $("v-line2"), vFacts: $("v-facts"),
    feed: $("feed-list"), feedEmpty: $("feed-empty"),
  };

  let payload = null;                 // the last state the service sent
  let anchor = { rate: 1, real: 0, virtual: 0 };   // live: the system clock itself
  let sessionEnd = null;              // ms, once the session is over
  let source = null;                  // the EventSource
  let lastMessageAt = null;           // Date.now() of the last state
  let lostAt = Date.now();            // when the stream was lost (now: not connected yet)
  let reconnectTimer = null;
  // Which instance served this page (pid/start, from the HTML): compared from the first message on.
  const servedBy = document.querySelector('meta[name="scdash-instance"]').getAttribute("content");
  let serviceId = /^\d+\//.test(servedBy) ? servedBy : null;
  const feedItems = new Map();        // line id -> {li, rev, ...}

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
  function nowMs() {
    return anchor.virtual + (Date.now() - anchor.real) * anchor.rate;
  }
  function parseIso(text) {
    return text ? Date.parse(text) : null;
  }
  const TIME = new Intl.DateTimeFormat("en-US", { hour: "numeric", minute: "2-digit" });
  const DATE = new Intl.DateTimeFormat("en-US", { weekday: "short", month: "short", day: "numeric" });
  const MONTH_DAY = new Intl.DateTimeFormat("en-US", { month: "short", day: "numeric" });
  function hm(seconds) {
    const s = Math.max(0, Math.floor(seconds));
    return Math.floor(s / 3600) + ":" + String(Math.floor((s % 3600) / 60)).padStart(2, "0");
  }
  function placeName(p, short) {
    if (!p) return null;
    return (short ? p.short : p.name) || p.name || p.code;
  }
  function icon(name, extra) {
    const NS = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", "i" + (extra ? " " + extra : ""));
    const use = document.createElementNS(NS, "use");
    use.setAttribute("href", "#i-" + name);
    svg.appendChild(use);
    return svg;
  }
  function el(tag, cls, text) {
    const n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text !== undefined) n.textContent = text;
    return n;
  }

  // ---------------------------------------------------------------- the clock (one timer)

  function tick() {
    renderClocks();
    if (lostAt !== null && Date.now() - lostAt > 2000) showOffline(true);
    setTimeout(tick, 1000 - (Date.now() % 1000) + 5);
  }

  function renderClocks() {
    const now = new Date(nowMs());
    setText(ui.clock, TIME.format(now));
    setText(ui.date, DATE.format(now));
    const s = payload && payload.state.session;
    const start = s ? parseIso(s.start) : null;
    if (start === null) {
      setText(ui.session, "–");
    } else if (payload.service.game_running) {
      setText(ui.session, hm(((sessionEnd !== null ? sessionEnd : now.getTime()) - start) / 1000));
    } else {
      setText(ui.session, MONTH_DAY.format(new Date(start)));
    }
  }

  // ---------------------------------------------------------------- the stream

  function connect() {
    reconnectTimer = null;
    if (source) source.close();
    source = new EventSource("/api/stream");
    source.addEventListener("state", (e) => {
      let p;
      try { p = JSON.parse(e.data); } catch (err) { return; }
      lastMessageAt = Date.now();
      lostAt = null;
      showOffline(false);
      render(p);
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
    if (ui.offline.hidden === on) ui.offline.hidden = !on;
    ui.body.classList.toggle("is-offline", on);
  }

  // ---------------------------------------------------------------- rendering

  function render(p) {
    // A restarted service has a new token: this page's would be refused. Load the page again.
    const id = p.service.pid + "/" + p.service.started;
    if (serviceId !== null && id !== serviceId) {
      if (source) source.close();
      window.location.reload();
      return;
    }
    serviceId = id;
    payload = p;
    anchor = { rate: p.clock.rate, real: p.clock.real, virtual: p.clock.virtual };
    sessionEnd = p.clock.session_end;
    renderStrip(p);
    renderAlerts(p);
    renderView(p);
    renderFeed(p.state.feed || []);
    renderClocks();
  }

  function inQuantum(st) {
    const q = st.quantum;
    return Boolean(q && !q.arrived && !q.closed && q.target);
  }

  function stateWord(p) {
    const s = p.state.session, svc = p.service, h = p.state.health && p.state.health.status;
    if (!svc.game_running) {
      if (svc.mode === "replay" && svc.replay && !svc.replay.done) return ["Starting", ""];
      return ["No game running", "state--off"];
    }
    if (p.state.preflight.ok === false) return ["Preflight failed", "bad"];
    if (h === "dead") return ["Dead", "bad"];
    if (h === "downed") return ["Downed", "bad"];
    if (s.game === "in_game") return inQuantum(p.state) ? ["Quantum", "state--quantum"] : ["In game", "state--live"];
    if (s.game === "menu") return ["Main menu", ""];
    if (s.game === "ended") return ["Quitting", "state--off"];
    return ["Starting", ""];
  }

  function locationText(st) {
    if (inQuantum(st)) return "To " + placeName(st.quantum.target, false);
    const loc = st.location;
    if (loc && !loc.left) return placeName(loc, false);
    if (st.body) return "Near " + placeName(st.body, false);
    if (loc) return "Left " + placeName(loc, false);
    return "–";
  }

  function renderStrip(p) {
    const st = p.state, svc = p.service;
    const replay = svc.mode === "replay" && svc.replay;
    if (replay) setText(ui.replay, "Replay " + svc.replay.speed + "×" + (svc.replay.done ? ", ended" : ""));
    if (ui.replay.hidden === !!replay) ui.replay.hidden = !replay;

    const [word, tone] = stateWord(p);
    setText(ui.state, word);
    setClass(ui.state, "state" + (tone && tone !== "bad" ? " " + tone : ""));
    setClass(ui.stateBox, "si si--state" + (tone === "bad" ? " si--bad" : ""));

    const ok = st.preflight.ok;
    const differs = ok === true && st.preflight.order === "differs";
    if (ui.sticksNote.hidden === differs) ui.sticksNote.hidden = !differs;
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

    setText(ui.sessionK, svc.game_running ? "Session" : "Last played");
    setText(ui.loc, st.session.id ? locationText(st) : "–");
    const sh = st.ship;
    setText(ui.ship, !sh ? "No ship" : (sh.name || sh.class || "A ship") + (sh.aboard === false ? " (not aboard)" : ""));
  }

  function renderAlerts(p) {
    const st = p.state, items = [];
    if (st.preflight.ok === false) items.push(preflightAlert(st.preflight));
    const h = st.health && st.health.status;
    if (p.service.game_running && (h === "downed" || h === "dead")) {
      items.push({ tone: "bad", icon: "stop", kind: h === "dead" ? "Dead" : "Downed",
                   title: h === "dead" ? "You died" : "You are incapacitated", text: "", todo: "" });
    }
    if (p.flags && p.flags.hangar_stuck) {
      items.push({ tone: "warn", icon: "warn", kind: "Attention", title: "Hangar queue stuck",
                   text: "Waiting past twice its estimate.", todo: "Cancel at the hangar terminal and request again" });
    }
    for (const a of st.alerts || []) {               // stage 3 fills these
      items.push({ tone: a.level === "alert" ? "bad" : a.level || "warn", icon: a.level === "alert" ? "stop" : "warn",
                   kind: a.kind || "Attention", title: a.title || a.text || "", text: a.detail || "", todo: a.todo || "" });
    }
    const key = JSON.stringify(items);
    if (ui.alerts.dataset.key === key) return;
    ui.alerts.dataset.key = key;
    ui.alerts.textContent = "";
    for (const a of items) {
      const box = el("div", "alert alert--" + a.tone);
      box.setAttribute("role", "alert");
      box.appendChild(icon(a.icon, "alert__icon"));
      const body = el("div", "alert__body");
      body.append(el("span", "alert__kind", a.kind), el("b", "alert__title", a.title));
      if (a.text) body.appendChild(el("span", "alert__text", a.text));
      box.appendChild(body);
      box.appendChild(el("p", "alert__do", a.todo));
      ui.alerts.appendChild(box);
    }
  }

  /* The red alert for a missing device. The check fails only when the AB6 base or the MTQ
     throttle is missing from the joystick list; a different order is a note, not an alert. */
  function preflightAlert(pf) {
    const missing = (pf.missing || []).join(" ");
    const ab6 = /AB6/i.test(missing), mtq = /MTQ/i.test(missing);
    let title, todo;
    if (ab6 && mtq) {
      title = "Stick base and throttle not detected";
      todo = "Quit the game. Switch on the AB6 base and check the MTQ's cable; when MOZA Cockpit shows both, start the game again";
    } else if (mtq) {
      title = "Throttle not detected";
      todo = "Quit the game. Check the MTQ throttle's USB cable; when MOZA Cockpit shows it, start the game again";
    } else {
      title = "Stick base not detected";
      todo = "Quit the game. Switch on the AB6 base; when MOZA Cockpit shows it, start the game again";
    }
    return { tone: "bad", icon: "stop", kind: "Preflight failed", title: title, text: pf.text || "", todo: todo };
  }

  function renderView(p) {
    const st = p.state, s = st.session, svc = p.service;
    let title, idle = false, line1 = "", line2 = "", facts = [];
    if (!s.id) {
      title = svc.log_found ? "Waiting for the game" : "No game log found";
      idle = true;
    } else if (!svc.game_running) {
      idle = true;
      title = "Nothing running";
      const start = parseIso(s.start), end = sessionEnd;
      if (start !== null) {
        line1 = "Last session " + DATE.format(new Date(start)) + " · " + TIME.format(new Date(start)) +
                (end ? " to " + TIME.format(new Date(end)) : "");
      }
      line2 = s.ended ? "" : "It ended without a quit line: the game crashed or was closed by force.";
      const places = new Set((st.places || []).map((x) => x.place || x.code));
      if (start !== null && end) facts.push([hm((end - start) / 1000), "played"]);
      facts.push([String(places.size), places.size === 1 ? "place" : "places"]);
      facts.push([String((st.jumps || []).length), "quantum jumps"]);
      facts.push([String((st.deaths || []).length), "deaths"]);
    } else if (s.game === "in_game") {
      if (inQuantum(st)) title = "Quantum to " + placeName(st.quantum.target, false);
      else if (st.location && !st.location.left) title = placeName(st.location, false);
      else title = st.body ? "Near " + placeName(st.body, false) : "In flight";
      const bits = [];
      if (st.ship && st.ship.aboard !== false) bits.push(st.ship.name || st.ship.class);
      if (st.body && title.indexOf(placeName(st.body, false)) < 0) bits.push("near " + placeName(st.body, false));
      line1 = bits.join(" · ");
      const z = st.zone || {}, zb = [];
      if (z.jurisdiction) zb.push(z.jurisdiction + " jurisdiction");
      if (z.armistice) zb.push("armistice zone");
      if (z.monitored) zb.push("monitored space");
      line2 = zb.join(" · ");
    } else {
      title = s.game === "menu" ? "At the main menu" : "The game is starting";
      line1 = st.preflight.ok === true ? "Joysticks: " + st.preflight.text : "";
    }
    setText(ui.vTitle, title);
    setClass(ui.vTitle, "now__title" + (idle ? " now__title--idle" : ""));
    setText(ui.vLine1, line1);
    setText(ui.vLine2, line2);
    const key = JSON.stringify(facts);
    if (ui.vFacts.dataset.key !== key) {
      ui.vFacts.dataset.key = key;
      ui.vFacts.textContent = "";
      for (const [v, k] of facts) {
        const f = el("div", "fact");
        f.append(el("b", "fact__v num", v), el("span", "fact__k", k));
        ui.vFacts.appendChild(f);
      }
    }
  }

  // ---------------------------------------------------------------- the feed

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
        const li = el("li", "ev");
        const time = el("time", "num");
        const text = el("span");
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
        setText(item.time, TIME.format(new Date(parseIso(line.t))));
        setText(item.text, line.text);
      }
      const at = prev ? prev.nextSibling : ui.feed.firstChild;
      if (at !== item.li) ui.feed.insertBefore(item.li, at);
      prev = item.li;
    }
    const empty = want.length === 0;
    if (ui.feedEmpty.hidden === empty) ui.feedEmpty.hidden = !empty;
  }

  // ---------------------------------------------------------------- for later stages

  /* A changing request: the token in its header, a JSON body. */
  async function post(path, body) {
    const r = await fetch(path, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-SCDash-Token": TOKEN },
      body: JSON.stringify(body || {}),
      cache: "no-store",
    });
    return r.json();
  }
  /* A private stream (a route behind the server's PRIVATE guard, such as stage 4b's terminal
     output): fetch() sends the token header and the browser's Sec-Fetch-Site, which an
     EventSource cannot. The response is close-delimited HTTP/1.0 in the event-stream format;
     each `data:` line goes to onData(text, event). Reconnects by itself after `retryMs` (or the
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
              let cut;
              while ((cut = buf.indexOf("\n\n")) >= 0) {
                const block = buf.slice(0, cut);
                buf = buf.slice(cut + 2);
                let event = "message";
                const data = [];
                for (const line of block.split("\n")) {
                  if (line.startsWith("data: ")) data.push(line.slice(6));
                  else if (line.startsWith("event: ")) event = line.slice(7);
                  else if (line.startsWith("retry: ")) retry = parseInt(line.slice(7), 10) || retry;
                }
                if (data.length) onData(data.join("\n"), event);
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

  window.scdash = Object.freeze({ post: post, openPrivateStream: openPrivateStream });

  connect();
  tick();
})();
