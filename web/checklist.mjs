// ✅ Checklist: every item from every order, grouped by kind (worked out from the name, movable), with a tick
// (received / checked), a job number and a staff tag. Shared by the website tool (saved in the browser) and the PC app
// (saved on the PC through /api/tags). Saved by order number + item, so ticks and tags follow the item into any later
// printout that has the same order.
//
//   const cl = createChecklist({el, store, getRes});   store = {load: async () => obj, save: async obj => {}}
//   cl.render()   (call again after a new PDF is read)

export const AUTO_GROUPS = [   // first match wins: more specific groups first
  ["Chickens & pets", /chicken|poultry|\bhens?\b|\bducks?\b|\bpets?\b|leg rings|fake eggs|nest box|feeder|\bcoop\b|\bbirds?\b/i],
  ["Tools & soldering", /solder|rosin|tweezer|plier|cutter|nipper|stripper|multimeter|tester|screwdriver|\bbits?\b|torx|hex key|spanner|wrench|\bflux\b|heat ?gun|hot air|preheat|station|\bmat\b|\bjig\b|clamp|crimp(ing)? (tool|plier)|endoscope|mandrel|deburr|test leads?|wishful|magnif|microscope|telescope|helping hand|desolder|\bwick\b|tools?\b/i],
  ["Phone, computer & AV", /iphone|samsung|galaxy|\bpixel\b|phone|tempered glass|screen protector|lightning|usb hub|laptop|tablet|ipad|airpods|\bgpu\b|\bcpu\b|asus|lenovo|\bdell\b|\bvga\b|hdmi|ypbpr|rgbs/i],
  ["Dev boards & displays", /esp32|esp8266|esp-|wt32|arduino|raspberry|orange ?pi|\bpico\b|stm32|devkit|dev(elopment)?[ -]?board|lilygo|heltec|t-display|wio|meshtastic|lora|\blcd\b|oled|amoled|\btft\b|display|e-?paper|e-?ink|touch ?screen/i],
  ["Modules & power", /module|\bmod\b|sensor|\brtc\b|relay|buck|boost|converter|step ?(down|up)|power supply|smps|charger|\bbms\b|amplifier|transmitter|receiver|ds1307|ds3231|ina219|hx711|driver board|regulator|batter(y|ies)|18650|21700|lithium|li-?ion|igniter|high voltage/i],
  ["Connectors & cables", /connector|\bjst\b|\bxh\b|\bph ?2|dupont|cable|\bwire\b|silicone wire|plug|socket|\bjack\b|terminal|magnetic|header|\brca\b|\bxlr\b|adapter|extension lead|pre-?crimped|pogo|signal line/i],
  ["Components", /diode|schottky|resistor|capacitor|transistor|mosfet|rectifier|zener|thermistor|\bntc\b|\bfuse\b|\bleds?\b|led strip|ws2812|inductor|crystal|oscillator|\bic\b|optocoupler|potentiometer|switch|button|buzzer|varistor|triac|thyristor|1n\d{4}|\bpcb\b|interposer|breakout|\bsmd\b/i],
  ["Phone, computer & AV", /\bcase\b|keyboard|mouse/i],      // weak words: only when nothing above matched
  ["Appliance parts", /vacuum|motor|carbon brush|\bbrushes\b|filter|appliance|pump|heater|heating element|thermostat|washing|dryer|\bfans?\b|blender|kettle|gasket/i],
];
export const NOT_NAMED = "Not named (several items)";
export const OTHER = "Other";

/** The group an item goes in from its name and option (before you move it). */
export function autoGroup(title, variant = "") {
  for (const text of [title, variant]) {          // the name decides; the option only when the name says nothing
    for (const [name, re] of AUTO_GROUPS) if (re.test(text)) return name;
  }
  return OTHER;
}

/** One checklist row per item (one per order when the items aren't named). Paid and cancelled orders both listed. */
export function checklistRows(res) {
  const rows = [];
  for (const o of res.orders) {
    const base = {ref: o.ref, date: o.date, store: o.store, status: o.status, cancelled: o.flags.includes("cancelled"), currency: o.currency, page: o.page};
    if (!o.items.length) {
      rows.push({...base, key: `${o.ref}#order`, title: `Order ${o.ref}: several items, not named on the Orders page`, variant: "",
        qty: null, unitPrice: null, amount: o.total, auto: NOT_NAMED});
      continue;
    }
    o.items.forEach((i, k) => rows.push({...base, key: `${o.ref}#${k}`, title: i.title, variant: i.variant, qty: i.qty, unitPrice: i.unitPrice,
      amount: i.amount, auto: autoGroup(i.title, i.variant)}));
  }
  return rows;
}

