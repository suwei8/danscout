const $ = id => document.getElementById(id);
const game = $("game"), period = $("period");

async function jget(u){ const r = await fetch(u); return r.ok ? r.json() : null; }

let results = {}, postsData = [];

function renderChart(){
  const key = $("ptype").value;
  const cnt = {};
  for (const p of postsData){
    const s = (p.fields?.[key] || "") + "";
    for (const d of new Set(s.match(/\d/g) || [])) cnt[d] = (cnt[d]||0) + 1;
  }
  const rows = "0123456789".split("").map(d => [d, cnt[d]||0])
    .sort((a,b) => b[1]-a[1] || a[0].localeCompare(b[0]));
  const mx = Math.max(1, ...rows.map(r=>r[1]));
  $("ptype_n").textContent = `参与 ${postsData.filter(p=>(p.fields?.[key]||"")).length} 帖`;
  $("chart").innerHTML = rows.map(([d,v]) =>
    `<div class="col" title="${d}: ${v}帖"><span class="v">${v||""}</span>` +
    `<div class="vbar" style="height:${Math.round(v/mx*130)}px;opacity:${v?0.45+v/mx*0.55:0.12}"></div>` +
    `<span class="d">${d}</span></div>`).join("");
}
async function loadPeriods(){
  const [idx, res] = await Promise.all([
    jget(`data/${game.value}/index.json`),
    jget(`data/${game.value}/results.json`)]);
  results = res || {};
  period.innerHTML = "";
  (idx?.periods || []).forEach(p => {
    const o = document.createElement("option");
    o.value = o.textContent = p; period.appendChild(o);
  });
  load();
}

async function load(){
  const d = await jget(`data/${game.value}/${period.value}.json`);
  if (!d) { $("meta").textContent = "无数据"; return; }
  postsData = d.posts || [];
  renderChart();
  const kj = results[d.period];
  $("meta").innerHTML = `第${d.period}期 · ${d.post_count}帖 · ` +
    (kj ? `开奖 <b style="color:#d33;font-size:18px;letter-spacing:3px">${kj}</b>` : `<span style="color:#888">未开奖</span>`) +
    ` · 采集于 ${d.fetched_at}`;



  const tb = document.querySelector("#posts tbody");
  tb.innerHTML = "";
  for (const p of d.posts){
    const f = p.fields || {};
    const tr = document.createElement("tr");
    tr.innerHTML = `<td><a href="${p.url}" target="_blank">${p.predictor}</a><div class="meta">${p.author!==p.predictor?p.author:""} ${p.board}</div></td>` +
      [f.dutan,f.shuangdan,f.sandan,f.ma5,f.ma6,f.shama,f.hezhi,f.kuadu]
        .map(x=>`<td class="mono">${x||""}</td>`).join("") +
      `<td>${(f.zuxuan||[]).length||""}</td><td>${(f.zhixuan||[]).length||""}</td>`;
    tr.onclick = () => alert(p.title+"\n\n"+(p.text||"").slice(0,800));
    tb.appendChild(tr);
  }

  const zx = {};
  d.posts.forEach(p => (p.fields?.zhixuan||[]).forEach(n => zx[n]=(zx[n]||0)+1));
  const hot = Object.entries(zx).filter(([,c])=>c>=3).sort((a,b)=>b[1]-a[1]);
  const all = Object.keys(zx).sort();
  $("zxlist").innerHTML =
    `<div class="meta">被≥3帖推荐的（注后×次数）</div>` +
    hot.map(([n,c])=>`<span class="num">${n}×${c}</span>`).join("") +
    `<div class="meta" style="margin-top:10px">全部直选（${all.length}注去重）</div>` +
    `<div class="mono" style="font-size:12px;line-height:1.9">${all.join(" ")}</div>`;
}

game.onchange = loadPeriods;
period.onchange = load;
$("ptype").onchange = renderChart;
loadPeriods();
