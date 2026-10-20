// Argus — front end. Vanilla JS, no build step.
// Every value that comes from data or the model is inserted with textContent, never innerHTML.
(function () {
  "use strict";

  // ---------- small helpers ----------

  function h(tag, attrs, ...children) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v === null || v === undefined || v === false) continue;
      if (k === "class") el.className = v;
      else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (k === "text") el.textContent = v;
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const c of children.flat()) {
      if (c === null || c === undefined || c === false) continue;
      el.appendChild(typeof c === "string" || typeof c === "number" ? document.createTextNode(String(c)) : c);
    }
    return el;
  }

  // Icon markup is a fixed, trusted set of paths (never data).
  const ICONS = {
    ask: '<path d="M4 5h16v10H9l-5 4z"/>',
    shield: '<path d="M12 3l7 3v6c0 4.5-3 7.5-7 9-4-1.5-7-4.5-7-9V6z"/><path d="M9 12l2 2 4-4"/>',
    table: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 10h18M9 10v10"/>',
    chart: '<path d="M4 20V10M10 20V4M16 20v-7M22 20H2"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
    send: '<path d="M12 19V5M5 12l7-7 7 7"/>',
    check: '<path d="M5 12.5l4.5 4.5L19 7"/>',
    x: '<path d="M6 6l12 12M18 6L6 18"/>',
    info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    alert: '<path d="M12 3l9.5 17h-19z"/><path d="M12 10v4M12 17h.01"/>',
    ban: '<circle cx="12" cy="12" r="9"/><path d="M5.6 5.6l12.8 12.8"/>',
    copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3"/>',
    download: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
    chevron: '<path d="M9 6l6 6-6 6"/>',
    eye: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    db: '<ellipse cx="12" cy="6" rx="7" ry="3"/><path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/>',
    lock: '<rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V8a4 4 0 0 1 8 0v3"/>',
    target: '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="5"/><circle cx="12" cy="12" r="1"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    spark: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>',
  };
  function icon(name, size) {
    const s = size || 16;
    const el = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    el.setAttribute("width", s); el.setAttribute("height", s); el.setAttribute("viewBox", "0 0 24 24");
    el.setAttribute("fill", "none"); el.setAttribute("stroke", "currentColor");
    el.setAttribute("stroke-width", "2"); el.setAttribute("stroke-linecap", "round"); el.setAttribute("stroke-linejoin", "round");
    el.setAttribute("aria-hidden", "true");
    el.innerHTML = ICONS[name];
    return el;
  }

  async function api(path, body) {
    const res = await fetch(path, body === undefined ? {} : {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
    });
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail ? (typeof data.detail === "string" ? data.detail : "Invalid request") : `HTTP ${res.status}`);
    return data;
  }

  const store = {
    get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
    set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } },
  };

  const fmtMs = (ms) => (ms == null ? "" : ms < 1 ? "<1 ms" : ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(1)}s`);
  const fmtInt = (n) => new Intl.NumberFormat().format(n);
  // "2017-11-26T09:23:40.000" -> "2017-11-26 09:23:40"; midnight timestamps -> just the date
  const fmtDate = (v) => String(v).replace("T", " ").replace(/\.\d+$/, "").replace(/ 00:00:00$/, "");

  // ---------- SQL display ----------

  const KEYWORDS = new Set(("select from where group by order having limit join left right inner outer full cross on using as " +
    "and or not in is null case when then else end with distinct union all over partition desc asc between like " +
    "count sum avg min max cast date_trunc year month extract coalesce round filter interval true false").split(" "));

  function highlightSql(sql) {
    const frag = document.createDocumentFragment();
    const re = /(--[^\n]*)|('(?:[^']|'')*')|(\b\d+(?:\.\d+)?\b)|([A-Za-z_][A-Za-z0-9_]*)|(\s+|.)/g;
    let m;
    while ((m = re.exec(sql))) {
      const [tok, cm, str, num, word] = m;
      let cls = null;
      if (cm) cls = "cm"; else if (str) cls = "str"; else if (num) cls = "num";
      else if (word && KEYWORDS.has(word.toLowerCase())) cls = "kw";
      frag.appendChild(cls ? h("span", { class: cls, text: tok }) : document.createTextNode(tok));
    }
    return frag;
  }

  function sqlBlock(sql, opts) {
    opts = opts || {};
    const block = h("div", { class: "sql-block", "data-open": opts.open ? "true" : "false" });
    const toggle = h("button", { class: "sql-toggle", type: "button", "aria-expanded": opts.open ? "true" : "false" },
      icon("chevron", 14), opts.title || "SQL");
    toggle.addEventListener("click", () => {
      const open = block.dataset.open !== "true";
      block.dataset.open = String(open);
      toggle.setAttribute("aria-expanded", String(open));
    });
    const copy = h("button", { class: "btn ghost small", type: "button", "aria-label": "Copy SQL" }, icon("copy", 14), "Copy");
    copy.addEventListener("click", async () => {
      try { await navigator.clipboard.writeText(sql); copy.lastChild.textContent = "Copied"; } catch (e) { copy.lastChild.textContent = "Copy failed"; }
      setTimeout(() => { copy.lastChild.textContent = "Copy"; }, 1400);
    });
    block.append(
      h("div", { class: "sql-head" }, toggle, opts.note ? h("span", { class: "limit-note", text: opts.note }) : null,
        h("span", { class: "grow" }), copy),
      h("pre", { class: "sql-code" }, h("code", {}, highlightSql(sql))),
    );
    return block;
  }

  // ---------- results: table, chart, figure ----------

  function dataTable(result) {
    const thead = h("tr", {}, result.columns.map((c) => h("th", { class: c.kind === "number" ? "n" : "", text: c.name })));
    const body = result.rows.slice(0, 500).map((row) => h("tr", {}, row.map((v, i) => {
      const num = result.columns[i].kind === "number";
      if (v === null) return h("td", { class: `null ${num ? "n" : ""}`, text: "null" });
      if (result.columns[i].kind === "date") return h("td", { text: fmtDate(v) });
      return h("td", { class: num ? "n" : "", text: num ? Charts.fmt(v) : String(v) });
    })));
    const wrap = h("div", {}, h("div", { class: "table-wrap" }, h("table", { class: "data" }, h("thead", {}, thead), h("tbody", {}, body))));
    const notes = [];
    if (result.rows.length > 500) notes.push(`Showing the first 500 of ${fmtInt(result.row_count)} rows.`);
    if (result.truncated) notes.push(`The guard capped this result at ${fmtInt(state.status ? state.status.row_limit : 1000)} rows.`);
    if (notes.length) wrap.appendChild(h("div", { class: "table-note", text: notes.join(" ") }));
    return wrap;
  }

  function toCsv(result) {
    const esc = (v) => {
      if (v === null || v === undefined) return "";
      const s = String(v);
      return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
    };
    return [result.columns.map((c) => esc(c.name)).join(","), ...result.rows.map((r) => r.map(esc).join(","))].join("\n");
  }

  function downloadCsv(result, name) {
    const blob = new Blob([toCsv(result)], { type: "text/csv" });
    const a = h("a", { href: URL.createObjectURL(blob), download: `${name}.csv` });
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(a.href), 1000);
  }

  // Picks the right form for a result: a figure, a chart with a table tab, or a table alone.
  function resultView(result) {
    if (!result.rows.length) {
      return h("div", { class: "notice info" }, icon("info"), h("div", {}, "The query ran but returned no rows."));
    }
    const fig = Charts.figure(result);
    if (fig) return fig;
    const spec = Charts.series(result);
    if (!spec) return dataTable(result);

    const chartHost = h("div", { class: "chart" });
    Charts.chart(chartHost, spec);
    const tablePane = dataTable(result);
    tablePane.hidden = true;
    const chartTab = h("button", { class: "tab", type: "button", role: "tab", "aria-selected": "true", text: "Chart" });
    const tableTab = h("button", { class: "tab", type: "button", role: "tab", "aria-selected": "false", text: "Table" });
    const select = (showChart) => {
      chartHost.hidden = !showChart; tablePane.hidden = showChart;
      chartTab.setAttribute("aria-selected", String(showChart)); tableTab.setAttribute("aria-selected", String(!showChart));
    };
    chartTab.addEventListener("click", () => select(true));
    tableTab.addEventListener("click", () => select(false));
    return h("div", { style: "display:flex;flex-direction:column;gap:12px" },
      h("div", { class: "tabs", role: "tablist" }, chartTab, tableTab), chartHost, tablePane);
  }

  // ---------- state, theme, chrome ----------

  const state = { status: null, examples: null, schema: null, feed: [], view: "ask", busy: false };
  const main = document.getElementById("main");

  function applyThemeButton() {
    const btn = document.getElementById("theme-btn");
    const dark = document.documentElement.dataset.theme === "dark" ||
      (!document.documentElement.dataset.theme && matchMedia("(prefers-color-scheme: dark)").matches);
    btn.replaceChildren(icon(dark ? "sun" : "moon", 16));
    btn.onclick = () => {
      const next = dark ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem("nl2sql.theme", next); } catch (e) { /* ignore */ }
      applyThemeButton();
    };
  }

  function renderChrome() {
    document.getElementById("brand-mark").replaceChildren(icon("eye", 17));
    const labels = { ask: ["ask", "Ask"], guard: ["shield", "Guard lab"], schema: ["table", "Schema"], eval: ["chart", "Evaluation"] };
    for (const btn of document.querySelectorAll(".nav-item")) {
      const [ic, label] = labels[btn.dataset.view];
      btn.replaceChildren(icon(ic, 17), label);
      btn.onclick = () => { location.hash = btn.dataset.view; };
    }
    applyThemeButton();
    const s = state.status;
    if (!s) return;
    const dataChip = document.getElementById("data-chip");
    dataChip.hidden = false;
    if (s.data_source === "sample") {
      dataChip.className = "chip warning hide-sm";
      dataChip.replaceChildren(icon("alert", 14), "Sample data, not real");
    } else {
      dataChip.replaceChildren(icon("db", 14), h("strong", { text: "Olist" }),
        `${fmtInt(s.orders)} orders · ${s.data_start.slice(0, 4)}–${s.data_end.slice(0, 4)}`);
    }
    const modelChip = document.getElementById("model-chip");
    modelChip.hidden = false;
    modelChip.replaceChildren(h("span", { class: `dot ${s.key_configured ? "good" : "warning"}` }),
      h("strong", { text: s.provider_label }), s.key_configured ? s.model : "no API key");
    modelChip.title = s.key_configured ? `Model: ${s.model}${s.fallback ? ` · backup: ${s.fallback}` : ""}`
      : `Set ${s.key_env} in .env and restart the server`;
    document.getElementById("sidebar-foot").textContent = `Row limit ${fmtInt(s.row_limit)} · read-only`;
  }

  function renderHistory() {
    const list = store.get("nl2sql.history", []);
    const host = document.getElementById("history");
    if (!list.length) { host.replaceChildren(h("div", { class: "history-empty", text: "Questions you ask appear here." })); return; }
    host.replaceChildren(...list.map((q) => h("button", {
      class: "history-item", type: "button", title: q, text: q,
      onclick: () => { location.hash = "ask"; setTimeout(() => fillComposer(q), 0); },
    })));
  }

  function remember(q) {
    const list = store.get("nl2sql.history", []).filter((x) => x !== q);
    list.unshift(q);
    store.set("nl2sql.history", list.slice(0, 10));
    renderHistory();
  }

  // ---------- Ask ----------

  let composerInput, sendButton, feedHost;

  function fillComposer(q) {
    if (!composerInput) return;
    composerInput.value = q;
    composerInput.dispatchEvent(new Event("input"));
    composerInput.focus();
  }

  function renderAsk() {
    const s = state.status;
    composerInput = h("textarea", { rows: "1", placeholder: "Ask a question about orders, revenue, delivery, sellers…",
      "aria-label": "Your question", maxlength: "500" });
    sendButton = h("button", { class: "send-btn", type: "button", "aria-label": "Ask", disabled: true }, icon("send", 18));
    const sync = () => {
      composerInput.style.height = "auto";
      composerInput.style.height = `${Math.min(160, composerInput.scrollHeight)}px`;
      composerInput.style.overflowY = composerInput.scrollHeight > 160 ? "auto" : "hidden";
      sendButton.disabled = state.busy || composerInput.value.trim().length < 3;
    };
    composerInput.addEventListener("input", sync);
    composerInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); if (!sendButton.disabled) submit(); }
    });
    sendButton.addEventListener("click", submit);

    const examples = h("div", { class: "examples" }, (state.examples ? state.examples.questions : []).map((q) =>
      h("button", { class: "example", type: "button", text: q, onclick: () => fillComposer(q) })));

    const composer = h("div", { class: "composer-sticky" }, h("div", { class: "composer-box" }, composerInput, sendButton));
    feedHost = h("div", { class: "feed" });

    const view = h("div", { class: "view" });
    if (!state.feed.length) {
      view.appendChild(h("div", { class: "empty-hero" },
        h("h1", { text: "Ask your data a question" }),
        h("p", { text: s ? `Answers come from a SQL query over ${fmtInt(s.orders)} marketplace orders (${s.data_start} to ${s.data_end}). ` +
          "Every query is checked before it runs, and you can always see the SQL." : "" }),
        h("div", { class: "trust-row" },
          h("span", { class: "trust" }, icon("shield", 16), "Validated before it runs"),
          h("span", { class: "trust" }, icon("lock", 16), "Read-only database"),
          h("span", { class: "trust" }, icon("ban", 16), "Says no instead of guessing")),
      ));
    }
    if (s && !s.key_configured) {
      view.appendChild(h("div", { class: "notice warning", style: "margin-bottom:16px" }, icon("alert"),
        h("div", {}, h("strong", { text: "No API key yet. " }),
          `Questions need a ${s.provider_label} key: add ${s.key_env}=… to the .env file and restart the server. `,
          "The Guard lab, Schema and Evaluation pages work without one.")));
    }
    view.append(composer, examples, feedHost);
    main.replaceChildren(view);
    for (const item of state.feed) feedHost.appendChild(item.node);
    sync();
  }

  function stepChip(label, status, time) {
    const ic = status === "done" ? icon("check", 13) : status === "fail" ? icon("x", 13) :
      status === "active" ? h("span", { class: "spinner" }) : null;
    return h("span", { class: `step ${status}` }, ic, label, time ? h("span", { class: "t", text: time }) : null);
  }

  function pipeline(data) {
    const sep = () => h("span", { class: "step-sep", "aria-hidden": "true" }, icon("chevron", 12));
    if (!data) {
      return h("div", { class: "pipeline", "aria-live": "polite" }, stepChip("Writing SQL", "active"), sep(),
        stepChip("Validate", "skipped"), sep(), stepChip("Execute", "skipped"));
    }
    const t = data.timings || {};
    const st = data.stage;
    const write = st === "generation_error" ? stepChip("Write SQL", "fail") :
      stepChip(st === "cannot_answer" ? "Declined" : "Write SQL", "done", t.generate_s != null ? `${t.generate_s.toFixed(1)}s` : "");
    const validate = st === "blocked" ? stepChip("Validate", "fail", fmtMs(t.guard_ms)) :
      ["answered", "db_error"].includes(st) ? stepChip("Validate", "done", fmtMs(t.guard_ms)) : stepChip("Validate", "skipped");
    const execute = st === "answered" ? stepChip("Execute", "done", fmtMs(t.execute_ms)) :
      st === "db_error" ? stepChip("Execute", "fail") : stepChip("Execute", "skipped");
    return h("div", { class: "pipeline" }, write, sep(), validate, sep(), execute);
  }

  const STAGE_BADGE = {
    answered: ["good", "check", "Validated"],
    cannot_answer: ["info", "info", "Not answerable"],
    blocked: ["critical", "ban", "Blocked"],
    db_error: ["warning", "alert", "Query failed"],
    generation_error: ["critical", "alert", "Model error"],
  };

  function resultCard(question, data) {
    const card = h("article", { class: "card result" });
    const badge = data ? (() => { const [cls, ic, label] = STAGE_BADGE[data.stage]; return h("span", { class: `badge ${cls}` }, icon(ic, 12), label); })() : null;
    card.appendChild(h("div", { class: "result-head" }, h("h2", { class: "result-q", text: question }), badge));
    card.appendChild(pipeline(data));
    if (!data) return card;

    const body = h("div", { class: "result-body" });
    if (data.stage === "answered") {
      body.appendChild(resultView(data.result));
    } else if (data.stage === "cannot_answer") {
      body.appendChild(h("div", { class: "notice info" }, icon("info"),
        h("div", {}, h("strong", { text: "This data can't answer that. " }), data.error || "")));
    } else if (data.stage === "blocked") {
      body.appendChild(h("div", { class: "notice critical" }, icon("ban"),
        h("div", {}, h("strong", { text: "Blocked before execution. " }), data.error || "", " The query never reached the database.")));
    } else if (data.stage === "db_error") {
      body.appendChild(h("div", { class: "notice warning" }, icon("alert"),
        h("div", {}, h("strong", { text: "The database rejected the query. " }), data.error || "")));
    } else {
      body.appendChild(h("div", { class: "notice critical" }, icon("alert"), h("div", { text: data.error || "Something went wrong." })));
    }
    const sql = data.executed_sql || data.generated_sql;
    if (sql) {
      const limitAdded = data.executed_sql && data.generated_sql && !/\blimit\b/i.test(data.generated_sql);
      body.appendChild(sqlBlock(sql, {
        open: data.stage !== "answered",
        title: data.executed_sql ? "SQL that ran" : "SQL generated (not run)",
        note: limitAdded ? "LIMIT added by the guard" : null,
      }));
    }
    card.appendChild(body);

    const foot = h("div", { class: "result-foot" });
    if (data.model) foot.appendChild(h("span", { class: "meta" }, icon("spark", 13), data.model));
    if (data.fallback_from) {
      foot.appendChild(h("span", { class: "badge warning", title: "The primary model was busy, so the backup answered." },
        icon("alert", 12), `${data.fallback_from} busy, answered by backup`));
    }
    if (data.tokens) foot.appendChild(h("span", { class: "meta", text: `${fmtInt(data.tokens.input)} in · ${fmtInt(data.tokens.output)} out tokens` }));
    if (data.tables_used && data.tables_used.length) foot.appendChild(h("span", { class: "meta" }, icon("table", 13), data.tables_used.join(", ")));
    if (data.result) foot.appendChild(h("span", { class: "meta", text: `${fmtInt(data.result.row_count)} row${data.result.row_count === 1 ? "" : "s"}` }));
    foot.appendChild(h("span", { class: "grow" }));
    if (data.result && data.result.rows.length) {
      foot.appendChild(h("button", { class: "btn ghost small", type: "button",
        onclick: () => downloadCsv(data.result, "answer") }, icon("download", 14), "CSV"));
    }
    card.appendChild(foot);
    return card;
  }

  async function submit() {
    const question = composerInput.value.trim();
    if (question.length < 3 || state.busy) return;
    state.busy = true;
    sendButton.disabled = true;
    const item = { question, node: resultCard(question, null) };
    state.feed.unshift(item);
    const hero = main.querySelector(".empty-hero");
    if (hero) hero.remove();
    feedHost.prepend(item.node);
    composerInput.value = "";
    composerInput.dispatchEvent(new Event("input"));
    remember(question);
    let data;
    try {
      data = await api("/api/ask", { question });
    } catch (e) {
      data = { question, stage: "generation_error", error: `Request failed: ${e.message}`, timings: {} };
    }
    const node = resultCard(question, data);
    item.node.replaceWith(node);
    item.node = node;
    state.busy = false;
    if (composerInput) composerInput.dispatchEvent(new Event("input"));
  }

  // ---------- Guard lab ----------

  function renderGuard() {
    const presets = state.examples ? state.examples.guard_presets : [];
    const editor = h("textarea", { class: "editor", spellcheck: "false", "aria-label": "SQL to check" });
    editor.value = presets.length ? presets[1].sql : "";
    const verdict = h("div", { class: "verdict", "aria-live": "polite" });
    const runBtn = h("button", { class: "btn primary", type: "button" }, icon("shield", 15), "Run through the guard");
    const presetButtons = presets.map((p, i) => h("button", {
      class: "preset", type: "button", "aria-pressed": i === 1 ? "true" : "false",
      onclick: (e) => {
        editor.value = p.sql;
        for (const b of presetButtons) b.setAttribute("aria-pressed", "false");
        e.currentTarget.setAttribute("aria-pressed", "true");
        verdict.replaceChildren();
      },
    }, h("span", { class: `dot ${p.kind === "attack" ? "critical" : "good"}` }), p.label));

    async function run() {
      const sql = editor.value.trim();
      if (!sql) return;
      runBtn.disabled = true;
      verdict.replaceChildren(h("div", { class: "pipeline", style: "padding:0" }, stepChip("Checking", "active")));
      try {
        const r = await api("/api/guard", { sql });
        const parts = [];
        if (!r.allowed) {
          parts.push(h("div", { class: "notice critical" }, icon("ban"), h("div", {},
            h("strong", { text: "Blocked. " }), r.reason, ` Rejected in ${fmtMs(r.timings.guard_ms)}; it never reached the database.`)));
        } else {
          parts.push(h("div", { class: "notice good" }, icon("check"), h("div", {},
            h("strong", { text: "Allowed. " }), `Checked in ${fmtMs(r.timings.guard_ms)}, ran in ${fmtMs(r.timings.execute_ms)}. This is the exact query that ran:`)));
          parts.push(sqlBlock(r.executed_sql, { open: true, title: "SQL that ran",
            note: /\blimit\b/i.test(sql) ? null : "LIMIT added by the guard" }));
          if (r.error) parts.push(h("div", { class: "notice warning" }, icon("alert"), h("div", { text: r.error })));
          if (r.result) parts.push(dataTable(r.result));
        }
        verdict.replaceChildren(...parts);
      } catch (e) {
        verdict.replaceChildren(h("div", { class: "notice critical" }, icon("alert"), h("div", { text: e.message })));
      } finally {
        runBtn.disabled = false;
      }
    }
    runBtn.addEventListener("click", run);
    editor.addEventListener("keydown", (e) => { if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); run(); } });

    const checks = [
      ["Parses, never pattern-matches", "The SQL becomes a syntax tree. Text tricks don't get through."],
      ["Exactly one statement", "A hidden second statement is rejected."],
      ["Only SELECT", "Inserts, updates, deletes, drops and settings are rejected."],
      ["Known tables and columns", "Checked against the catalog. No table functions, no raw layer."],
      ["Bounded result", "A LIMIT is added or tightened before anything runs."],
    ];
    const side = h("aside", { class: "card card-pad" },
      h("h2", { class: "section-title", text: "What the guard checks" }),
      h("ol", { class: "checks" }, checks.map(([t, d], i) =>
        h("li", {}, h("span", { class: "n", text: String(i + 1) }), h("div", {}, h("strong", { text: t }), d)))),
      h("div", { class: "divider" }),
      h("h2", { class: "section-title", text: "If something slipped past" }),
      h("p", { style: "margin:0;color:var(--text-2);font-size:13px", text:
        "The database connection is opened read-only with external file access disabled, so even a query that passed the guard could not change data or read files." }));

    main.replaceChildren(h("div", { class: "view" },
      h("div", { class: "view-head" }, h("h1", { text: "Guard lab" }),
        h("p", { text: "Every model-written query passes through this guard before it reaches the warehouse. Try to get something past it." })),
      h("div", { class: "lab" },
        h("div", {},
          h("div", { class: "presets" }, presetButtons),
          editor,
          h("div", { class: "lab-actions" }, runBtn, h("span", { class: "kbd", text: "Ctrl + Enter" })),
          verdict),
        side)));
  }

  // ---------- Schema ----------

  async function renderSchema() {
    main.replaceChildren(h("div", { class: "view" }, h("div", { class: "pipeline", style: "padding:0" }, stepChip("Loading schema", "active"))));
    if (!state.schema) state.schema = await api("/api/schema");
    const sc = state.schema;
    const totalCols = sc.tables.reduce((n, t) => n + t.columns.length, 0);
    const stat = (label, value) => h("div", { class: "stat" }, h("div", { class: "stat-label", text: label }), h("div", { class: "stat-value", text: value }));
    const s = state.status;

    const cards = sc.tables.map((t) => h("section", { class: "card card-pad table-card" },
      h("div", { class: "table-card-head" }, h("h3", { text: t.name }), h("span", { class: "grow" }),
        h("span", { class: "badge neutral", text: `${fmtInt(t.rows)} rows` })),
      h("p", { class: "desc", text: t.description }),
      h("ul", { class: "col-list" }, t.columns.map((c) => h("li", {},
        h("div", {}, h("span", { class: "col-name", text: c.name }), h("span", { class: "col-type", text: c.type.toLowerCase() })),
        h("div", { class: "col-desc", text: c.description }),
        c.sample_values.length ? h("div", { class: "values" }, c.sample_values.map((v) => h("span", { class: "value-chip", text: String(v) }))) : null)))));

    const promptPre = h("pre", { class: "prompt-pre mono", text: sc.prompt_text });
    promptPre.hidden = true;
    const promptBtn = h("button", { class: "btn small", type: "button", text: "Show the exact prompt text" });
    promptBtn.addEventListener("click", () => { promptPre.hidden = !promptPre.hidden; promptBtn.textContent = promptPre.hidden ? "Show the exact prompt text" : "Hide prompt text"; });

    main.replaceChildren(h("div", { class: "view" },
      h("div", { class: "view-head" }, h("h1", { text: "Schema" }),
        h("p", { text: "This is everything the model knows about the data: tables, descriptions, live sample values, metric definitions and what is not available." })),
      h("div", { class: "summary-row" }, stat("Tables", String(sc.tables.length)), stat("Columns", String(totalCols)),
        stat("Defined metrics", String(Object.keys(sc.metrics).length)), stat("Years covered", s ? `${s.data_start.slice(0, 4)}–${s.data_end.slice(0, 4)}` : "")),
      h("div", { class: "schema-grid" },
        h("section", { class: "card card-pad" }, h("h2", { class: "section-title", text: "Metric definitions" }),
          h("dl", { class: "def-list" }, Object.entries(sc.metrics).flatMap(([k, v]) => [h("dt", { text: k }), h("dd", { text: v })]))),
        h("section", { class: "card card-pad" }, h("h2", { class: "section-title", text: "Not in this data (the assistant will decline)" }),
          h("ul", { class: "plain-list" }, sc.not_available.map((x) => h("li", { text: x }))),
          h("div", { class: "divider" }), promptBtn, promptPre),
        ...cards)));
  }

  // ---------- Evaluation ----------

  async function renderEval() {
    main.replaceChildren(h("div", { class: "view" }, h("div", { class: "pipeline", style: "padding:0" }, stepChip("Loading runs", "active"))));
    const { runs } = await api("/api/eval/runs");
    const head = h("div", { class: "view-head" }, h("h1", { text: "Evaluation" }),
      h("p", { text: "Execution accuracy on hand-written questions: the generated query and the gold query are both run, and their results compared." }));
    if (!runs.length) {
      main.replaceChildren(h("div", { class: "view" }, head, h("div", { class: "card empty" },
        h("p", { text: "No evaluation runs yet. Run this in the project folder:" }),
        h("p", {}, h("code", { text: "python eval\\run_eval.py" })))));
      return;
    }
    const select = h("select", { class: "select", "aria-label": "Evaluation run" }, runs.map((r) =>
      h("option", { value: r.name, text: `${r.run_at ? r.run_at.replace("T", " ") : r.name} · ${r.label || ""} · ${r.model || ""}` })));
    const body = h("div", {});
    select.addEventListener("change", () => showRun(select.value, body));
    main.replaceChildren(h("div", { class: "view" }, head, h("div", { class: "eval-head" }, select), body));
    showRun(runs[0].name, body);
  }

  async function showRun(name, host) {
    const d = await api(`/api/eval/runs/${encodeURIComponent(name)}`);
    const pct = (x) => `${Math.round(x * 100)}%`;
    const parts = [];
    if (d.data_source === "sample") {
      parts.push(h("div", { class: "notice warning", style: "margin-bottom:16px" }, icon("alert"),
        h("div", { text: "This run used generated sample data. Its numbers are not results." })));
    }
    const answerable = d.records.filter((r) => r.band !== "unanswerable").length;
    const left = h("section", { class: "card card-pad" },
      h("div", { class: "hero-figure" }, h("div", { class: "stat-label", text: "Execution accuracy" }),
        h("div", { class: "value", text: pct(d.execution_accuracy) })),
      h("div", { style: "color:var(--text-2);font-size:13px;margin-bottom:14px",
        text: `${d.records.filter((r) => r.correct && r.band !== "unanswerable").length} of ${answerable} answerable questions` }),
      h("div", { class: "stat-row" },
        h("div", { class: "stat" }, h("div", { class: "stat-label", text: "Valid SQL" }), h("div", { class: "stat-value", text: pct(d.valid_sql_rate) })),
        h("div", { class: "stat" }, h("div", { class: "stat-label", text: "Median time" }),
          h("div", { class: "stat-value", text: d.median_latency_s != null ? `${d.median_latency_s.toFixed(1)}s` : "—" }))),
      h("div", { class: "divider" }),
      h("div", { style: "display:flex;flex-direction:column;gap:6px;font-size:12.5px;color:var(--text-2)" },
        h("span", {}, h("strong", { text: "Model " }), `${d.provider || ""} · ${d.model}`),
        h("span", {}, h("strong", { text: "Effort " }), d.effort || ""),
        h("span", {}, h("strong", { text: "Blocked by guard " }), String(d.blocked_by_guard)),
        h("span", {}, h("strong", { text: "Tokens " }), `${fmtInt(d.total_input_tokens)} in · ${fmtInt(d.total_output_tokens)} out`)));

    const bandHost = h("div", { class: "chart" });
    const bands = Object.entries(d.by_band).map(([b, v]) => ({ label: `${b.replace(/_/g, " ")} (${v.correct}/${v.total})`, value: v.total ? v.correct / v.total : 0 }));
    Charts.chart(bandHost, { form: "bar", points: bands.sort((a, b) => b.value - a.value), valueName: "accuracy" },
      { format: (v) => pct(v), title: "Accuracy by question type" });
    const right = h("section", { class: "card card-pad" }, h("h2", { class: "section-title", text: "Accuracy by question type" }), bandHost);

    const rows = [];
    for (const r of d.records) {
      const detail = h("tr", { class: "detail", hidden: true }, h("td", { colspan: "5" }, h("div", { class: "detail-grid" },
        h("div", {}, h("h4", { text: "Generated SQL" }), h("pre", { class: "mono" }, r.predicted_sql ? highlightSql(r.predicted_sql) : document.createTextNode(r.error || "(none)"))),
        h("div", {}, h("h4", { text: "Gold SQL" }), h("pre", { class: "mono" }, r.gold_sql ? highlightSql(r.gold_sql) : document.createTextNode("(should decline)"))))));
      const row = h("tr", { class: "rec", tabindex: "0", "aria-expanded": "false" },
        h("td", { class: "mono", text: r.id }),
        h("td", {}, h("span", { class: `badge ${r.correct ? "good" : "critical"}` }, icon(r.correct ? "check" : "x", 12), r.correct ? "Pass" : "Fail")),
        h("td", { text: r.band.replace(/_/g, " ") }),
        h("td", { class: "q", text: r.question }),
        h("td", { class: "q", text: r.reason || "" }));
      const toggle = () => { detail.hidden = !detail.hidden; row.setAttribute("aria-expanded", String(!detail.hidden)); };
      row.addEventListener("click", toggle);
      row.addEventListener("keydown", (e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); toggle(); } });
      rows.push(row, detail);
    }
    const table = h("div", { class: "table-wrap", style: "max-height:none" }, h("table", { class: "data records" },
      h("thead", {}, h("tr", {}, ["Id", "Result", "Type", "Question", "Why"].map((t) => h("th", { text: t })))),
      h("tbody", {}, rows)));

    parts.push(h("div", { class: "eval-grid" }, left, right), h("h2", { class: "section-title", text: "Every question — click a row to compare SQL" }), table);
    host.replaceChildren(...parts);
  }

  // ---------- routing & boot ----------

  function route() {
    const view = (location.hash || "#ask").slice(1);
    state.view = ["ask", "guard", "schema", "eval"].includes(view) ? view : "ask";
    for (const btn of document.querySelectorAll(".nav-item")) {
      if (btn.dataset.view === state.view) btn.setAttribute("aria-current", "page"); else btn.removeAttribute("aria-current");
    }
    main.scrollTop = 0;
    const render = { ask: renderAsk, guard: renderGuard, schema: renderSchema, eval: renderEval }[state.view];
    Promise.resolve(render()).catch((e) => main.replaceChildren(h("div", { class: "view" },
      h("div", { class: "notice critical" }, icon("alert"), h("div", { text: e.message })))));
  }

  async function boot() {
    renderChrome();
    renderHistory();
    try {
      [state.status, state.examples] = await Promise.all([api("/api/status"), api("/api/examples")]);
    } catch (e) {
      main.replaceChildren(h("div", { class: "view" }, h("div", { class: "notice critical" }, icon("alert"), h("div", {},
        h("strong", { text: "The warehouse isn't ready. " }), e.message,
        " Build it with: python scripts\\build_warehouse.py (or --sample), then restart the server."))));
      return;
    }
    renderChrome();
    window.addEventListener("hashchange", route);
    matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyThemeButton);
    route();
  }

  boot();
})();
