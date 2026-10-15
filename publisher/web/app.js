"use strict";
const $ = (s, r = document) => r.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmtN = n => (n == null ? "-" : Number(n).toLocaleString("ko-KR"));
let S = null;            // /api/state
let tab = "schedule", subCat = "science", statFmt = "";

async function api(method, path, body, raw) {
  const opt = {method, headers: {"X-Requested-With": "yt-publisher"}};
  if (raw) { opt.body = raw; } else if (body !== undefined) { opt.body = JSON.stringify(body); opt.headers["Content-Type"] = "application/json"; }
  const r = await fetch(path, opt);
  let d = null; try { d = await r.json(); } catch (e) {}
  if (!r.ok) { const err = new Error((d && d.error) || "요청에 실패했습니다"); err.data = d; throw err; }
  return d;
}
function toast(m) { const t = $("#toast"); t.textContent = m; t.classList.add("show"); clearTimeout(toast.t); toast.t = setTimeout(() => t.classList.remove("show"), 3200); }
async function act(fn, ok) { try { const r = await fn(); if (ok) toast(ok); return r; } catch (e) { toast(e.message); throw e; } }
const catName = c => (S.shorts_categories[c] || (c === "longform" ? "롱폼" : c || ""));
const fmtAt = iso => iso ? iso.replace("T", " ").slice(0, 16) : "";

async function loadState() {
  S = await api("GET", "/api/state");
  const b = $("#banner");
  b.hidden = false;
  if (S.settings.mode === "live") { b.className = "live"; b.textContent = "실제 발행 모드 — 연결된 유튜브 채널에 업로드됩니다"; }
  else { b.className = "demo"; b.textContent = "데모 모드 — 가짜 업로드와 가짜 조회수로 화면을 시험하는 중입니다. 실제로는 아무것도 올라가지 않습니다 (설정에서 변경)"; }
  $("#tick").textContent = S.last_tick ? "마지막 점검 " + fmtAt(S.last_tick) : "";
}

// ---------- 편성표 ----------
async function viewSchedule() {
  const g = await api("GET", "/api/schedule?days=7");
  const today = g.days[0].date;
  let h = `<div class="row"><h2 class="grow">앞으로 7일 (${esc(g.timezone)})</h2><button id="run">지금 점검</button></div>`;
  h += `<div class="grid"><table><tr><th></th>${g.days.map(d => `<th class="${d.date === today ? "today" : ""}">${d.date.slice(5)} (${d.weekday})</th>`).join("")}</tr>`;
  for (const t of g.times) {
    h += `<tr><td class="t">${t}</td>`;
    for (const d of g.days) {
      const c = d.cells[t];
      h += `<td><div class="cell ${c.past ? "past" : ""}">` + c.videos.map(chip).join("") + `</div></td>`;
    }
    h += "</tr>";
  }
  h += "</table></div>";
  if (g.custom.length) h += `<h3>슬롯 밖 시각으로 예약된 영상</h3>` + g.custom.map(chip).join("");
  const drafts = (await api("GET", "/api/videos?status=draft")).length;
  h += `<p class="mute">초안 ${drafts}개가 대기 중입니다. 쇼츠·롱폼 탭에서 영상을 올리고 '예약'을 누르면 빈 슬롯에 자동으로 들어갑니다.</p>`;
  $("#view").innerHTML = h;
  $("#run").onclick = () => act(() => api("POST", "/api/run", {}), "점검했습니다").then(render);
  document.querySelectorAll("[data-vid]").forEach(b => b.onclick = () => openVideo(+b.dataset.vid));
}
function chip(v) {
  const k = v.format === "longform" ? "longform" : v.category;
  return `<button class="chip cat-${esc(k)}" data-vid="${v.id}"><b>${esc(v.title || "(제목 없음)")}</b><small>${esc(catName(k))} · ${esc(S.status_label[v.status] || v.status)}</small></button>`;
}