export const emptyTags = () => ({v: 1, items: {}, groups: [], staff: [], jobs: []});

export function groupOf(row, tags) { return tags.items[row.key]?.group || row.auto; }

/** Checklist as CSV (one row per item, with group, tick, job and staff). */
export function checklistCsv(res, tags) {
  const q = v => { const s = String(v ?? ""); return /[",\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s; };
  const c = v => v == null ? "" : (v / 100).toFixed(2);
  const out = [["group", "ticked", "job number", "staff", "item", "option", "qty", "unit price", "amount", "currency", "order date", "order number", "store", "status"]];
  const rows = checklistRows(res).sort((a, b) => groupOf(a, tags).localeCompare(groupOf(b, tags)) || (a.date < b.date ? 1 : -1));
  for (const r of rows) {
    const t = tags.items[r.key] || {};
    out.push([groupOf(r, tags), t.done ? "yes" : "", t.job || "", t.staff || "", r.title, r.variant, r.qty ?? "", c(r.unitPrice), c(r.amount), r.currency,
      r.date, r.ref, r.store, r.status]);
  }
  return "﻿" + out.map(r => r.map(q).join(",")).join("\r\n") + "\r\n";
}

const CSS = `
.cl-bar { display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin-bottom:12px; }
.cl-bar input[type=search], .cl-bar select { padding:7px 9px; border-radius:8px; border:1px solid var(--line); background:var(--card); color:inherit; font:inherit; }
.cl-bar input[type=search] { flex:1 1 180px; min-width:150px; }
.cl-bar label { font-size:13px; color:var(--soft, var(--mute)); display:inline-flex; gap:5px; align-items:center; }
.cl-prog { display:flex; align-items:center; gap:10px; margin-bottom:12px; font-size:13px; color:var(--soft, var(--mute)); }
.cl-prog div { flex:1; height:8px; border-radius:6px; background:var(--line); overflow:hidden; }
.cl-prog div i { display:block; height:100%; background:var(--accent); }
.cl-group { background:var(--card); border:1px solid var(--line); border-radius:12px; margin-bottom:12px; overflow:hidden; }
.cl-group > summary { list-style:none; cursor:pointer; display:flex; align-items:center; gap:10px; padding:10px 14px; font-weight:700; }
.cl-group > summary::-webkit-details-marker { display:none; }
.cl-group > summary::before { content:"▸"; color:var(--faint, var(--mute)); transition:transform .15s; }
.cl-group[open] > summary::before { transform:rotate(90deg); }
.cl-group > summary small { font-weight:400; color:var(--soft, var(--mute)); margin-left:auto; }
.cl-group.cl-over { outline:2px dashed var(--accent); }
.cl-row { display:grid; grid-template-columns:28px minmax(0,1fr) 150px 110px 130px; gap:8px 10px; align-items:center; padding:9px 14px; border-top:1px solid var(--line); }
.cl-row.done .cl-name { opacity:.55; text-decoration:line-through; }
.cl-row.cancelled .cl-name::after { content:" (cancelled)"; color:var(--warn); font-size:12px; }
.cl-row input[type=checkbox] { width:20px; height:20px; accent-color:var(--accent); cursor:pointer; }
.cl-name { font-size:14px; min-width:0; }
.cl-name small { display:block; color:var(--soft, var(--mute)); font-size:12px; }
.cl-row input[type=text], .cl-row select { width:100%; padding:6px 8px; border-radius:7px; border:1px solid var(--line); background:var(--bg2, #fff); color:inherit; font:inherit; font-size:13px; }
.cl-row .cl-drag { cursor:grab; }
.cl-tagged { font-size:11px; padding:1px 7px; border-radius:10px; background:var(--accent); color:var(--accent-ink, #fff); margin-left:6px; }
.cl-empty { color:var(--faint, var(--mute)); padding:30px; text-align:center; }
@media (max-width: 760px) {
  .cl-row { grid-template-columns:28px minmax(0,1fr) minmax(0,1fr); grid-template-areas:"tick name name" ". job staff" ". grp grp"; }
  .cl-row > :nth-child(1) { grid-area:tick; } .cl-row > :nth-child(2) { grid-area:name; } .cl-row > :nth-child(3) { grid-area:grp; }
  .cl-row > :nth-child(4) { grid-area:job; } .cl-row > :nth-child(5) { grid-area:staff; }
}`;

export function createChecklist({el, store, getRes, extraButtons = ""}) {
  if (!document.getElementById("cl-css")) {
    const st = document.createElement("style"); st.id = "cl-css"; st.textContent = CSS; document.head.appendChild(st);
  }
  let tags = emptyTags(), loaded = false;
  const view = {q: "", hideDone: false, job: "", staff: "", open: {}};
  const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;"}[c]));
  const money = c => c == null ? "" : "$" + (c / 100).toLocaleString("en-NZ", {minimumFractionDigits: 2, maximumFractionDigits: 2});
  let saveTimer = null;
  const save = () => { clearTimeout(saveTimer); saveTimer = setTimeout(() => store.save(tags).catch(e => alert("Couldn't save: " + e.message)), 250); };
  const remember = (list, v) => { if (v && !tags[list].includes(v)) { tags[list].push(v); tags[list].sort((a, b) => a.localeCompare(b, undefined, {numeric: true})); } };
  const setItem = (key, patch) => {
    const t = {...(tags.items[key] || {}), ...patch};
    for (const k of Object.keys(t)) if (t[k] === "" || t[k] === false || t[k] == null) delete t[k];
    if (Object.keys(t).length) tags.items[key] = t; else delete tags.items[key];
    if (patch.job) remember("jobs", patch.job);
    if (patch.staff) remember("staff", patch.staff);
    save();
  };

  async function render() {
    if (!loaded) { try { tags = {...emptyTags(), ...(await store.load() || {})}; } catch { tags = emptyTags(); } loaded = true; }
    const res = getRes();
    if (!res || !res.orders.length) { el.innerHTML = '<div class="cl-empty">Open a PDF first.</div>'; return; }
    const all = checklistRows(res);
    const groupNames = [...new Set([...AUTO_GROUPS.map(g => g[0]), OTHER, NOT_NAMED, ...tags.groups, ...all.map(r => groupOf(r, tags))])];
    const q = view.q.toLowerCase();
    const shown = all.filter(r => {
      const t = tags.items[r.key] || {};
      if (view.hideDone && t.done) return false;
      if (view.job && (view.job === "(none)" ? t.job : t.job !== view.job)) return false;
      if (view.staff && (view.staff === "(none)" ? t.staff : t.staff !== view.staff)) return false;
      return !q || [r.title, r.variant, r.store, r.ref, t.job, t.staff, groupOf(r, tags)].join(" ").toLowerCase().includes(q);
    });
    const done = all.filter(r => tags.items[r.key]?.done).length;
    const opt = (list, cur, none) => `<option value="">${none}</option><option value="(none)"${cur === "(none)" ? " selected" : ""}>(no tag yet)</option>` +
      list.map(v => `<option${v === cur ? " selected" : ""}>${esc(v)}</option>`).join("");
    el.innerHTML = `
      <div class="cl-bar">
        <input type="search" id="clQ" placeholder="🔎 Find an item, store, job or staff…" value="${esc(view.q)}">
        <select id="clJob" title="Show one job">${opt(tags.jobs, view.job, "All jobs")}</select>
        <select id="clStaff" title="Show one staff member">${opt(tags.staff, view.staff, "All staff")}</select>
        <label><input type="checkbox" id="clHide"${view.hideDone ? " checked" : ""}> Hide ticked</label>
        <button id="clNewGroup">＋ New group</button>
        <button id="clCsv">⬇ Checklist CSV</button>${extraButtons}
      </div>
      <div class="cl-prog"><span>✅ ${done} of ${all.length} ticked</span><div><i style="width:${all.length ? 100 * done / all.length : 0}%"></i></div></div>
      <datalist id="clJobs">${tags.jobs.map(v => `<option value="${esc(v)}">`).join("")}</datalist>
      <datalist id="clStaffs">${tags.staff.map(v => `<option value="${esc(v)}">`).join("")}</datalist>
      ${groupNames.map(g => {
        const rows = shown.filter(r => groupOf(r, tags) === g).sort((a, b) => a.date < b.date ? 1 : -1);
        const inGroup = all.filter(r => groupOf(r, tags) === g);
        if (!inGroup.length && !tags.groups.includes(g)) return "";
        if (!rows.length && (view.q || view.job || view.staff || view.hideDone)) return "";     // filtering: only groups with matches
        const gDone = inGroup.filter(r => tags.items[r.key]?.done).length;
        const total = inGroup.reduce((a, r) => a + (r.cancelled ? 0 : (r.amount || 0)), 0);
        const open = view.open[g] ?? true;
        return `<details class="cl-group" data-g="${esc(g)}"${open ? " open" : ""}><summary>${esc(g)} <small>${gDone}/${inGroup.length} ticked · ${money(total)}</small></summary>
          ${rows.map(r => {
            const t = tags.items[r.key] || {};
            return `<div class="cl-row${t.done ? " done" : ""}${r.cancelled ? " cancelled" : ""}" data-k="${esc(r.key)}" draggable="true">
              <input type="checkbox" data-f="done"${t.done ? " checked" : ""} title="Received / checked">
              <div class="cl-name cl-drag" title="Drag onto another group to move it">${esc(r.title)}${r.variant ? ` <i>(${esc(r.variant)})</i>` : ""}
                <small>${r.qty != null ? `${r.qty} × ${money(r.unitPrice)} = ${money(r.amount)}` : money(r.amount)} · ${esc(r.store)} · ${r.date} · #${esc(r.ref)}</small></div>
              <select data-f="group" title="Group">${groupNames.map(n => `<option${n === g ? " selected" : ""}>${esc(n)}</option>`).join("")}</select>
              <input type="text" data-f="job" list="clJobs" placeholder="Job #" value="${esc(t.job || "")}" title="Job number">
              <input type="text" data-f="staff" list="clStaffs" placeholder="Staff" value="${esc(t.staff || "")}" title="Staff member">
            </div>`;
          }).join("") || `<div class="cl-row" style="display:block;color:var(--faint, var(--mute))">${inGroup.length ? "Nothing here matches." : "Empty: drag items here or pick this group on an item."}</div>`}
        </details>`;
      }).join("")}`;

    const $ = s => el.querySelector(s);
    $("#clQ").oninput = e => { view.q = e.target.value; const pos = e.target.selectionStart; render().then(() => { const i = el.querySelector("#clQ"); i.focus(); i.setSelectionRange(pos, pos); }); };
    $("#clJob").onchange = e => { view.job = e.target.value; render(); };
    $("#clStaff").onchange = e => { view.staff = e.target.value; render(); };
    $("#clHide").onchange = e => { view.hideDone = e.target.checked; render(); };
    $("#clNewGroup").onclick = () => {
      const n = (prompt("Name for the new group (e.g. Stock, Returns, Job 1234 parts):") || "").trim();
      if (n && !groupNames.includes(n)) { tags.groups.push(n); save(); render(); }
    };
    $("#clCsv").onclick = () => {
      const a = document.createElement("a");
      a.href = URL.createObjectURL(new Blob([checklistCsv(getRes(), tags)], {type: "text/csv"}));
      a.download = "AliExpress checklist - " + (getRes().file || "orders").replace(/\.pdf.*$/i, "") + ".csv";
      document.body.appendChild(a); a.click(); a.remove();
    };
    el.querySelectorAll(".cl-group").forEach(d => d.addEventListener("toggle", () => { view.open[d.dataset.g] = d.open; }));
    el.querySelectorAll(".cl-row[data-k]").forEach(row => {
      const key = row.dataset.k;
      row.querySelector('[data-f="done"]').onchange = e => { setItem(key, {done: e.target.checked}); render(); };
      row.querySelector('[data-f="group"]').onchange = e => { setItem(key, {group: e.target.value === all.find(r => r.key === key).auto ? "" : e.target.value}); render(); };
      for (const f of ["job", "staff"]) {
        const inp = row.querySelector(`[data-f="${f}"]`);
        inp.onchange = e => { setItem(key, {[f]: e.target.value.trim()}); render(); };
        inp.onkeydown = e => { if (e.key === "Enter") e.target.blur(); };
      }
      row.addEventListener("dragstart", e => { e.dataTransfer.setData("text/aer-item", key); e.dataTransfer.effectAllowed = "move"; });
    });
    el.querySelectorAll(".cl-group").forEach(d => {
      d.addEventListener("dragover", e => { if (e.dataTransfer.types.includes("text/aer-item")) { e.preventDefault(); e.stopPropagation(); d.classList.add("cl-over"); } });
      d.addEventListener("dragleave", () => d.classList.remove("cl-over"));
      d.addEventListener("drop", e => {
        const key = e.dataTransfer.getData("text/aer-item");
        if (!key) return;
        e.preventDefault(); e.stopPropagation(); d.classList.remove("cl-over");
        const r = all.find(x => x.key === key);
        setItem(key, {group: d.dataset.g === r.auto ? "" : d.dataset.g}); render();
      });
    });
  }
  return {
    render,
    getTags: () => tags,
    async replaceTags(t) { tags = {...emptyTags(), ...t}; loaded = true; await store.save(tags); await render(); },
  };
}
