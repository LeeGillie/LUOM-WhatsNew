/* LUOM What's New UI.
 *
 * Reads /api/index and /api/state from the local server (wecreat_index.server),
 * filters and sorts entirely in the browser, and starts scans with POST /api/scan.
 * Filter state lives in the URL hash so a reload or bookmark keeps it.
 */
(() => {
  "use strict";

  // ------------------------------------------------------------------ helpers

  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ESC[c]);

  const decoder = document.createElement("textarea");
  const unescapeHtml = (s) => { decoder.innerHTML = s ?? ""; return decoder.value; };

  const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const MONTHS_LONG = ["January", "February", "March", "April", "May", "June", "July",
    "August", "September", "October", "November", "December"];

  /** WordPress / scanner timestamps carry no zone; read them as local wall time. */
  function parseIso(s) {
    if (!s) return null;
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2})(?::(\d{2}))?)?/.exec(s);
    if (!m) return null;
    return new Date(+m[1], +m[2] - 1, +m[3], +(m[4] || 0), +(m[5] || 0), +(m[6] || 0));
  }
  const fmtDate = (d) => d ? `${MONTHS[d.getMonth()]} ${d.getDate()}, ${d.getFullYear()}` : "—";
  function fmtTime(d) {
    let h = d.getHours(); const ap = h >= 12 ? "PM" : "AM"; h = h % 12 || 12;
    return `${h}:${String(d.getMinutes()).padStart(2, "0")} ${ap}`;
  }
  const fmtDateTime = (d) => d ? `${fmtDate(d)} · ${fmtTime(d)}` : "—";
  function fmtRelative(d) {
    if (!d) return "";
    const s = Math.round((Date.now() - d.getTime()) / 1000);
    if (s < 45) return "just now";
    const m = Math.round(s / 60); if (m < 60) return `${m} min ago`;
    const h = Math.round(m / 60); if (h < 24) return `${h} hour${h === 1 ? "" : "s"} ago`;
    const days = Math.round(h / 24); if (days < 30) return `${days} day${days === 1 ? "" : "s"} ago`;
    const mo = Math.round(days / 30); return `${mo} month${mo === 1 ? "" : "s"} ago`;
  }
  const plural = (n, one, many) => `${n} ${n === 1 ? one : (many || one + "s")}`;

  async function getJson(url, opts) {
    const res = await fetch(url, Object.assign({ cache: "no-store" }, opts));
    let body = null;
    try { body = await res.json(); } catch (_) { /* empty body */ }
    return { ok: res.ok, status: res.status, body };
  }

  let toastTimer = 0;
  function toast(msg, isError) {
    const el = $("#toast");
    el.textContent = msg;
    el.classList.toggle("err", !!isError);
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { el.hidden = true; }, isError ? 7000 : 4500);
  }

  // ------------------------------------------------------------------ model

  /** Which rule(s) produced a match, derived from the reason strings. */
  const RULES = [
    { key: "ultra-category", label: "Lumos Ultra category", test: (r) => /Lumos Ultra specific/i.test(r) },
    { key: "ultra-title", label: "Title names Lumos Ultra", test: (r) => /^title mentions/i.test(r) },
    { key: "ultra-body", label: "Body names Lumos Ultra", test: (r) => /^body mentions/i.test(r) },
    { key: "shared-category", label: "Shared hardware / software category", test: (r) => /^shared category/i.test(r) },
    { key: "makeit-topic", label: "MakeIt workflow topic", test: (r) => /MakeIt topic/i.test(r) },
  ];

  const STATUS_LABEL = { new: "New", updated: "Updated", unchanged: "Unchanged" };
  const CONF_LABEL = { direct: "Direct", likely: "Likely", other: "Not Lumos Ultra" };

  // ------------------------------------------------------------------ viewer preferences
  // Remembered in this browser only (localStorage); the page works without them.

  const PREF_KEYS = { showOther: "luom-whatsnew.showOther", linkMode: "luom-whatsnew.linkMode" };
  function readPref(key, fallback) {
    try { const v = localStorage.getItem(key); return v === null ? fallback : v; } catch (_) { return fallback; }
  }
  function writePref(key, value) {
    try { localStorage.setItem(key, value); } catch (_) { /* private mode: keep it for this visit */ }
  }
  /** How article links open: a separate reused window, one reused tab, or a new tab each time. */
  const LINK_MODES = ["window", "reuse", "new"];
  const linkModeOf = (v) => (LINK_MODES.includes(v) ? v : "window");
  const PREFS = {
    showOther: readPref(PREF_KEYS.showOther, "0") === "1",          // off by default
    linkMode: linkModeOf(readPref(PREF_KEYS.linkMode, "window")),   // separate window by default
  };
  /** Indexed, but not about the Lumos Ultra. */
  const isOther = (a) => a.confidence === "other";
  /** Name of the browser tab / window reused for WeCreat articles, and the handle to it. */
  const ARTICLE_TAB = "luom-whatsnew-article";
  let articleTab = null;

  /** Size and place the article window beside the app: right-hand part of the screen. */
  function articleWindowFeatures() {
    const s = window.screen || {};
    const availW = s.availWidth || 1280, availH = s.availHeight || 800;
    const width = Math.round(Math.max(760, Math.min(1200, availW * 0.55)));
    const height = Math.round(availH * 0.92);
    const left = Math.round((s.availLeft || 0) + Math.max(0, availW - width - 16));
    const top = Math.round((s.availTop || 0) + Math.max(0, (availH - height) / 2));
    return `popup=yes,width=${width},height=${height},left=${left},top=${top}`;
  }

  let INDEX = null;     // raw index.json
  let STATE = null;     // raw state.json
  let ARTICLES = [];    // enriched records

  function enrich(a) {
    const paths = (a.category_paths && a.category_paths.length)
      ? a.category_paths
      : (a.categories || []).map(unescapeHtml);
    const cats = paths.map((p) => {
      const parts = p.split(" › ");
      return { path: p, section: parts[0], leaf: parts[parts.length - 1], parent: parts.slice(0, -1).join(" › ") };
    });
    // One entry per distinct path (the API occasionally repeats a term).
    const seen = new Set();
    const uniqueCats = cats.filter((c) => !seen.has(c.path) && seen.add(c.path));
    const pub = parseIso(a.published_iso);
    const mod = parseIso(a.modified_iso);
    const reasons = a.match_reasons || [];
    const rules = RULES.filter((r) => reasons.some(r.test)).map((r) => r.key);
    const excerpt = (a.excerpt || "").replace(/\s*(\[…\]|\[&hellip;\]|\.\.\.)\s*$/, "…");
    return Object.assign({}, a, {
      _cats: uniqueCats,
      _sections: Array.from(new Set(uniqueCats.map((c) => c.section))),
      _pub: pub,
      _mod: mod,
      _seen: parseIso(a.first_seen),
      _rules: rules,
      _excerpt: excerpt,
      _modifiedLater: pub && mod && (mod - pub) > 24 * 3600 * 1000,
      _hay: {
        title: (a.title || "").toLowerCase(),
        excerpt: excerpt.toLowerCase(),
        text: (a.text || "").toLowerCase(),
        categories: uniqueCats.map((c) => c.path).join(" | ").toLowerCase(),
        reasons: reasons.join(" | ").toLowerCase(),
        url: `${a.url || ""} ${a.slug || ""}`.toLowerCase(),
        id: String(a.id),
      },
    });
  }

  // ------------------------------------------------------------------ filter state

  const DEFAULTS = {
    tab: "articles", q: "", scope: "all", sort: "published-desc",
    section: "", cat: "", topic: "", conf: "", status: "", rule: "", year: "", tag: "", from: "", to: "",
  };
  let F = Object.assign({}, DEFAULTS);

  const CONTROLS = {
    q: "#fQuery", scope: "#fScope", sort: "#fSort", section: "#fSection", cat: "#fCategory", topic: "#fTopic",
    conf: "#fConfidence", status: "#fStatus", rule: "#fRule", year: "#fYear", tag: "#fTag",
    from: "#fFrom", to: "#fTo",
  };

  function readHash() {
    const p = new URLSearchParams(location.hash.slice(1));
    F = Object.assign({}, DEFAULTS);
    for (const k of Object.keys(DEFAULTS)) if (p.has(k)) F[k] = p.get(k);
  }
  function writeHash() {
    const p = new URLSearchParams();
    for (const [k, v] of Object.entries(F)) if (v && v !== DEFAULTS[k]) p.set(k, v);
    const h = p.toString();
    history.replaceState(null, "", h ? `#${h}` : location.pathname + location.search);
  }

  // ------------------------------------------------------------------ search

  /** `lumos "test grid" -vision` -> include ["lumos", "test grid"], exclude ["vision"] */
  function parseQuery(q) {
    const include = [], exclude = [];
    const re = /(-?)"([^"]+)"|(-?)(\S+)/g;
    let m;
    while ((m = re.exec(q))) {
      const neg = m[1] || m[3];
      const term = (m[2] || m[4] || "").toLowerCase().trim();
      if (!term || term === "-") continue;
      (neg ? exclude : include).push(term);
    }
    return { include, exclude };
  }

  function haystackFor(a, scope) {
    if (scope === "all") return Object.values(a._hay).join(" \n ");
    return a._hay[scope] || "";
  }

  /** A short window of article text around the first search hit, or "". */
  function snippet(a, terms) {
    if (!terms.length || !a.text) return "";
    const shown = `${a._hay.title} ${a._hay.excerpt}`;
    const hay = a._hay.text;
    // Only worth showing when some term is not already visible on the card.
    const hidden = terms.filter((t) => !shown.includes(t) && hay.includes(t));
    if (!hidden.length) return "";
    const at = Math.min(...hidden.map((t) => hay.indexOf(t)));
    const start = Math.max(0, at - 90);
    const end = Math.min(a.text.length, at + 170);
    let s = a.text.slice(start, end);
    if (start > 0) s = "…" + s.replace(/^\S*\s/, "");
    if (end < a.text.length) s = s.replace(/\s\S*$/, "") + "…";
    return s;
  }

  /** Wrap the matched terms in <mark>, escaping everything else. */
  function highlight(text, terms) {
    if (!terms.length || !text) return esc(text);
    const lower = text.toLowerCase();
    const hits = [];
    for (const t of terms) {
      let i = 0;
      while ((i = lower.indexOf(t, i)) !== -1) { hits.push([i, i + t.length]); i += t.length; }
    }
    if (!hits.length) return esc(text);
    hits.sort((x, y) => x[0] - y[0]);
    const merged = [hits[0].slice()];
    for (const h of hits.slice(1)) {
      const last = merged[merged.length - 1];
      if (h[0] <= last[1]) last[1] = Math.max(last[1], h[1]); else merged.push(h.slice());
    }
    let out = "", pos = 0;
    for (const [s, e] of merged) {
      out += esc(text.slice(pos, s)) + "<mark>" + esc(text.slice(s, e)) + "</mark>";
      pos = e;
    }
    return out + esc(text.slice(pos));
  }

  // ------------------------------------------------------------------ filtering + sorting

  function applyFilters(list, skip) {
    const { include, exclude } = parseQuery(F.q);
    const from = F.from ? parseIso(F.from) : null;
    const to = F.to ? parseIso(F.to) : null;
    if (to) to.setHours(23, 59, 59, 999);
    return list.filter((a) => {
      if (!PREFS.showOther && isOther(a)) return false;
      if (include.length || exclude.length) {
        const hay = haystackFor(a, F.scope);
        if (!include.every((t) => hay.includes(t))) return false;
        if (exclude.some((t) => hay.includes(t))) return false;
      }
      if (skip !== "section" && F.section && !a._sections.includes(F.section)) return false;
      if (skip !== "cat" && F.cat && !a._cats.some((c) => c.path === F.cat)) return false;
      if (skip !== "topic" && F.topic && !(a.topics || []).includes(F.topic)) return false;
      if (skip !== "conf" && F.conf && a.confidence !== F.conf) return false;
      if (skip !== "status" && F.status && a.status !== F.status) return false;
      if (skip !== "rule" && F.rule && !a._rules.includes(F.rule)) return false;
      if (skip !== "year" && F.year && (!a._pub || String(a._pub.getFullYear()) !== F.year)) return false;
      if (skip !== "tag" && F.tag && !(a.tags || []).includes(F.tag)) return false;
      if (from && (!a._pub || a._pub < from)) return false;
      if (to && (!a._pub || a._pub > to)) return false;
      return true;
    });
  }

  const byDate = (key, dir) => (x, y) => ((x[key]?.getTime() || 0) - (y[key]?.getTime() || 0)) * dir || y.id - x.id;
  const SORTS = {
    "published-desc": { cmp: byDate("_pub", -1), group: "_pub" },
    "published-asc": { cmp: byDate("_pub", 1), group: "_pub" },
    "modified-desc": { cmp: byDate("_mod", -1), group: "_mod" },
    "firstseen-desc": { cmp: (x, y) => byDate("_seen", -1)(x, y) || byDate("_pub", -1)(x, y), group: "_seen" },
    "confidence": {
      cmp: (x, y) => (x.confidence === y.confidence ? 0 : x.confidence === "direct" ? -1 : 1) || byDate("_pub", -1)(x, y),
      group: "confidence",
    },
    "title-asc": { cmp: (x, y) => x.title.localeCompare(y.title), group: null },
    "title-desc": { cmp: (x, y) => y.title.localeCompare(x.title), group: null },
  };

  // ------------------------------------------------------------------ dropdowns

  function countBy(list, keysOf) {
    const m = new Map();
    for (const a of list) for (const k of keysOf(a)) if (k) m.set(k, (m.get(k) || 0) + 1);
    return m;
  }

  /** Rebuild a <select>'s options, with live counts under the other active filters. */
  function fillSelect(sel, allLabel, entries, value) {
    const opts = [`<option value="">${esc(allLabel)}</option>`];
    let found = !value;
    for (const e of entries) {
      if (e.value === value) found = true;
      opts.push(`<option value="${esc(e.value)}"${e.value === value ? " selected" : ""}${e.count ? "" : " class=\"zero\""}>${esc(e.label)}${e.count != null ? `  (${e.count})` : ""}</option>`);
    }
    if (!found) opts.push(`<option value="${esc(value)}" selected>${esc(value)}  (0)</option>`);
    sel.innerHTML = opts.join("");
    sel.classList.toggle("is-set", !!value);
  }

  function buildDropdowns() {
    // Section
    {
      const pool = applyFilters(ARTICLES, "section");
      const counts = countBy(pool, (a) => a._sections);
      const all = Array.from(new Set(ARTICLES.flatMap((a) => a._sections))).sort();
      fillSelect($("#fSection"), "All sections", all.map((s) => ({ value: s, label: s, count: counts.get(s) || 0 })), F.section);
    }
    // Category - narrowed to the chosen section, labelled by its path
    {
      const pool = applyFilters(ARTICLES, "cat");
      const counts = countBy(pool, (a) => a._cats.map((c) => c.path));
      const all = new Map();
      for (const a of ARTICLES) for (const c of a._cats) all.set(c.path, c);
      const entries = Array.from(all.values())
        .filter((c) => !F.section || c.section === F.section)
        .sort((x, y) => x.path.localeCompare(y.path))
        .map((c) => ({ value: c.path, label: c.path, count: counts.get(c.path) || 0 }));
      fillSelect($("#fCategory"), F.section ? `All in ${F.section}` : "All categories", entries, F.cat);
    }
    // Topic - labels computed by the scanner (config.json "topics")
    {
      const counts = countBy(applyFilters(ARTICLES, "topic"), (a) => a.topics || []);
      const order = [];
      for (const a of ARTICLES) for (const t of a.topics || []) if (!order.includes(t)) order.push(t);
      order.sort((x, y) => x.localeCompare(y));
      fillSelect($("#fTopic"), "Any topic", order.map((t) => ({ value: t, label: t, count: counts.get(t) || 0 })), F.topic);
    }
    // Confidence
    {
      const counts = countBy(applyFilters(ARTICLES, "conf"), (a) => [a.confidence]);
      fillSelect($("#fConfidence"), "Any confidence",
        ["direct", "likely"].concat(PREFS.showOther ? ["other"] : [])
          .map((k) => ({ value: k, label: CONF_LABEL[k], count: counts.get(k) || 0 })), F.conf);
    }
    // Status
    {
      const counts = countBy(applyFilters(ARTICLES, "status"), (a) => [a.status]);
      fillSelect($("#fStatus"), "Any status",
        ["new", "updated", "unchanged"].map((k) => ({ value: k, label: STATUS_LABEL[k], count: counts.get(k) || 0 })), F.status);
    }
    // Matched by
    {
      const counts = countBy(applyFilters(ARTICLES, "rule"), (a) => a._rules);
      fillSelect($("#fRule"), "Any rule",
        RULES.map((r) => ({ value: r.key, label: r.label, count: counts.get(r.key) || 0 })), F.rule);
    }
    // Year
    {
      const counts = countBy(applyFilters(ARTICLES, "year"), (a) => [a._pub && String(a._pub.getFullYear())]);
      const years = Array.from(new Set(ARTICLES.map((a) => a._pub && String(a._pub.getFullYear())).filter(Boolean))).sort().reverse();
      fillSelect($("#fYear"), "Any year", years.map((y) => ({ value: y, label: y, count: counts.get(y) || 0 })), F.year);
    }
    // Tag - only shown when the site actually uses tags
    {
      const tags = Array.from(new Set(ARTICLES.flatMap((a) => a.tags || []))).sort();
      $("#fTagField").hidden = !tags.length && !F.tag;
      const counts = countBy(applyFilters(ARTICLES, "tag"), (a) => a.tags || []);
      fillSelect($("#fTag"), "Any tag", tags.map((t) => ({ value: t, label: t, count: counts.get(t) || 0 })), F.tag);
    }
    $("#fQuery").value = F.q;
    $("#fScope").value = F.scope;
    $("#fSort").value = SORTS[F.sort] ? F.sort : DEFAULTS.sort;
    $("#fFrom").value = F.from; $("#fFrom").classList.toggle("is-set", !!F.from);
    $("#fTo").value = F.to; $("#fTo").classList.toggle("is-set", !!F.to);
  }

  // ------------------------------------------------------------------ rendering: articles

  function groupLabel(a, key) {
    if (key === "confidence") return a.confidence === "direct" ? "Direct — names the Lumos Ultra" : "Likely — shared software, hardware and workflows";
    const d = a[key];
    return d ? `${MONTHS_LONG[d.getMonth()]} ${d.getFullYear()}` : "Undated";
  }

  function cardHtml(a, terms) {
    const scopeHits = (s) => F.scope === "all" || F.scope === s ? terms : [];
    const d = a._pub;
    const badges = [];
    if (a.status === "new") badges.push(`<span class="badge badge-new">New</span>`);
    if (a.status === "updated") badges.push(`<span class="badge badge-updated">Updated</span>`);
    badges.push(`<span class="badge badge-${esc(a.confidence)}" title="${a.confidence === "direct" ? "Names the Lumos Ultra or sits in a Lumos Ultra category"
      : isOther(a) ? "Indexed, but not about the Lumos Ultra" : "Shared software / hardware or a MakeIt workflow"}">${esc(CONF_LABEL[a.confidence] || a.confidence)}</span>`);

    const cats = a._cats.map((c) =>
      `<button type="button" class="cat" data-cat="${esc(c.path)}" title="Filter to ${esc(c.path)}">` +
      (c.parent ? `<span class="cat-parent">${highlight(c.parent.replace(/^WeCreat /, ""), scopeHits("categories"))} › </span>` : "") +
      `${highlight(c.leaf, scopeHits("categories"))}</button>`
    ).join("");

    const reasons = (a.match_reasons || []).map((r) =>
      `<li>${highlight(r, scopeHits("reasons")).replace(/'([^']+)'/g, "<code>$1</code>")}</li>`).join("");

    const foot = [];
    if (a._modifiedLater) foot.push(`<span title="${esc(a.modified_iso)}">Modified ${esc(fmtDate(a._mod))}</span>`);
    if (a._seen) foot.push(`<span${foot.length ? '' : ""} title="${esc(a.first_seen)}">First seen ${esc(fmtDate(a._seen))}</span>`);
    foot.push(`<span${foot.length ? '' : ""}>ID ${highlight(String(a.id), scopeHits("id"))}</span>`);
    foot.push(`<a class="ext" href="${esc(a.url)}" target="_blank" rel="noopener" title="Read the original article on WeCreat's site">Read on help.wecreat.com ↗</a>`);

    const snip = (F.scope === "all" || F.scope === "text") ? snippet(a, terms) : "";
    const cls = (a.status === "new" ? " is-new" : a.status === "updated" ? " is-updated" : "")
      + (isOther(a) ? " is-other" : "");
    return `
      <article class="card${cls}">
        <div class="date-block" title="Published ${esc(a.published_iso)}">
          <span class="m">${d ? MONTHS[d.getMonth()] : "—"}</span>
          <span class="d">${d ? d.getDate() : ""}</span>
          <span class="y">${d ? d.getFullYear() : ""}</span>
        </div>
        <div class="card-body">
          <div class="card-head">
            <h3 class="card-title"><a href="${esc(a.url)}" target="_blank" rel="noopener">${highlight(a.title, scopeHits("title"))}</a></h3>
            <div class="badges">${badges.join("")}</div>
          </div>
          ${a._excerpt ? `<p class="excerpt clamp" title="Click to expand">${highlight(a._excerpt, scopeHits("excerpt"))}</p>` : ""}
          ${snip ? `<p class="snippet"><span class="snippet-label">In article</span>${highlight(snip, terms)}</p>` : ""}
          ${cats ? `<div class="cats">${cats}</div>` : ""}
          <div class="card-foot">
            ${foot.join("")}
            <details class="why why-row"><summary>${isOther(a) ? "Why it is not included" : "Why it matched"}</summary><ul>${reasons}</ul></details>
          </div>
        </div>
      </article>`;
  }

  function renderArticles() {
    const list = $("#list");
    if (!INDEX) return;
    buildDropdowns();

    const sort = SORTS[F.sort] || SORTS[DEFAULTS.sort];
    const rows = applyFilters(ARTICLES).sort(sort.cmp);
    const { include } = parseQuery(F.q);

    const total = PREFS.showOther ? ARTICLES.length : ARTICLES.filter((a) => !isOther(a)).length;
    const hidden = ARTICLES.length - total;
    $("#resultCount").innerHTML = (rows.length === total
      ? `<strong>${total}</strong> articles`
      : `Showing <strong>${rows.length}</strong> of ${total}`)
      + (hidden ? ` <span class="muted">· ${hidden} not about the Lumos Ultra hidden</span>` : "");
    renderChips();

    if (!rows.length) {
      list.innerHTML = `
        <div class="empty">
          <h3>No articles match</h3>
          <p>Try a different search term or loosen a filter.</p>
          <button type="button" class="btn" data-action="clear">Clear filters</button>
        </div>`;
      return;
    }

    const out = [];

    // Pin what the last scan found at the top, whatever the sort order. The
    // same cards stay in their normal place below, still marked.
    const fresh = F.status ? [] : rows.filter((a) => a.status === "new" || a.status === "updated");
    if (fresh.length) {
      const n = fresh.filter((a) => a.status === "new").length;
      const u = fresh.length - n;
      const bits = [n && plural(n, "new article"), u && plural(u, "updated article")].filter(Boolean).join(" · ");
      const since = INDEX.previous_run
        ? `Scan of ${esc(fmtDateTime(parseIso(INDEX.generated_at)))}, compared with ${esc(fmtDateTime(parseIso(INDEX.previous_run)))}`
        : "";
      out.push(`
        <section class="fresh" aria-label="New since the last scan">
          <div class="fresh-head">
            <span class="fresh-dot" aria-hidden="true"></span>
            <h2>New since the last scan</h2>
            <span class="fresh-count">${bits}</span>
            ${since ? `<span class="fresh-since">${since}</span>` : ""}
          </div>
          <div class="cards">${fresh.sort(SORTS["published-desc"].cmp).map((a) => cardHtml(a, include)).join("")}</div>
        </section>
        <div class="all-head"><h2>All articles</h2></div>`);
    }

    let current = null, bucket = [];
    const flush = () => {
      if (!bucket.length) return;
      if (current !== null) out.push(`<div class="group-head"><h2>${esc(current)}</h2><span class="n">${plural(bucket.length, "article")}</span></div>`);
      out.push(`<div class="cards">${bucket.join("")}</div>`);
      bucket = [];
    };
    for (const a of rows) {
      const g = sort.group ? groupLabel(a, sort.group) : null;
      if (g !== current) { flush(); current = g; }
      bucket.push(cardHtml(a, include));
    }
    flush();
    list.innerHTML = out.join("");
  }

  function renderChips() {
    const chips = [];
    const add = (key, text) => chips.push(`<button type="button" class="chip-active" data-clear="${key}" title="Remove this filter">${esc(text)}<span class="x" aria-hidden="true">×</span></button>`);
    if (F.q) add("q", `${F.scope !== "all" ? $("#fScope").selectedOptions[0]?.text : "Search"}: ${F.q}`);
    if (F.section) add("section", F.section);
    if (F.cat) add("cat", F.cat.replace(/^WeCreat /, ""));
    if (F.topic) add("topic", `Topic: ${F.topic}`);
    if (F.conf) add("conf", CONF_LABEL[F.conf] || F.conf);
    if (F.status) add("status", STATUS_LABEL[F.status] || F.status);
    if (F.rule) add("rule", (RULES.find((r) => r.key === F.rule) || {}).label || F.rule);
    if (F.year) add("year", F.year);
    if (F.tag) add("tag", `Tag: ${F.tag}`);
    if (F.from) add("from", `From ${fmtDate(parseIso(F.from))}`);
    if (F.to) add("to", `To ${fmtDate(parseIso(F.to))}`);
    $("#activeChips").innerHTML = chips.join("");
    $("#clearFilters").hidden = chips.length < 2;
  }

  function renderNewsStrip() {
    const strip = $("#newsStrip");
    const c = INDEX?.counts || {};
    const n = c.new || 0, u = c.updated || 0, gone = c.no_longer_matching || 0;
    if (!n && !u && !gone) { strip.hidden = true; return; }
    const parts = [];
    if (n) parts.push(`<strong>${plural(n, "new article")}</strong>`);
    if (u) parts.push(`<strong>${plural(u, "update")}</strong>`);
    if (gone) parts.push(`${gone} no longer matching`);
    strip.innerHTML = `
      <span>${parts.join(" · ")} since the previous scan${INDEX.previous_run ? ` (${esc(fmtDateTime(parseIso(INDEX.previous_run)))})` : ""}.</span>
      <span class="spacer"></span>
      ${n ? `<button type="button" class="btn btn-sm" data-show-status="new">Show new</button>` : ""}
      ${u ? `<button type="button" class="btn btn-sm" data-show-status="updated">Show updated</button>` : ""}
      <button type="button" class="btn btn-sm btn-ghost" data-show-tab="state">Details</button>`;
    strip.hidden = false;
  }

  // ------------------------------------------------------------------ rendering: state

  const S = { q: "", conf: "", seen: "", key: "published_iso", dir: -1 };

  function tile(label, value, sub, small) {
    return `<div class="tile"><div class="tile-label">${esc(label)}</div>
      <div class="tile-value${small ? " sm" : ""}">${value}</div>${sub ? `<div class="tile-sub">${sub}</div>` : ""}</div>`;
  }

  function renderState() {
    const tiles = $("#stateTiles");
    if (!STATE) {
      tiles.innerHTML = "";
      $("#stateChanges").innerHTML = `<p class="muted">No <code>state.json</code> yet — run a scan to record a baseline.</p>`;
      $("#stateTable tbody").innerHTML = "";
      $("#stateSub").textContent = "";
      return;
    }
    const all = Object.entries(STATE.articles || {}).map(([id, v]) => Object.assign({ id: +id }, v));
    const tracked = PREFS.showOther ? all : all.filter((t) => t.confidence !== "other");
    const last = parseIso(STATE.last_run), prev = parseIso(STATE.previous_run);
    const direct = all.filter((t) => t.confidence === "direct").length;
    const likely = all.filter((t) => t.confidence === "likely").length;
    const others = all.length - direct - likely;
    const otherOpt = $('#sConfidence option[value="other"]');
    if (otherOpt) otherOpt.hidden = !PREFS.showOther;
    if (!PREFS.showOther && S.conf === "other") S.conf = "";
    const c = INDEX?.counts || {};
    tiles.innerHTML = [
      tile("Scans recorded", esc(STATE.runs ?? 0), INDEX ? `Index run #${esc(INDEX.run_number)}` : ""),
      tile("Last run", esc(fmtDate(last)), last ? `${esc(fmtTime(last))} · ${esc(fmtRelative(last))}` : "", true),
      tile("Previous run", esc(fmtDate(prev)), prev ? `${esc(fmtTime(prev))} · ${esc(fmtRelative(prev))}` : "First run", true),
      tile("About the Lumos Ultra", esc(direct + likely), `${direct} direct · ${likely} likely`
        + (others ? ` · ${others} other KB articles also tracked` : "")),
      tile("Scanned last run", esc(c.articles_scanned ?? "—"), INDEX ? `Profile: ${esc(INDEX.source?.profile || "?")}` : ""),
    ].join("");

    // Changes (from index.json - state.json itself stores only the baseline)
    const ch = INDEX?.changes_since_last_run || { new: [], updated: [], no_longer_matching: [] };
    const col = (title, color, items, sub) => `
      <div class="change-col">
        <h3><span class="dot" style="background:${color}"></span>${esc(title)} <span class="muted">${items.length}</span></h3>
        ${items.length ? `<ul>${items.map((i) => `<li><a href="${esc(i.url || "#")}" target="_blank" rel="noopener">${esc(i.title)}</a><span class="sub">${sub(i)}</span></li>`).join("")}</ul>`
          : `<p class="none">None</p>`}
      </div>`;
    $("#stateChanges").innerHTML =
      col("New", "var(--new)", ch.new || [], (i) => `Published ${esc(i.published || "")} · ID ${esc(i.id)}`) +
      col("Updated", "var(--updated)", ch.updated || [], (i) =>
        `Modified ${esc(fmtDate(parseIso(i.modified)))}${i.previously_modified ? ` (was ${esc(fmtDate(parseIso(i.previously_modified)))})` : ""}`) +
      col("No longer matching", "var(--danger)", ch.no_longer_matching || [],
        (i) => `ID ${esc(i.id)}${i.reason ? ` · ${esc(i.reason)}` : ""}`);

    // Table
    const q = S.q.trim().toLowerCase();
    const rows = tracked.filter((t) => {
      if (q && !(t.title || "").toLowerCase().includes(q) && !String(t.id).includes(q)) return false;
      if (S.conf && t.confidence !== S.conf) return false;
      if (S.seen === "last" && t.first_seen !== STATE.last_run) return false;
      if (S.seen === "earlier" && t.first_seen === STATE.last_run) return false;
      return true;
    }).sort((x, y) => {
      const a = x[S.key] ?? "", b = y[S.key] ?? "";
      return (typeof a === "number" ? a - b : String(a).localeCompare(String(b))) * S.dir || y.id - x.id;
    });
    $("#stateSub").textContent = rows.length === tracked.length ? `${tracked.length}` : `${rows.length} of ${tracked.length}`;
    $$("#stateTable th").forEach((th) => {
      if (th.dataset.key === S.key) th.setAttribute("aria-sort", S.dir > 0 ? "ascending" : "descending");
      else th.removeAttribute("aria-sort");
    });
    const cell = (iso) => `<td title="${esc(iso || "")}">${esc(fmtDate(parseIso(iso)))}</td>`;
    $("#stateTable tbody").innerHTML = rows.map((t) => `
      <tr class="${t.first_seen === STATE.last_run && (STATE.runs || 0) > 1 ? "fresh" : ""}">
        <td class="col-title"><a href="${esc(t.url)}" target="_blank" rel="noopener">${esc(t.title)}</a><span class="id">ID ${esc(t.id)}</span></td>
        <td><span class="badge badge-${esc(t.confidence)}">${esc(CONF_LABEL[t.confidence] || t.confidence)}</span></td>
        ${cell(t.published_iso)}${cell(t.modified_iso)}${cell(t.first_seen)}${cell(t.last_seen)}
      </tr>`).join("") || `<tr><td colspan="6" class="muted">No tracked articles match.</td></tr>`;
  }

  // ------------------------------------------------------------------ header / tabs

  function renderHeader() {
    const d = INDEX ? parseIso(INDEX.generated_at) : null;
    $("#lastRun").textContent = d ? fmtDateTime(d) : "Never";
    $("#lastRun").setAttribute("datetime", INDEX?.generated_at || "");
    $("#lastRunRel").textContent = d ? fmtRelative(d) : "Run a scan to build the index";
    $("#lastRunBox").classList.toggle("stale", !!d && Date.now() - d.getTime() > 8 * 24 * 3600 * 1000);
    $("#lastRunBox").title = INDEX
      ? `index.json generated ${INDEX.generated_at} (run #${INDEX.run_number})${INDEX.previous_run ? `\nprevious run ${INDEX.previous_run}` : ""}`
      : "";
    $("#countArticles").textContent = PREFS.showOther ? ARTICLES.length : ARTICLES.filter((a) => !isOther(a)).length;
    const tracked = Object.values(STATE?.articles || {});
    $("#countState").textContent = PREFS.showOther ? tracked.length
      : tracked.filter((t) => t.confidence !== "other").length;
    const fresh = ARTICLES.filter((a) => a.status === "new" && (PREFS.showOther || !isOther(a))).length;
    $("#countNew").hidden = !fresh;
    $("#countNew").textContent = `${fresh} new`;
    if (!STOPPED) document.title = fresh ? `(${fresh} new) LUOM What's New` : "LUOM What's New";
    if (INFO?.data_dir) $("#stateDataDir").textContent = INFO.data_dir;
  }

  function setTab(tab) {
    F.tab = tab === "state" ? "state" : "articles";
    for (const b of $$(".tab")) b.setAttribute("aria-selected", String(b.dataset.tab === F.tab));
    $("#tab-articles").hidden = F.tab !== "articles";
    $("#tab-state").hidden = F.tab !== "state";
    writeHash();
  }

  function updateStickyOffset() {
    document.documentElement.style.setProperty("--sticky-offset", `${$(".topbar").offsetHeight}px`);
  }

  function renderAll() {
    renderHeader();
    renderNewsStrip();
    renderArticles();
    renderState();
    setTab(F.tab);
    updateStickyOffset();
  }

  function showNoIndex(message) {
    $("#list").innerHTML = `
      <div class="empty">
        <h3>No index yet</h3>
        <p>${esc(message || "Run a scan to read WeCreat's public knowledge base and build your index.")}</p>
        <button type="button" class="btn btn-primary" data-action="scan">Run first scan</button>
      </div>`;
    $("#resultCount").textContent = "";
  }

  // ------------------------------------------------------------------ data loading

  async function loadData() {
    try {
      const [idx, st] = await Promise.all([getJson("api/index"), getJson("api/state")]);
      INDEX = idx.ok ? idx.body : null;
      STATE = st.ok ? st.body : null;
    } catch (err) {
      showNoIndex("Cannot reach LUOM What's New. It may have been stopped - start it again, then reload this page.");
      return;
    }
    ARTICLES = (INDEX?.articles || []).map(enrich);
    renderAll();
    if (!INDEX) { showNoIndex(); if (splashDone) openFirstRun(); }
  }

  // ------------------------------------------------------------------ splash

  const SPLASH_MIN_MS = 1800;
  const splashStart = Date.now();
  let splashDone = document.documentElement.classList.contains("no-splash");
  let splashSkip = null;

  /** Fade the splash out once it has been up for SPLASH_MIN_MS (or is clicked). */
  function hideSplash() {
    const el = $("#splash");
    if (splashDone || !el) { splashDone = true; return Promise.resolve(); }
    try { sessionStorage.setItem("luom-splash-shown", "1"); } catch (_) { /* private mode */ }
    const wait = Math.max(0, SPLASH_MIN_MS - (Date.now() - splashStart));
    return new Promise((resolve) => {
      const finish = () => {
        el.classList.add("is-leaving");
        setTimeout(() => { el.hidden = true; splashDone = true; resolve(); }, 400);
      };
      const timer = setTimeout(finish, wait);
      splashSkip = () => { clearTimeout(timer); splashSkip = null; finish(); };
    });
  }

  // ------------------------------------------------------------------ first run / exit

  let INFO = null;      // /api/info
  let STOPPED = false;

  function openFirstRun() {
    const dlg = $("#firstRun");
    if (dlg.open) return;
    $("#frDataDir").textContent = INFO?.data_dir || "the application data folder";
    $("#frProgress").hidden = true;
    $("#frError").hidden = true;
    $("#frGo").disabled = false;
    $("#frGo").textContent = "Download index now";
    $("#frExit").disabled = false;
    if (typeof dlg.showModal === "function") dlg.showModal(); else dlg.setAttribute("open", "");
  }

  function firstRunProgress(status) {
    if (!$("#firstRun").open) return;
    $("#frProgress").hidden = false;
    const log = $("#frLog");
    log.textContent = (status.log || []).join("\n") || "Starting…";
    log.scrollTop = log.scrollHeight;
  }

  /** Finish the dialog's download. Returns false when the dialog was not in use. */
  function firstRunDone(ok) {
    const dlg = $("#firstRun");
    if (!dlg.open) return false;
    $("#frExit").disabled = false;
    if (ok && INDEX) {
      dlg.close();
      $("#scanPanel").hidden = true;
      updateStickyOffset();
      toast(`Index built — ${plural(ARTICLES.length, "article")}. Later scans will highlight anything new.`);
    } else {
      $("#frProgress").hidden = false;
      $("#frError").textContent = "The download did not finish. Check the internet connection and try again, or exit.";
      $("#frError").hidden = false;
      $("#frGo").disabled = false;
      $("#frGo").textContent = "Try again";
    }
    return true;
  }

  async function exitProgram() {
    STOPPED = true;
    clearTimeout(polling);
    try {
      await getJson("api/shutdown", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    } catch (_) { /* already gone */ }
    const dlg = $("#firstRun");
    if (dlg.open) dlg.close();
    $(".topbar").hidden = true;
    $(".page").hidden = true;
    $("#toast").hidden = true;
    $("#stopped").hidden = false;
    document.title = "LUOM What's New — stopped";
    window.close(); // only works if the tab was opened by script; the message covers the rest
  }

  // ------------------------------------------------------------------ scanning

  let polling = 0;

  function setScanning(on) {
    const btn = $("#scanBtn");
    btn.classList.toggle("is-busy", on);
    btn.disabled = on;
    $(".btn-text", btn).textContent = on ? "Scanning…" : "Run scan";
  }

  function showScanLog(status) {
    firstRunProgress(status);
    const panel = $("#scanPanel");
    panel.hidden = false;
    const log = $("#scanLog");
    const atBottom = log.scrollTop + log.clientHeight >= log.scrollHeight - 8;
    log.textContent = (status.log || []).join("\n") || "Starting…";
    if (atBottom) log.scrollTop = log.scrollHeight;
    const st = $("#scanStatus");
    st.className = "scan-panel-status";
    if (status.running) st.textContent = `Running since ${fmtDateTime(parseIso(status.started_at))}`;
    else if (status.exit_code === 0) { st.textContent = `Finished ${fmtDateTime(parseIso(status.finished_at))}`; st.classList.add("ok"); }
    else if (status.exit_code != null) { st.textContent = `Failed (exit code ${status.exit_code})`; st.classList.add("err"); }
    updateStickyOffset();
  }

  async function pollScan() {
    clearTimeout(polling);
    let r;
    try { r = await getJson("api/scan"); } catch (_) { polling = setTimeout(pollScan, 2000); return; }
    const status = r.body || {};
    showScanLog(status);
    if (status.running) { polling = setTimeout(pollScan, 700); return; }
    setScanning(false);
    if (status.exit_code === 0) {
      await loadData();
      if (firstRunDone(true)) return;
      const c = INDEX?.counts || {};
      const bits = [];
      if (c.new) bits.push(plural(c.new, "new article"));
      if (c.updated) bits.push(plural(c.updated, "update"));
      if (c.no_longer_matching) bits.push(`${c.no_longer_matching} dropped`);
      toast(`Scan complete — ${bits.length ? bits.join(", ") : "nothing new"}.`);
      setTimeout(() => { if (!$("#scanBtn").disabled) { $("#scanPanel").hidden = true; updateStickyOffset(); } }, 6000);
    } else {
      if (firstRunDone(false)) return;
      toast("Scan failed — see the scan output for details.", true);
    }
  }

  async function startScan() {
    setScanning(true);
    let r;
    try {
      r = await getJson("api/scan", { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" });
    } catch (_) {
      setScanning(false);
      if (firstRunDone(false)) return;
      toast("Cannot reach the local server.", true);
      return;
    }
    if (!r.ok && r.status !== 409) {
      setScanning(false);
      if (firstRunDone(false)) return;
      toast(r.body?.error || `Could not start the scan (HTTP ${r.status}).`, true);
      return;
    }
    if (r.status === 409) toast("A scan is already running — showing its progress.");
    showScanLog(r.body || {});
    pollScan();
  }

  // ------------------------------------------------------------------ events

  function setFilter(key, value) {
    F[key] = value;
    if (key === "section" && F.cat && !F.cat.startsWith(value)) F.cat = "";
    writeHash();
    renderArticles();
  }

  function bind() {
    let qTimer = 0;
    $("#fQuery").addEventListener("input", (e) => {
      clearTimeout(qTimer);
      qTimer = setTimeout(() => setFilter("q", e.target.value.trim()), 120);
    });
    for (const [key, sel] of Object.entries(CONTROLS)) {
      if (key === "q") continue;
      $(sel).addEventListener("change", (e) => setFilter(key, e.target.value));
    }

    $("#clearFilters").addEventListener("click", clearFilters);
    $("#activeChips").addEventListener("click", (e) => {
      const b = e.target.closest("[data-clear]");
      if (b) setFilter(b.dataset.clear, DEFAULTS[b.dataset.clear]);
    });

    $("#list").addEventListener("click", (e) => {
      const cat = e.target.closest(".cat");
      if (cat) { F.section = ""; setFilter("cat", cat.dataset.cat); window.scrollTo({ top: 0, behavior: "smooth" }); return; }
      const ex = e.target.closest(".excerpt");
      if (ex && !window.getSelection().toString()) { ex.classList.toggle("clamp"); return; }
      const act = e.target.closest("[data-action]");
      if (act?.dataset.action === "clear") clearFilters();
      if (act?.dataset.action === "scan") startScan();
    });

    $("#newsStrip").addEventListener("click", (e) => {
      const s = e.target.closest("[data-show-status]");
      if (s) { setFilter("status", s.dataset.showStatus); return; }
      const t = e.target.closest("[data-show-tab]");
      if (t) setTab(t.dataset.showTab);
    });

    for (const b of $$(".tab")) b.addEventListener("click", () => setTab(b.dataset.tab));
    $(".tabs").addEventListener("keydown", (e) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;
      const next = F.tab === "articles" ? "state" : "articles";
      setTab(next); $(`#tabBtn-${next}`).focus();
    });

    $("#scanBtn").addEventListener("click", startScan);

    // Viewer preferences
    $("#optShowOther").checked = PREFS.showOther;
    $("#optShowOther").addEventListener("change", (e) => {
      PREFS.showOther = e.target.checked;
      writePref(PREF_KEYS.showOther, PREFS.showOther ? "1" : "0");
      if (!PREFS.showOther && F.conf === "other") F.conf = "";
      renderHeader(); renderArticles(); renderState();
    });
    $("#optLinkMode").value = PREFS.linkMode;
    $("#optLinkMode").addEventListener("change", (e) => {
      PREFS.linkMode = linkModeOf(e.target.value);
      writePref(PREF_KEYS.linkMode, PREFS.linkMode);
      articleTab = null;   // the next article opens in the newly chosen way
    });

    // Article links: "window" sends every WeCreat article to one separate
    // browser window, "reuse" to one tab; "new" leaves the links' own
    // target=_blank behaviour. Ctrl/Shift/middle-click keep their usual
    // meaning in every mode.
    document.addEventListener("click", (e) => {
      if (PREFS.linkMode === "new" || e.defaultPrevented || e.button !== 0
          || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
      const link = e.target.closest("a[href]");
      if (!link) return;
      let url;
      try { url = new URL(link.href); } catch (_) { return; }
      if (url.hostname !== "help.wecreat.com") return;
      // Keep a handle on the tab rather than finding it by name: browsers
      // clear a tab's name when it moves to another site. The tab keeps its
      // opener link to this page - browsers only let the opener send it to
      // the next article. (It only ever shows WeCreat's own help site.)
      if (!articleTab || articleTab.closed) {
        // One name per mode, so a leftover article window is never reused as
        // the "same tab" or vice versa. "" keeps an existing one's page.
        articleTab = window.open("", `${ARTICLE_TAB}-${PREFS.linkMode}`,
          PREFS.linkMode === "window" ? articleWindowFeatures() : "");
        if (!articleTab) return;                // pop-up blocked: let the link open normally
      }
      e.preventDefault();
      articleTab.location.href = url.href;
      articleTab.focus();
    });

    // About & disclaimer
    const openAbout = () => { const d = $("#about"); if (!d.open) d.showModal(); };
    $("#aboutBtn").addEventListener("click", openAbout);
    document.addEventListener("click", (e) => { if (e.target.closest("[data-open-about]")) openAbout(); });
    $("#aboutClose").addEventListener("click", () => $("#about").close());
    $("#about").addEventListener("click", (e) => { if (e.target === $("#about")) $("#about").close(); });
    $("#splash").addEventListener("click", () => splashSkip && splashSkip());
    $("#exitBtn").addEventListener("click", () => {
      if (window.confirm("Stop LUOM What's New? The page will stop working until you start the program again.")) exitProgram();
    });

    // First-run dialog: the user has to pick one of the two buttons.
    $("#firstRun").addEventListener("cancel", (e) => e.preventDefault());
    $("#frExit").addEventListener("click", exitProgram);
    $("#frGo").addEventListener("click", () => {
      $("#frGo").disabled = true;
      $("#frGo").textContent = "Downloading…";
      $("#frExit").disabled = true;
      $("#frError").hidden = true;
      $("#frProgress").hidden = false;
      $("#frLog").textContent = "Starting…";
      startScan();
    });
    $("#scanPanelClose").addEventListener("click", () => { $("#scanPanel").hidden = true; updateStickyOffset(); });

    // State tab controls
    $("#sQuery").addEventListener("input", (e) => { S.q = e.target.value; renderState(); });
    $("#sConfidence").addEventListener("change", (e) => { S.conf = e.target.value; renderState(); });
    $("#sSeen").addEventListener("change", (e) => { S.seen = e.target.value; renderState(); });
    $("#stateTable thead").addEventListener("click", (e) => {
      const th = e.target.closest("th");
      if (!th) return;
      const key = th.dataset.key;
      S.dir = S.key === key ? -S.dir : (key === "title" || key === "confidence" ? 1 : -1);
      S.key = key;
      renderState();
    });

    // "/" focuses search, Esc clears it
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && splashSkip) { splashSkip(); return; }
      const typing = /^(INPUT|SELECT|TEXTAREA)$/.test(document.activeElement?.tagName);
      if (e.key === "/" && !typing) {
        e.preventDefault();
        if (F.tab !== "articles") setTab("articles");
        $("#fQuery").focus(); $("#fQuery").select();
      } else if (e.key === "Escape" && document.activeElement === $("#fQuery") && F.q) {
        $("#fQuery").value = ""; setFilter("q", "");
      }
    });

    window.addEventListener("hashchange", () => { readHash(); renderArticles(); setTab(F.tab); });
    window.addEventListener("resize", updateStickyOffset);

    // Refresh when coming back to the tab, in case a scheduled scan ran meanwhile.
    document.addEventListener("visibilitychange", async () => {
      if (document.hidden || STOPPED || $("#scanBtn").disabled || $("#firstRun").open) return;
      try {
        const r = await getJson("api/index");
        if (r.ok && r.body?.generated_at !== INDEX?.generated_at) await loadData();
      } catch (_) { /* server gone; leave the page as is */ }
    });

    setInterval(renderHeader, 30000);
  }

  function clearFilters() {
    const keep = { tab: F.tab, sort: F.sort, scope: F.scope };
    F = Object.assign({}, DEFAULTS, keep);
    writeHash();
    renderArticles();
  }

  // ------------------------------------------------------------------ boot

  async function boot() {
    // Read before the first render rewrites the hash with the filter state.
    const wantAbout = new URLSearchParams(location.hash.slice(1)).has("about");
    readHash();
    bind();
    try {
      const r = await getJson("api/info");
      if (r.ok) INFO = r.body;
    } catch (_) { /* loadData reports an unreachable server */ }
    if (INFO?.version) {
      $("#appVersion").textContent = `v${INFO.version}`;
      $("#aboutVersion").textContent = INFO.version;
    }
    await loadData();
    await hideSplash();
    if (!INDEX && !STOPPED) openFirstRun();
    // ...#about links straight to the About & disclaimer dialog.
    else if (wantAbout) $("#aboutBtn").click();
    // Attach to a scan that was started from another tab or before a reload.
    try {
      const r = await getJson("api/scan");
      if (r.body?.running) { setScanning(true); pollScan(); }
    } catch (_) { /* ignore */ }
  }

  boot();
})();