// ---------- 영상 목록 ----------
async function viewList(fmt) {
  let cat = "";
  let h = "";
  if (fmt === "longform" && !S.settings.longform.enabled)
    h += `<div class="card"><b>롱폼은 아직 꺼져 있습니다.</b><p class="mute">폴더와 설정만 준비해 둔 상태입니다. 작업이 시작되면 설정 탭에서 '롱폼 사용'을 켜세요. 그 전에는 예약할 수 없습니다.</p></div>`;
  if (fmt === "shorts") {
    h += `<div class="sub">` + Object.entries(S.shorts_categories).map(([k, n]) => `<button class="cat-${k} ${k === subCat ? "on" : ""}" data-sub="${k}">${esc(n)}</button>`).join("") + `</div>`;
    cat = subCat;
  }
  h += `<div class="drop" id="drop">영상을 여기로 끌어다 놓거나 <label style="display:inline;color:var(--ink);text-decoration:underline;cursor:pointer">파일 선택<input id="file" type="file" multiple accept=".mp4,.mov,.webm,.m4v" hidden></label> (mp4·mov·webm·m4v)<div id="prog"></div></div>`;
  h += `<div class="row"><span class="mute grow">폴더로 넣기: ${esc(S.inbox_dir)}/${fmt}${cat ? "/" + cat : ""}</span><button id="scan">폴더 새로고침</button></div>`;
  const vs = await api("GET", `/api/videos?format=${fmt}${cat ? "&category=" + cat : ""}`);
  if (!vs.length) h += `<div class="card mute">아직 영상이 없습니다. 위에 영상을 올려 보세요.</div>`;
  else {
    h += `<table class="list"><tr><th>제목</th><th>상태</th><th>공개 예정</th><th>조회수</th><th></th></tr>`;
    for (const v of vs) {
      h += `<tr class="click" data-vid="${v.id}"><td><span class="dot" style="background:var(--c-${fmt === "longform" ? "longform" : v.category})"></span>${esc(v.title || v.file_name)}${v.errors.length ? ` <span class="pill failed">확인 필요 ${v.errors.length}</span>` : ""}</td>
      <td><span class="pill ${v.status}">${esc(v.status_label)}</span></td><td>${fmtAt(v.publish_at)}</td><td class="vw" data-id="${v.id}">-</td>
      <td>${v.status === "draft" ? `<button data-q="${v.id}">예약</button>` : ""}</td></tr>`;
    }
    h += "</table>";
  }
  $("#view").innerHTML = h;
  document.querySelectorAll("[data-sub]").forEach(b => b.onclick = () => { subCat = b.dataset.sub; render(); });
  document.querySelectorAll("tr[data-vid]").forEach(r => r.onclick = e => { if (!e.target.closest("button")) openVideo(+r.dataset.vid); });
  document.querySelectorAll("[data-q]").forEach(b => b.onclick = () => queueVideo(+b.dataset.q));
  $("#scan").onclick = () => act(() => api("POST", "/api/inbox/scan", {}), "폴더를 확인했습니다").then(render);
  const drop = $("#drop");
  drop.ondragover = e => { e.preventDefault(); drop.classList.add("over"); };
  drop.ondragleave = () => drop.classList.remove("over");
  drop.ondrop = e => { e.preventDefault(); drop.classList.remove("over"); uploadFiles(e.dataTransfer.files, fmt, cat); };
  $("#file").onchange = e => uploadFiles(e.target.files, fmt, cat);
  api("GET", "/api/stats/overview?format=" + fmt).then(o => o.videos.forEach(r => { const c = document.querySelector(`.vw[data-id="${r.id}"]`); if (c) c.textContent = fmtN(r.views); })).catch(() => {});
}
function uploadFiles(files, fmt, cat) {
  const list = [...files]; if (!list.length) return;
  let i = 0;
  const next = () => {
    if (i >= list.length) { toast("업로드를 마쳤습니다"); render(); return; }
    const f = list[i++];
    const x = new XMLHttpRequest();
    x.open("POST", `/api/upload?format=${fmt}&category=${cat || ""}&name=${encodeURIComponent(f.name)}`);
    x.setRequestHeader("X-Requested-With", "yt-publisher");
    x.upload.onprogress = e => { if (e.lengthComputable) $("#prog").innerHTML = `${esc(f.name)} (${i}/${list.length}) <div class="bar"><i style="width:${(e.loaded / e.total * 100).toFixed(0)}%"></i></div>`; };
    x.onload = () => { if (x.status >= 400) { let m = "업로드 실패"; try { m = JSON.parse(x.responseText).error; } catch (e) {} toast(f.name + ": " + m); } else { try { if (JSON.parse(x.responseText).duplicate) toast(f.name + ": 이미 등록된 영상입니다"); } catch (e) {} } next(); };
    x.onerror = () => { toast("업로드 실패"); next(); };
    x.send(f);
  };
  next();
}
async function queueVideo(id) {
  try { await api("POST", `/api/videos/${id}/queue`, {}); toast("예약했습니다"); render(); }
  catch (e) { toast((e.data && e.data.errors ? e.data.errors.join(" / ") : e.message)); openVideo(id); }
}

