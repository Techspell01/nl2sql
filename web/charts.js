// Charts for query results. Plain SVG, no library: each form follows the same specs
// (single series, thin marks, hairline grid, value labels in text ink, hover + focus tooltips).
(function () {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";
  const nf = new Intl.NumberFormat(undefined, { maximumFractionDigits: 2 });
  const nfCompact = new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 });
  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

  function svg(tag, attrs, text) {
    const el = document.createElementNS(NS, tag);
    for (const [k, v] of Object.entries(attrs || {})) el.setAttribute(k, v);
    if (text != null) el.textContent = text;
    return el;
  }

  function fmt(v) {
    if (v === null || v === undefined) return "—";
    if (typeof v === "number") return Math.abs(v) >= 1e6 ? nfCompact.format(v) : nf.format(v);
    if (typeof v === "boolean") return v ? "true" : "false";
    return String(v);
  }

  function fmtAxis(v) {
    return Math.abs(v) >= 1e4 ? nfCompact.format(v) : nf.format(v);
  }

  function humanize(name) {
    const s = String(name).replace(/_/g, " ").trim();
    return s.charAt(0).toUpperCase() + s.slice(1);
  }

  // ISO timestamps from the API -> short labels ("Mar 2017" when every point is a month start)
  function dateLabels(values) {
    const monthly = values.every((v) => typeof v === "string" && /^\d{4}-\d{2}-01/.test(v));
    return values.map((v) => {
      if (typeof v !== "string") return fmt(v);
      const [y, m, d] = v.slice(0, 10).split("-");
      return monthly ? `${MONTHS[Number(m) - 1]} ${y}` : `${d} ${MONTHS[Number(m) - 1]} ${y}`;
    });
  }

  let measureCtx;
  function textWidth(text, font) {
    measureCtx = measureCtx || document.createElement("canvas").getContext("2d");
    measureCtx.font = font || "12.5px system-ui, -apple-system, 'Segoe UI', sans-serif";
    return measureCtx.measureText(text).width;
  }

  function niceTicks(min, max, count) {
    if (min === max) { max = min + 1; }
    const span = max - min;
    const step0 = Math.pow(10, Math.floor(Math.log10(span / count)));
    const err = (count * step0) / span;
    const step = step0 * (err <= 0.15 ? 10 : err <= 0.35 ? 5 : err <= 0.75 ? 2 : 1);
    const lo = Math.floor(min / step) * step;
    const hi = Math.ceil(max / step) * step;
    const ticks = [];
    for (let v = lo; v <= hi + step / 2; v += step) ticks.push(Number(v.toPrecision(12)));
    return ticks;
  }

  // A bar with a 4px rounded data-end and a square base, growing right (horizontal) or up (vertical).
  function barPath(x0, x1, y, h, horizontal) {
    if (horizontal) {
      const w = x1 - x0, r = Math.max(0, Math.min(4, Math.abs(w), h / 2)), dir = w >= 0 ? 1 : -1;
      const tip = x1 - dir * r;
      return `M${x0},${y}H${tip}a${r},${r} 0 0 ${dir > 0 ? 1 : 0} ${dir * r},${r}V${y + h - r}` +
        `a${r},${r} 0 0 ${dir > 0 ? 1 : 0} ${-dir * r},${r}H${x0}Z`;
    }
    // vertical: x0 = left, x1 = width, y = top of bar (value end), h = baseline y
    const left = x0, w = x1, top = y, base = h, r = Math.max(0, Math.min(4, w / 2, base - top));
    return `M${left},${base}V${top + r}a${r},${r} 0 0 1 ${r},${-r}H${left + w - r}` +
      `a${r},${r} 0 0 1 ${r},${r}V${base}Z`;
  }

  function tooltip(host) {
    const tip = document.createElement("div");
    tip.className = "tooltip";
    tip.hidden = true;
    const tv = document.createElement("div"); tv.className = "tv";
    const tl = document.createElement("div"); tl.className = "tl";
    const key = document.createElement("span"); key.className = "key";
    const label = document.createElement("span");
    tl.append(key, label);
    tip.append(tv, tl);
    host.appendChild(tip);
    return {
      show(x, y, value, text) {
        tv.textContent = value; label.textContent = text;
        tip.style.left = `${x}px`; tip.style.top = `${y}px`; tip.hidden = false;
      },
      hide() { tip.hidden = true; },
    };
  }

  // ---------- forms ----------

  function horizontalBar(host, points, opts) {
    const width = Math.max(320, host.clientWidth);
    const font = "12.5px system-ui, -apple-system, 'Segoe UI', sans-serif";
    const labelW = Math.min(240, Math.max(...points.map((p) => textWidth(p.label, font))) + 14);
    const valueText = points.map((p) => opts.format(p.value));
    const valueW = Math.max(...valueText.map((t) => textWidth(t, "12px system-ui"))) + 10;
    const rowH = 32, barH = 18, padTop = 4;
    const height = padTop + points.length * rowH + 4;
    const minV = Math.min(0, ...points.map((p) => p.value));
    const maxV = Math.max(0, ...points.map((p) => p.value));
    const x0 = labelW, x1 = width - valueW;
    const X = (v) => x0 + ((v - minV) / ((maxV - minV) || 1)) * (x1 - x0);
    const root = svg("svg", { width, height, role: "img", "aria-label": opts.title });
    const tip = tooltip(host);

    points.forEach((p, i) => {
      const y = padTop + i * rowH + (rowH - barH) / 2;
      const g = svg("g", { class: "mark-group", tabindex: "0", role: "listitem",
        "aria-label": `${p.label}: ${valueText[i]}` });
      g.appendChild(svg("rect", { class: "mark-hit", x: 0, y: padTop + i * rowH, width, height: rowH }));
      const label = p.label.length > 34 ? p.label.slice(0, 33) + "…" : p.label;
      g.appendChild(svg("text", { class: "cat-label", x: labelW - 12, y: y + barH / 2 + 4, "text-anchor": "end" }, label));
      g.appendChild(svg("path", { class: "mark", d: barPath(X(0), X(p.value), y, barH, true) }));
      const tipX = X(p.value);
      g.appendChild(svg("text", { class: "val-label", x: p.value >= 0 ? tipX + 6 : tipX - 6, y: y + barH / 2 + 4,
        "text-anchor": p.value >= 0 ? "start" : "end" }, valueText[i]));
      const show = () => tip.show(Math.min(tipX, x1 - 40), y, valueText[i], p.label);
      g.addEventListener("pointerenter", show);
      g.addEventListener("focus", show);
      g.addEventListener("pointerleave", tip.hide);
      g.addEventListener("blur", tip.hide);
      root.appendChild(g);
    });
    root.appendChild(svg("line", { class: "baseline", x1: X(0), x2: X(0), y1: 0, y2: height }));
    host.appendChild(root);
  }

  function columns(host, points, opts) {
    const width = Math.max(320, host.clientWidth), height = 240;
    const m = { top: 22, right: 8, bottom: 28, left: 8 };
    const maxV = Math.max(0, ...points.map((p) => p.value));
    const band = (width - m.left - m.right) / points.length;
    const w = Math.min(24, band * 0.6);
    const base = height - m.bottom;
    const Y = (v) => base - (v / (maxV || 1)) * (base - m.top);
    const root = svg("svg", { width, height, role: "img", "aria-label": opts.title });
    const tip = tooltip(host);
    points.forEach((p, i) => {
      const cx = m.left + band * (i + 0.5);
      const g = svg("g", { class: "mark-group", tabindex: "0", "aria-label": `${p.label}: ${opts.format(p.value)}` });
      g.appendChild(svg("rect", { class: "mark-hit", x: cx - band / 2, y: 0, width: band, height }));
      g.appendChild(svg("path", { class: "mark", d: barPath(cx - w / 2, w, Y(p.value), base, false) }));
      g.appendChild(svg("text", { class: "val-label", x: cx, y: Y(p.value) - 6, "text-anchor": "middle" }, opts.format(p.value)));
      g.appendChild(svg("text", { class: "tick", x: cx, y: height - 8, "text-anchor": "middle" }, p.label));
      const show = () => tip.show(cx, Y(p.value) - 4, opts.format(p.value), p.label);
      g.addEventListener("pointerenter", show);
      g.addEventListener("focus", show);
      g.addEventListener("pointerleave", tip.hide);
      g.addEventListener("blur", tip.hide);
      root.appendChild(g);
    });
    root.appendChild(svg("line", { class: "baseline", x1: m.left, x2: width - m.right, y1: base, y2: base }));
    host.appendChild(root);
  }

  function line(host, points, opts) {
    const width = Math.max(320, host.clientWidth), height = 260;
    const values = points.map((p) => p.value);
    const ticks = niceTicks(Math.min(0, ...values), Math.max(...values), 4);
    const tickW = Math.max(...ticks.map((t) => textWidth(fmtAxis(t), "11.5px system-ui"))) + 10;
    const last = points[points.length - 1];
    const endW = textWidth(opts.format(last.value), "12px system-ui") + 14;
    const m = { top: 12, right: endW, bottom: 28, left: tickW };
    const lo = ticks[0], hi = ticks[ticks.length - 1];
    const X = (i) => m.left + (points.length === 1 ? 0.5 : i / (points.length - 1)) * (width - m.left - m.right);
    const Y = (v) => m.top + (1 - (v - lo) / ((hi - lo) || 1)) * (height - m.top - m.bottom);
    const root = svg("svg", { width, height, role: "img", "aria-label": opts.title });

    for (const t of ticks) {
      root.appendChild(svg("line", { class: t === lo ? "baseline" : "gridline", x1: m.left, x2: width - m.right, y1: Y(t), y2: Y(t) }));
      root.appendChild(svg("text", { class: "tick", x: m.left - 8, y: Y(t) + 4, "text-anchor": "end" }, fmtAxis(t)));
    }
    const every = Math.max(1, Math.ceil(points.length / Math.max(2, Math.floor((width - m.left - m.right) / 72))));
    points.forEach((p, i) => {
      if (i % every === 0 || i === points.length - 1) {
        root.appendChild(svg("text", { class: "tick", x: X(i), y: height - 8, "text-anchor": "middle" }, p.label));
      }
    });
    const d = points.map((p, i) => `${i ? "L" : "M"}${X(i)},${Y(p.value)}`).join("");
    root.appendChild(svg("path", { class: "area", d: `${d}L${X(points.length - 1)},${Y(lo)}L${X(0)},${Y(lo)}Z` }));
    root.appendChild(svg("path", { class: "line", d }));
    const li = points.length - 1;
    root.appendChild(svg("circle", { class: "end-dot", cx: X(li), cy: Y(last.value), r: 4 }));
    root.appendChild(svg("text", { class: "val-label", x: X(li) + 9, y: Y(last.value) + 4 }, opts.format(last.value)));

    // crosshair: snaps to the nearest point; arrow keys move it when focused
    const cross = svg("line", { class: "crosshair", y1: m.top, y2: height - m.bottom, visibility: "hidden" });
    const dot = svg("circle", { class: "end-dot", r: 4, visibility: "hidden" });
    const hit = svg("rect", { class: "mark-hit", x: m.left, y: 0, width: width - m.left - m.right, height, tabindex: "0",
      "aria-label": `${opts.title}. Use arrow keys to read values.` });
    root.append(cross, dot, hit);
    const tip = tooltip(host);
    let at = li;
    const show = (i) => {
      at = Math.max(0, Math.min(li, i));
      const x = X(at), y = Y(points[at].value);
      cross.setAttribute("x1", x); cross.setAttribute("x2", x); cross.setAttribute("visibility", "visible");
      dot.setAttribute("cx", x); dot.setAttribute("cy", y); dot.setAttribute("visibility", "visible");
      tip.show(x, y, opts.format(points[at].value), points[at].label);
    };
    const hide = () => { cross.setAttribute("visibility", "hidden"); dot.setAttribute("visibility", "hidden"); tip.hide(); };
    hit.addEventListener("pointermove", (e) => {
      const rect = root.getBoundingClientRect();
      const px = e.clientX - rect.left;
      const step = (width - m.left - m.right) / Math.max(1, li);
      show(Math.round((px - m.left) / (step || 1)));
    });
    hit.addEventListener("pointerleave", hide);
    hit.addEventListener("focus", () => show(at));
    hit.addEventListener("blur", hide);
    hit.addEventListener("keydown", (e) => {
      if (e.key === "ArrowLeft") { show(at - 1); e.preventDefault(); }
      if (e.key === "ArrowRight") { show(at + 1); e.preventDefault(); }
    });
    host.appendChild(root);
  }

  // ---------- choosing a form ----------

  const TIME_NAME = /(^|_)(year|yr|month|mon|week|day|date|quarter|qtr|period)(_|$|s$)/i;

  function series(result) {
    const { columns: cols, rows } = result;
    if (!rows.length) return null;
    // year + month + value -> one time series labelled "Mar 2017"
    if (cols.length === 3 && cols.every((c) => c.kind === "number") &&
        /year|yr/i.test(cols[0].name) && /month|mon/i.test(cols[1].name)) {
      const pts = rows.map((r) => ({ key: r[0] * 100 + r[1], label: `${MONTHS[r[1] - 1]} ${r[0]}`, value: r[2] }))
        .sort((a, b) => a.key - b.key);
      return { form: pts.length >= 6 ? "line" : "columns", points: pts, valueName: cols[2].name, xName: "month" };
    }
    if (cols.length !== 2 || cols[1].kind !== "number") return null;
    const x = cols[0];
    const timeLike = x.kind === "date" || (x.kind === "number" && TIME_NAME.test(x.name));
    if (timeLike) {
      const sorted = rows.filter((r) => r[1] !== null).slice().sort((a, b) => (a[0] > b[0] ? 1 : a[0] < b[0] ? -1 : 0));
      const monthNumbers = x.kind === "number" && /month|mon/i.test(x.name) && sorted.every((r) => Number.isInteger(r[0]) && r[0] >= 1 && r[0] <= 12);
      const labels = x.kind === "date" ? dateLabels(sorted.map((r) => r[0]))
        : monthNumbers ? sorted.map((r) => MONTHS[r[0] - 1]) : sorted.map((r) => String(r[0]));
      const pts = sorted.map((r, i) => ({ label: labels[i], value: r[1] }));
      return { form: pts.length >= 6 ? "line" : "columns", points: pts, valueName: cols[1].name, xName: x.name };
    }
    if ((x.kind === "text" || x.kind === "bool") && rows.length >= 2 && rows.length <= 30) {
      const pts = rows.filter((r) => r[1] !== null).map((r) => ({ label: fmt(r[0]), value: r[1] }))
        .sort((a, b) => b.value - a.value);
      return { form: "bar", points: pts, valueName: cols[1].name, xName: x.name };
    }
    return null;
  }

  // Figures: one number -> a hero figure; one row of several values -> stat tiles.
  function figure(result) {
    const { columns: cols, rows } = result;
    if (rows.length !== 1) return null;
    if (cols.length === 1 && cols[0].kind === "number") {
      const wrap = document.createElement("div");
      wrap.className = "hero-figure";
      const label = document.createElement("div"); label.className = "stat-label"; label.textContent = humanize(cols[0].name);
      const value = document.createElement("div"); value.className = "value"; value.textContent = fmt(rows[0][0]);
      wrap.append(label, value);
      return wrap;
    }
    if (cols.length <= 6) {
      const wrap = document.createElement("div");
      wrap.className = "stat-row";
      cols.forEach((c, i) => {
        const s = document.createElement("div"); s.className = "stat";
        const l = document.createElement("div"); l.className = "stat-label"; l.textContent = humanize(c.name);
        const v = document.createElement("div"); v.className = "stat-value"; v.textContent = fmt(rows[0][i]);
        s.append(l, v);
        wrap.appendChild(s);
      });
      return wrap;
    }
    return null;
  }

  // Renders a chart into host and re-renders on resize. Returns false when no chart form fits.
  function chart(host, spec, opts) {
    opts = Object.assign({ format: fmt, title: humanize(spec.valueName) }, opts || {});
    const draw = () => {
      host.replaceChildren();
      if (spec.form === "bar") horizontalBar(host, spec.points, opts);
      else if (spec.form === "columns") columns(host, spec.points, opts);
      else line(host, spec.points, opts);
    };
    let lastWidth = 0;
    new ResizeObserver(() => {
      const w = host.clientWidth;
      if (w && Math.abs(w - lastWidth) > 4) { lastWidth = w; requestAnimationFrame(draw); }
    }).observe(host);
  }

  window.Charts = { series, figure, chart, fmt, humanize };
})();
