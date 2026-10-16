"use strict";
/* Onion or Not: every number on this page comes from a real call to /api/ask. */

const MODELS = [
  { id: "jev", name: "Jev", sub: "TypeSafe's hosted decision model", badge: "J" },
  { id: "anyjev", name: "AnyJev L0", sub: "Qwen3-8B on your machine, with AnyJev", badge: "AJ" },
  { id: "raw", name: "Qwen3-8B raw", sub: "the same model, no AnyJev correction", badge: "Q" },
];
// real headlines from The Onion and from news sites (Oct 2026); no answer key is shown, they're just inputs
const EXAMPLES = [
  "Corn Named World's Sexiest Plant",
  "Left-wing candidate Hitler Mussolini wins local vote in Peru",
  "TSA officers now not allowed to sit down while checking boarding passes and IDs",
  "Audubon Society Formally Excommunicates Penguins",
  "The First New Sunscreen Type In 25 Years Has Arrived On U.S. Shelves",
];
const HISTORY_KEY = "onion-or-not:history";

const $ = (s, root = document) => root.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const pct = p => {
  const v = p * 100;
  if (v === 100 || v === 0) return v + "%";
  if (v >= 99.95) return ">99.9%";
  if (v <= 0.05) return "<0.1%";
  return v > 99 || v < 1 ? v.toFixed(1) + "%" : Math.round(v) + "%";
};
const fmtMs = ms => ms < 1000 ? Math.round(ms) + " ms" : (ms / 1000).toFixed(1) + " s";
const fmtCost = c => c === 0 ? "free" : c < 0.0001 ? "<$0.0001" : "$" + c.toFixed(4);

let STATUS = null, RUN = 0;

// --------------------------------------------------------------------------------- status + setup
async function refreshStatus() {
  try { STATUS = await (await fetch("/api/status")).json(); } catch (e) { STATUS = null; }
  return STATUS;
}
function availability(id) {
  if (!STATUS) return { ok: false, html: `<div class="err">Can't reach the local server. Is <code>onion-or-not</code> still running?</div>` };
  if (id === "jev") {
    if (STATUS.jev.ready) return { ok: true };
    return { ok: false, html: `<div class="setup"><b>Add your TypeSafe API key</b> to ask Jev:<ol>
      <li>Get a key at <a href="https://typesafe.ai" target="_blank" rel="noopener">typesafe.ai</a></li>
      <li>Put <code>TYPESAFE_API_KEY=your-key</code> in the <code>.env</code> file</li>
      <li>Restart <code>onion-or-not</code></li></ol></div>` };
  }
  const L = STATUS.local;
  if (L.ready) return { ok: true };
  if (L.reason === "no_model") return { ok: false, html: `<div class="setup"><b>Download the open model</b> (about 5 GB, once):<ol>
      <li>Run <code>onion-or-not download</code></li><li>Reload this page</li></ol></div>` };
  return { ok: false, html: `<div class="err">The local model didn't load: ${esc(L.detail || "unknown error")}</div>` };
}

// --------------------------------------------------------------------------------------- cards
function card(m) {
  const c = document.createElement("article");
  c.className = "model card"; c.dataset.id = m.id;
  c.innerHTML = `<div class="m-head"><div class="badge ${m.id}">${m.badge}</div>
    <div><div class="m-name">${esc(m.name)}</div><div class="m-sub">${esc(m.sub)}</div></div></div>
    <div class="body"></div>`;
  return c;
}
function barHtml(p) {
  return `<div class="bar"><div class="s" style="width:${p * 100}%"></div><div class="r" style="width:${(1 - p) * 100}%"></div></div>`;
}
function renderIdle(m) {
  const a = availability(m.id);
  if (!a.ok) return a.html;
  if (m.id !== "jev" && STATUS.local.loaded === false)
    return `<div class="note">${STATUS.local.loading ? '<span class="spinner"></span>Loading the model on your machine…' : "Ready. The model loads on the first question."}</div>`;
  return `<div class="note">Ready.</div>`;
}
function renderWaiting(m) {
  const loading = m.id !== "jev" && STATUS && STATUS.local && !STATUS.local.loaded;
  return `<div class="verdict"><span class="note">${loading ? '<span class="spinner"></span>Loading the model on your machine (first time only)…' : '<span class="spinner"></span>Thinking…'}</span></div>
    <div><div class="bar wait"></div><div class="bar-labels"><span>satire</span><span>real news</span></div></div>`;
}
function renderResult(res, res2) {
  const p = res.probs["satire"], ans = p >= 0.5 ? "satire" : "real";
  let h = `<div class="verdict"><span class="ans ${ans}">${ans === "satire" ? "Satire" : "Real news"}</span>
    <span class="conf">${pct(Math.max(p, 1 - p))} sure</span></div>
    <div>${barHtml(p)}<div class="bar-labels"><span class="s"><b>${pct(p)}</b> satire</span><span class="r">real news <b>${pct(1 - p)}</b></span></div></div>`;
  if (res2 !== undefined) {
    if (res2 && res2.probs) {
      const q = res2.probs["satire"], same = (p >= 0.5) === (q >= 0.5);
      h += `<div class="swapped">Asked “real news or satire?” instead: <b>${pct(q)}</b> satire${barHtml(q)}
        <span class="flag ${same ? "same" : "changed"}">${same ? "Same answer" : "Changed its answer"}</span></div>`;
    } else if (res2 && res2.error) {
      h += `<div class="swapped err">Swapped order failed: ${esc(res2.error)}</div>`;
    } else {
      h += `<div class="swapped"><span class="spinner"></span>Asking with the options swapped…</div>`;
    }
  }
  const total = res.latency_ms + (res2 && res2.latency_ms ? res2.latency_ms : 0);
  const cost = res.cost_usd + (res2 && res2.cost_usd ? res2.cost_usd : 0);
  h += `<div class="meta"><span>${fmtMs(total)}</span><span>${fmtCost(cost)}</span><span title="${esc(res.model)}">${esc(res.model)}</span></div>`;
  return h;
}