// ---------- 영상 상세/수정 ----------
async function openVideo(id) {
  const v = await api("GET", "/api/videos/" + id);
  const ro = v.status === "uploaded" || v.status === "published";
  const d = $("#dlg");
  const catSel = v.format === "shorts" ? `<label>카테고리</label><select id="f_cat" ${ro ? "disabled" : ""}>${Object.entries(S.shorts_categories).map(([k, n]) => `<option value="${k}" ${k === v.category ? "selected" : ""}>${esc(n)}</option>`).join("")}</select>` : "";
  d.innerHTML = `<h2>${esc(v.file_name)}</h2>
  <p><span class="pill ${v.status}">${esc(v.status_label)}</span> ${v.publish_at ? "공개 예정 " + fmtAt(v.publish_at) : ""} ${v.youtube_id ? `· <a href="https://youtube.com/watch?v=${esc(v.youtube_id)}" target="_blank" rel="noopener">유튜브에서 보기</a>` : ""}</p>
  ${v.error ? `<p class="errs">${esc(v.error)}</p>` : ""}
  ${v.errors.length ? `<ul class="errs">${v.errors.map(e => `<li>${esc(e)}</li>`).join("")}</ul>` : ""}
  ${v.warnings.length ? `<ul class="warns">${v.warnings.map(e => `<li>${esc(e)}</li>`).join("")}</ul>` : ""}
  ${catSel}
  <label>제목 (100자 이내)</label><input type="text" id="f_title" maxlength="100" value="${esc(v.title)}" ${ro ? "disabled" : ""}>
  <label>설명</label><textarea id="f_desc" ${ro ? "disabled" : ""}>${esc(v.description)}</textarea>
  <label>태그 (쉼표로 구분)</label><input type="text" id="f_tags" value="${esc((v.tags || []).join(", "))}" ${ro ? "disabled" : ""}>
  <label class="chk"><input type="checkbox" id="f_syn" ${v.synthetic ? "checked" : ""} ${ro ? "disabled" : ""}>AI로 만들었거나 합성한 장면이 있습니다 (유튜브 '변경/합성 콘텐츠' 공개)</label>
  ${v.category === "shopping" ? `<label class="chk"><input type="checkbox" id="f_aff" ${v.affiliate ? "checked" : ""} ${ro ? "disabled" : ""}>제휴 링크·협찬이 포함된 영상입니다 (설명에 '광고/협찬/제휴' 문구 필요)</label>` : ""}
  ${v.category === "drama_movie" ? `<label class="chk"><input type="checkbox" id="f_rts" ${v.rights_confirmed ? "checked" : ""} ${ro ? "disabled" : ""}>이 영상에 쓴 장면·음악의 사용 권리를 확인했습니다 (저작권 신고·수익 제한 위험은 본인 책임)</label>` : ""}
  <div class="row" style="margin-top:16px">
    ${ro ? "" : `<button class="primary" id="b_save">저장</button>`}
    ${v.status === "draft" || v.status === "failed" ? `<button id="b_queue">저장하고 예약</button>` : ""}
    ${v.status === "queued" ? `<button id="b_unq">예약 취소</button>` : ""}
    ${ro ? "" : `<button class="danger" id="b_del">삭제</button>`}
    <span class="grow"></span><button id="b_close">닫기</button></div>
  ${v.status === "published" || v.status === "uploaded" ? `<h3>조회수 변화</h3><div id="vstat" class="mute">불러오는 중…</div>` : ""}`;
  d.showModal();
  const save = async () => {
    const body = {title: $("#f_title").value, description: $("#f_desc").value, tags: $("#f_tags").value.split(",").map(s => s.trim()).filter(Boolean), synthetic: $("#f_syn").checked};
    if ($("#f_cat")) body.category = $("#f_cat").value;
    if ($("#f_aff")) body.affiliate = $("#f_aff").checked;
    if ($("#f_rts")) body.rights_confirmed = $("#f_rts").checked;
    await act(() => api("PUT", "/api/videos/" + id, body));
  };
  $("#b_close").onclick = () => { d.close(); render(); };
  if ($("#b_save")) $("#b_save").onclick = async () => { await save(); toast("저장했습니다"); d.close(); render(); };
  if ($("#b_queue")) $("#b_queue").onclick = async () => { await save(); try { await api("POST", `/api/videos/${id}/queue`, {}); toast("예약했습니다"); d.close(); render(); } catch (e) { toast(e.data && e.data.errors ? e.data.errors.join(" / ") : e.message); openVideo(id); } };
  if ($("#b_unq")) $("#b_unq").onclick = async () => { await act(() => api("POST", `/api/videos/${id}/unqueue`, {}), "예약을 취소했습니다"); d.close(); render(); };
  if ($("#b_del")) $("#b_del").onclick = async () => { if (confirm("이 영상을 목록에서 삭제할까요? (원본 파일은 지워지지 않습니다)")) { await act(() => api("DELETE", "/api/videos/" + id), "삭제했습니다"); d.close(); render(); } };
  if ($("#vstat")) api("GET", "/api/stats/video/" + id).then(r => {
    const s = r.summary;
    $("#vstat").innerHTML = `조회 ${fmtN(s.views)} · 24시간 ${fmtN(s.views_24h)} · 7일 ${fmtN(s.views_7d)} · 좋아요 ${fmtN(s.likes)}${s.like_rate != null ? " (" + s.like_rate + "%)" : ""} · 댓글 ${fmtN(s.comments)}` + lineChart(r.snapshots.map(x => ({x: x.captured_at, y: x.views})));
  }).catch(() => {});
}

