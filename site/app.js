/* GitHub 热门监控站：读取 data/index.json 与 data/snapshots/*.json 渲染。 */

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const state = {
  index: null,          // {dates, latest, tracked, repo_url, site_url}
  snaps: {},            // date -> snapshot（内存缓存）
  currentDate: null,
  tab: 'trending',
  trendingSince: null,
  trendingLang: null,
  chart: null,
  historyRepos: [],
};

/* ---------- 工具 ---------- */

function esc(s) {
  return (s ?? '').toString().replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
}

function fmtStars(n) {
  if (n == null) return '-';
  if (n >= 1000) {
    const v = n / 1000;
    return (v >= 100 ? Math.round(v) : Math.round(v * 10) / 10) + 'k';
  }
  return String(n);
}

function cut(s, n) {
  s = (s ?? '').trim();
  return s.length > n ? s.slice(0, n) + '…' : s;
}

function ageDays(createdAt) {
  const t = Date.parse(createdAt);
  if (!t) return '?';
  return Math.max(0, Math.floor((Date.now() - t) / 86400000));
}

async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`${url} -> HTTP ${r.status}`);
  return r.json();
}

async function loadSnap(date) {
  if (!state.snaps[date]) state.snaps[date] = await fetchJSON(`data/snapshots/${date}.json`);
  return state.snaps[date];
}

const LANG_LABELS = {
  '': '全部', python: 'Python', typescript: 'TypeScript', rust: 'Rust', go: 'Go',
  javascript: 'JavaScript', java: 'Java', 'c++': 'C++', c: 'C', 'c#': 'C#',
  'jupyter-notebook': 'Jupyter', html: 'HTML', css: 'CSS', vue: 'Vue', swift: 'Swift', kotlin: 'Kotlin', zig: 'Zig',
};
const langLabel = slug => LANG_LABELS[slug] || (slug ? slug.charAt(0).toUpperCase() + slug.slice(1) : '全部');

/* ---------- 渲染 ---------- */