function drawIdle() {
  const box = $("#results"); box.innerHTML = "";
  for (const m of MODELS) { const c = card(m); $(".body", c).innerHTML = renderIdle(m); box.appendChild(c); }
}

// ----------------------------------------------------------------------------------------- ask
async function askOne(model, headline, swapped) {
  try {
    const r = await fetch("/api/ask", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ headline, model, swapped }) });
    const j = await r.json();
    if (!r.ok && !j.error) j.error = (j.detail && j.detail[0] && j.detail[0].msg) || `HTTP ${r.status}`;
    return j;
  } catch (e) { return { error: "Can't reach the local server." }; }
}

// the text box grows with the headline, so a long one is never cut off on a phone
function grow() { const t = $("#headline"); t.style.height = "auto"; t.style.height = t.scrollHeight + 2 + "px"; }

async function run(headline) {
  grow();
  headline = headline.replace(/\s+/g, " ").trim();
  if (!headline) { $("#headline").focus(); return; }
  const id = ++RUN, swap = $("#swap").checked;
  $("#go").disabled = true;
  await refreshStatus();
  const box = $("#results"); box.innerHTML = "";
  const entry = { t: headline, v: {} };
  // local models share one GPU, so ask them one after the other; Jev runs alongside
  const local = MODELS.filter(m => m.id !== "jev");
  const jobs = [];
  const cards = {};
  for (const m of MODELS) {
    const c = card(m); cards[m.id] = c; box.appendChild(c);
    const a = availability(m.id);
    $(".body", c).innerHTML = a.ok ? renderWaiting(m) : a.html;
  }
  const doModel = async m => {
    if (!availability(m.id).ok) return;
    const body = $(".body", cards[m.id]);
    const res = await askOne(m.id, headline, false);
    if (id !== RUN) return;
    if (res.error) { body.innerHTML = `<div class="err">${esc(res.error)}</div>`; return; }
    entry.v[m.id] = res.probs["satire"];
    body.innerHTML = renderResult(res, swap ? null : undefined);
    if (swap) {
      const res2 = await askOne(m.id, headline, true);
      if (id !== RUN) return;
      body.innerHTML = renderResult(res, res2);
    }
  };
  jobs.push(doModel(MODELS[0]));
  jobs.push((async () => { for (const m of local) await doModel(m); })());
  await Promise.all(jobs);
  if (id !== RUN) return;
  $("#go").disabled = false;
  if (Object.keys(entry.v).length) saveHistory(entry);
  refreshStatus();
}

// ------------------------------------------------------------------------------------- history
function loadHistory() { try { return JSON.parse(localStorage.getItem(HISTORY_KEY)) || []; } catch (e) { return []; } }
function saveHistory(entry) {
  const h = [entry, ...loadHistory().filter(x => x.t !== entry.t)].slice(0, 12);
  try { localStorage.setItem(HISTORY_KEY, JSON.stringify(h)); } catch (e) {}
  drawHistory();
}
function drawHistory() {
  const h = loadHistory(), ul = $("#history");
  $("#historyBox").hidden = !h.length;
  ul.innerHTML = "";
  for (const e of h) {
    const li = document.createElement("li");
    const dots = MODELS.map(m => {
      const p = e.v[m.id];
      if (p == null) return `<span class="dot none" title="${esc(m.name)}">${m.badge}</span>`;
      return `<span class="dot ${p >= .5 ? "satire" : "real"}" title="${esc(m.name)}: ${pct(p)} satire">${m.badge}</span>`;
    }).join("");
    li.innerHTML = `<span class="t">${esc(e.t)}</span><span class="v">${dots}</span>`;
    li.addEventListener("click", () => { $("#headline").value = e.t; run(e.t); window.scrollTo({ top: 0, behavior: "smooth" }); });
    ul.appendChild(li);
  }
}

// ---------------------------------------------------------------------------------------- init
$("#form").addEventListener("submit", ev => { ev.preventDefault(); run($("#headline").value); });
$("#headline").addEventListener("keydown", ev => {
  if (ev.key === "Enter" && !ev.shiftKey) { ev.preventDefault(); run($("#headline").value); }
});
$("#headline").addEventListener("input", grow);
window.addEventListener("resize", grow);
$("#clear").addEventListener("click", () => { try { localStorage.removeItem(HISTORY_KEY); } catch (e) {} drawHistory(); });
for (const ex of EXAMPLES) {
  const b = document.createElement("button");
  b.type = "button"; b.className = "chip"; b.textContent = ex;
  b.addEventListener("click", () => { $("#headline").value = ex; run(ex); });
  $("#examples").appendChild(b);
}

(async () => {
  await refreshStatus();
  drawIdle(); drawHistory();
  // start loading the local model in the background so the first question is quick
  if (STATUS && STATUS.local.ready && !STATUS.local.loaded) {
    await fetch("/api/warmup", { method: "POST" }).catch(() => {});
    const poll = setInterval(async () => {
      await refreshStatus();
      if (!$("#results .bar")) drawIdle();      // only redraw while nothing has been asked yet
      if (!STATUS || STATUS.local.loaded || !STATUS.local.ready) clearInterval(poll);
    }, 1500);
  }
})();