// ---------- 통계 ----------
function lineChart(pts, color = "var(--ink)") {
  if (pts.length < 2) return `<p class="mute">기록이 2번 이상 쌓이면 그래프가 나옵니다.</p>`;
  const W = 600, H = 200, p = 30, max = Math.max(...pts.map(q => q.y), 1);
  const X = i => p + i * (W - 2 * p) / (pts.length - 1), Y = y => H - p - y / max * (H - 2 * p);
  const path = pts.map((q, i) => (i ? "L" : "M") + X(i).toFixed(1) + " " + Y(q.y).toFixed(1)).join("");
  return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="조회수 그래프"><path d="${path}" fill="none" stroke="${color}" stroke-width="2"/>
  <text x="4" y="${Y(max) + 4}">${fmtN(max)}</text><text x="4" y="${H - p + 4}">0</text>
  <text x="${p}" y="${H - 8}">${esc(String(pts[0].x).slice(5, 10))}</text><text x="${W - p - 24}" y="${H - 8}">${esc(String(pts[pts.length - 1].x).slice(5, 10))}</text></svg>`;
}
async function viewStats() {
  const q = statFmt ? "?format=" + statFmt : "";
  const [o, ser] = await Promise.all([api("GET", "/api/stats/overview" + q), api("GET", "/api/stats/series?days=14" + (statFmt ? "&format=" + statFmt : ""))]);
  let h = `<div class="row"><h2 class="grow">영상 통계</h2><select id="sf" style="width:auto"><option value="">전체</option><option value="shorts">쇼츠</option><option value="longform">롱폼</option></select><button id="coll">지금 수집</button></div>`;
  h += `<div class="kpis"><div class="kpi"><b>${fmtN(o.total.videos)}</b>공개된 영상</div><div class="kpi"><b>${fmtN(o.total.views)}</b>전체 조회수</div><div class="kpi"><b>${fmtN(o.total.views_24h)}</b>최근 24시간</div><div class="kpi"><b>${fmtN(o.total.likes)}</b>좋아요</div></div>`;
  h += `<h3>하루 조회수 증가 (최근 14일)</h3>` + lineChart(ser.map(r => ({x: r.date, y: r.views})), "var(--c-science)");
  h += `<h3>카테고리별</h3><table class="list"><tr><th>구분</th><th>영상</th><th>조회수</th><th>24시간</th><th>평균 조회</th></tr>` +
    Object.entries(o.by_category).map(([k, g]) => `<tr><td><span class="dot" style="background:var(--c-${k})"></span>${esc(catName(k))}</td><td>${g.videos}</td><td>${fmtN(g.views)}</td><td>${fmtN(g.views_24h)}</td><td>${fmtN(g.avg_views)}</td></tr>`).join("") + `</table>`;
  if (!Object.keys(o.by_category).length) h += `<p class="mute">공개된 영상이 생기면 여기에 쌓입니다.</p>`;
  h += `<h3>잘 나온 영상</h3>` + (o.top.length ? `<table class="list"><tr><th>제목</th><th>24시간</th><th>7일</th><th>전체</th><th>좋아요율</th></tr>${o.top.map(r => `<tr class="click" data-vid="${r.id}"><td>${esc(r.title)}</td><td>${fmtN(r.views_24h)}</td><td>${fmtN(r.views_7d)}</td><td>${fmtN(r.views)}</td><td>${r.like_rate ?? "-"}%</td></tr>`).join("")}</table>` : `<p class="mute">아직 없습니다.</p>`);
  h += `<p class="mute">수집 간격은 공개 후 48시간까지 ${S.settings.stats_interval_min}분, 14일까지 6시간, 이후 하루 1번입니다. 마지막 수집: ${fmtAt(o.last_collected_at) || "없음"}. 유튜브는 2026-08-24부터 조회수 집계 기준을 바꿔서, 그 전후 숫자를 그대로 비교하면 어긋날 수 있습니다.</p>`;
  $("#view").innerHTML = h;
  $("#sf").value = statFmt; $("#sf").onchange = e => { statFmt = e.target.value; render(); };
  $("#coll").onclick = () => act(() => api("POST", "/api/run", {force_stats: true}), "수집했습니다").then(render);
  document.querySelectorAll("tr[data-vid]").forEach(r => r.onclick = () => openVideo(+r.dataset.vid));
}

// ---------- 설정 ----------
async function viewSettings() {
  const s = S.settings;
  const ch = S.channels;
  let h = `<h2>설정</h2><div class="card"><h3 style="margin-top:0">발행 방식</h3>
  <label class="chk"><input type="radio" name="mode" value="demo" ${s.mode !== "live" ? "checked" : ""}>데모 — 가짜 업로드·가짜 조회수로 화면만 시험</label>
  <label class="chk"><input type="radio" name="mode" value="live" ${s.mode === "live" ? "checked" : ""}>실제 발행 — 연결한 유튜브 채널에 업로드 (먼저 아래 연결을 마치세요)</label></div>`;
  h += `<div class="card"><h3 style="margin-top:0">유튜브 연결</h3>
  <p class="mute">구글 인증 파일(client_secret.json) ${S.has_secret ? "<b>올라가 있음</b>" : "<b>없음</b>"}. 발급 방법은 README의 '유튜브 연결' 부분을 따라 하세요.</p>
  <div class="row"><input type="file" id="sec" accept=".json" style="max-width:320px"><button id="secb">인증 파일 올리기</button></div>
  <h3>채널</h3>` + ch.map(c => `<div class="row"><b>${esc(c.name)}</b><span class="pill">${s.mode === "live" ? (c.authorized ? "연결됨" : "연결 안 됨") : "데모"}</span><button data-auth="${esc(c.id)}">구글 로그인</button><span class="mute" id="as_${esc(c.id)}">${S.auth[c.id] ? esc(S.auth[c.id].msg) : ""}</span></div>`).join("") +
  `<div class="row"><input type="text" id="cn" placeholder="채널 이름 추가 (예: 과학 채널)" style="max-width:260px"><button id="cadd">채널 추가</button></div>
  <h3>카테고리별 업로드 채널</h3>` + Object.entries(S.shorts_categories).map(([k, n]) => `<div class="row"><span style="width:120px"><span class="dot" style="background:var(--c-${k})"></span>${esc(n)}</span><select data-map="${k}" style="max-width:240px">${ch.map(c => `<option value="${esc(c.id)}" ${((s.channel_map || {})[k] || "default") === c.id ? "selected" : ""}>${esc(c.name)}</option>`).join("")}</select></div>`).join("") + `</div>`;
  h += `<div class="card"><h3 style="margin-top:0">예약 시각</h3>
  <label>쇼츠 시각 (쉼표로 구분, 24시간제)</label><input type="text" id="slots" value="${esc(s.shorts.slots.join(", "))}">
  <label>하루 업로드 상한 (유튜브 기본 한도는 하루 약 100개)</label><input type="number" id="cap" min="1" max="100" value="${s.daily_upload_cap}">
  <label>시간대</label><input type="text" id="tz" value="${esc(s.timezone)}">
  <h3>자동 예약</h3><p class="mute">검사를 통과한 새 영상을 알아서 예약합니다. 꺼 두면 직접 '예약'을 눌러야 합니다.</p>` +
  Object.entries(S.shorts_categories).map(([k, n]) => `<label class="chk"><input type="checkbox" data-auto="${k}" ${(s.auto_queue || []).includes(k) ? "checked" : ""}>${esc(n)}</label>`).join("") + `</div>`;
  h += `<div class="card"><h3 style="margin-top:0">롱폼</h3><label class="chk"><input type="checkbox" id="lf" ${s.longform.enabled ? "checked" : ""}>롱폼 사용 (작업이 시작되면 켜세요)</label>
  <label>롱폼 시각</label><input type="text" id="lfs" value="${esc(s.longform.slots.join(", "))}"></div>`;
  h += `<div class="row"><button class="primary" id="save">설정 저장</button><span class="mute">데이터 폴더: ${esc(S.data_dir)}</span></div>`;
  $("#view").innerHTML = h;
  $("#secb").onclick = async () => { const f = $("#sec").files[0]; if (!f) return toast("파일을 선택하세요"); await act(() => api("POST", "/api/client-secret", undefined, f), "인증 파일을 저장했습니다"); await loadState(); render(); };
  $("#cadd").onclick = async () => { const n = $("#cn").value.trim(); if (!n) return; await act(() => api("POST", "/api/channels", {id: n.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, "") || "ch" + Date.now(), name: n}), "추가했습니다"); await loadState(); render(); };
  document.querySelectorAll("[data-auth]").forEach(b => b.onclick = async () => { await act(() => api("POST", `/api/channels/${b.dataset.auth}/auth`, {}), "브라우저에서 구글 로그인을 완료하세요"); poll(b.dataset.auth); });
  $("#save").onclick = async () => {
    const times = v => v.split(",").map(x => x.trim()).filter(Boolean);
    const map = {}; document.querySelectorAll("[data-map]").forEach(e => map[e.dataset.map] = e.value);
    const body = {mode: document.querySelector("input[name=mode]:checked").value, timezone: $("#tz").value.trim(), daily_upload_cap: +$("#cap").value,
      shorts: {slots: times($("#slots").value)}, longform: {enabled: $("#lf").checked, slots: times($("#lfs").value)}, channel_map: map,
      auto_queue: [...document.querySelectorAll("[data-auto]:checked")].map(e => e.dataset.auto)};
    await act(() => api("PUT", "/api/settings", body), "저장했습니다"); await loadState(); render();
  };
}
function poll(cid) { const t = setInterval(async () => { await loadState(); const a = S.auth[cid]; const el = $("#as_" + cid); if (el && a) el.textContent = a.msg; if (!a || a.state !== "waiting") clearInterval(t); }, 2000); }

// ---------- 라우팅 ----------
async function render() {
  document.querySelectorAll("#tabs button").forEach(b => b.classList.toggle("on", b.dataset.tab === tab));
  try {
    await loadState();
    if (tab === "schedule") await viewSchedule();
    else if (tab === "shorts") await viewList("shorts");
    else if (tab === "longform") await viewList("longform");
    else if (tab === "stats") await viewStats();
    else await viewSettings();
  } catch (e) { $("#view").innerHTML = `<div class="card"><b>화면을 불러오지 못했습니다.</b><p class="mute">${esc(e.message)}</p></div>`; }
}
document.querySelectorAll("#tabs button").forEach(b => b.onclick = () => { tab = b.dataset.tab; render(); });
render();
setInterval(() => { if (!$("#dlg").open && tab !== "settings" && !document.querySelector("#prog .bar")) render(); }, 60000);