function repoCard(it, metaHtml) {
  return `<div class="repo-card">
    ${it.avatar ? `<img class="avatar" src="${esc(it.avatar)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">` : '<div class="avatar"></div>'}
    <div class="repo-main">
      <div class="repo-head">
        ${it.rank != null ? `<span class="rank">#${it.rank}</span>` : ''}
        <a class="repo-name" href="${esc(it.url)}" target="_blank" rel="noopener">${esc(it.full_name)}</a>
        ${it.language ? `<span class="lang-badge">${esc(it.language)}</span>` : ''}
      </div>
      ${it.description ? `<div class="repo-desc">${esc(cut(it.description, 120))}</div>` : ''}
      <div class="repo-meta">${metaHtml}</div>
    </div>
  </div>`;
}

const emptyHint = msg => `<div class="empty-hint">${esc(msg)}</div>`;

function renderTrending(snap) {
  const board = snap.trending || {};
  const sinces = Object.keys(board);
  if (!sinces.length) { $('#trending-list').innerHTML = emptyHint('本次未采集到 Trending 数据'); return; }
  const since = sinces.includes(state.trendingSince) ? state.trendingSince : sinces[0];
  state.trendingSince = since;
  const langs = board[since] || {};
  const slugs = Object.keys(langs);
  const slug = slugs.includes(state.trendingLang) ? state.trendingLang : slugs[0];
  state.trendingLang = slug;

  $('#since-select').innerHTML = sinces.map(s =>
    `<option value="${esc(s)}" ${s === since ? 'selected' : ''}>${s === 'daily' ? '日榜' : s === 'weekly' ? '周榜' : esc(s)}</option>`).join('');
  $('#lang-select').innerHTML = slugs.map(s =>
    `<option value="${esc(s)}" ${s === slug ? 'selected' : ''}>${esc(langLabel(s))}</option>`).join('');

  const items = langs[slug] || [];
  $('#trending-list').innerHTML = items.length
    ? items.map(it => repoCard(it, `⭐ ${fmtStars(it.stars)} · 今日 <span class="delta-up">+${it.period_stars ?? 0}</span>`)).join('')
    : emptyHint('暂无数据');
}

function renderRadar(snap) {
  const items = snap.radar || [];
  $('#radar-list').innerHTML = items.length
    ? items.map(it => repoCard(it, `⭐ ${fmtStars(it.stars)} · ${ageDays(it.created_at)} 天前创建`)).join('')
    : emptyHint('暂无数据');
}

function renderGainers(snap) {
  const rows = snap.gainers || [];
  if (!rows.length) {
    $('#gainers-wrap').innerHTML = emptyHint('暂无涨幅数据 —— 需要至少两次采样（6 小时），跑满一天后完整。');
    return;
  }
  const surgeSet = new Set((snap.surges || []).map(g => g.full_name));
  const body = rows.map(g => `
    <tr class="${surgeSet.has(g.full_name) ? 'surge' : ''}">
      <td><a href="${esc(g.url)}" target="_blank" rel="noopener">${esc(g.full_name)}</a></td>
      <td>${esc(g.language || '-')}</td>
      <td>⭐ ${fmtStars(g.stars)}</td>
      <td class="delta-up">+${g.delta_24h}</td>
      <td>${g.delta_6h == null ? '-' : `<span class="delta-up">+${g.delta_6h}</span>`}</td>
      <td class="muted">${esc(cut(g.description, 60))}</td>
    </tr>`).join('');
  $('#gainers-wrap').innerHTML = `
    <table class="data-table">
      <thead><tr><th>仓库</th><th>语言</th><th>Star</th><th>24h</th><th>6h</th><th>描述</th></tr></thead>
      <tbody>${body}</tbody>
    </table>`;
}

function renderChips() {
  $('#history-chips').innerHTML = state.historyRepos.map(name =>
    `<span class="chip">${esc(name)}<span class="x" data-repo="${esc(name)}" title="移除">✕</span></span>`).join('');
  $$('#history-chips .x').forEach(x => x.addEventListener('click', () => {
    state.historyRepos = state.historyRepos.filter(n => n !== x.dataset.repo);
    renderChips();
    drawHistory();
  }));
}

async function renderHistory(snap) {
  const tracked = state.index.tracked || [];
  $('#repo-datalist').innerHTML = tracked.map(n => `<option value="${esc(n)}">`).join('');
  if (!state.historyRepos.length) {
    const top = (snap.gainers || []).slice(0, 8).map(g => g.full_name);
    state.historyRepos = top.length ? top : Object.keys(snap.stars_sample || {}).slice(0, 8);
    renderChips();
  }
  drawHistory();
}

async function drawHistory() {
  const el = $('#history-chart');
  if (!state.historyRepos.length) {
    el.innerHTML = emptyHint('先添加要对比的仓库');
    return;
  }
  if (typeof echarts === 'undefined') {
    el.innerHTML = emptyHint('echarts.min.js 未加载（本地查看时请先把该文件放入 site/）');
    return;
  }
  const dates = state.index.dates || [];
  const snaps = [];
  for (const d of dates) snaps.push(await loadSnap(d));
  const series = state.historyRepos.map(name => ({
    name,
    type: 'line',
    smooth: true,
    showSymbol: false,
    connectNulls: true,
    data: snaps.map(s => (s.stars_sample || {})[name] ?? null),
  }));
  if (!state.chart) {
    state.chart = echarts.init(el);
    window.addEventListener('resize', () => state.chart && state.chart.resize());
  }
  state.chart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis' },
    legend: { type: 'scroll', textStyle: { color: '#8b949e' } },
    grid: { left: 60, right: 24, top: 40, bottom: 40 },
    xAxis: { type: 'category', data: dates, axisLabel: { color: '#8b949e' } },
    yAxis: { type: 'value', scale: true, axisLabel: { color: '#8b949e' }, splitLine: { lineStyle: { color: '#21262d' } } },
    series,
  }, true);
}

function renderReport(snap) {
  $('#digest-text').textContent = snap.digest || '（无摘要）';
  $('#snap-warnings').textContent = (snap.warnings || []).length ? '⚠ ' + snap.warnings.join('；') : '';
  const dates = (state.index.dates || []).slice().reverse();
  $('#report-links').innerHTML = dates.map(d =>
    `<a href="${esc(state.index.repo_url)}/blob/main/reports/${d}.md" target="_blank" rel="noopener">📄 ${d} 日报</a>`).join('')
    || '<span class="muted">暂无存档</span>';
}

/* ---------- 编排 ---------- */

async function renderCurrent() {
  const snap = await loadSnap(state.currentDate);
  $('#header-meta').textContent =
    `跟踪 ${snap.tracked.length} 个仓库 · 生成于 ${snap.generated_at}` +
    (snap.surges.length ? ` · ⚡告警 ${snap.surges.length} 条` : '');
  $('#repo-link').href = state.index.repo_url;

  renderTrending(snap);
  renderRadar(snap);
  renderGainers(snap);
  if (state.tab === 'history') await renderHistory(snap);
  if (state.tab === 'report') renderReport(snap);
}

async function init() {
  $$('.tab-btn').forEach(btn => btn.addEventListener('click', () => {
    $$('.tab-btn').forEach(b => b.classList.toggle('active', b === btn));
    state.tab = btn.dataset.tab;
    $$('.tab-panel').forEach(p => { p.hidden = p.id !== `panel-${state.tab}`; });
    renderCurrent();
  }));
  $('#since-select').addEventListener('change', e => { state.trendingSince = e.target.value; renderCurrent(); });
  $('#lang-select').addEventListener('change', e => { state.trendingLang = e.target.value; renderCurrent(); });
  $('#repo-add').addEventListener('click', () => {
    const name = $('#repo-input').value.trim();
    if (name && !state.historyRepos.includes(name)) {
      state.historyRepos.push(name);
      renderChips();
      drawHistory();
    }
    $('#repo-input').value = '';
  });

  try {
    state.index = await fetchJSON('data/index.json');
  } catch (e) {
    $('#empty').hidden = false;
    return;
  }
  if (!state.index.latest || !(state.index.dates || []).length) {
    $('#empty').hidden = false;
    return;
  }
  const sel = $('#date-select');
  sel.innerHTML = state.index.dates.slice().reverse().map(d => `<option value="${d}">${d}</option>`).join('');
  sel.value = state.index.latest;
  sel.addEventListener('change', () => { state.currentDate = sel.value; renderCurrent(); });
  state.currentDate = state.index.latest;
  await renderCurrent();
}

init();
