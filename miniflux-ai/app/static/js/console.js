const $ = id => document.getElementById(id);
const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

async function api(url, opt) {
  const r = await fetch(url, { credentials: 'same-origin', ...opt });
  if (!r.ok) throw Error(await r.text() || r.status);
  return r.json();
}

function toast(msg) {
  const t = $('toast');
  if (!t) return;
  t.textContent = msg;
  t.style.display = 'block';
  setTimeout(() => t.style.display = 'none', 3000);
}

function fmtRate(v) { return v == null ? '—' : Math.round(Number(v) * 100) + '%'; }
function fmtMs(v) { return v == null ? '—' : Math.round(Number(v)) + ' ms'; }
function fmtNum(v) { return v == null ? '—' : Number(v).toLocaleString(); }

/* =========================================================================
   Tab Navigation & Keyboard Shortcuts
   ========================================================================= */
const TAB_TITLES = {
  triage: { title: '待办与清理', desc: 'AI 自动执行微观研判与分类，你只需要一键清空废纸篓或对极少数边界文章快速定夺。' },
  rules: { title: '偏好与规则', desc: '配置关注词 (Boost) 与静音词 (Mute)。AI 评分与自主分流引擎将严格按此执行，免去微观打工。' },
  feeds: { title: '订阅源治理', desc: '各订阅源的抓取连通性、24h 延迟时序趋势、内容质量评级以及 AI 推荐权重一体化管理。' },
  explore: { title: '探索与系统', desc: '全文搜索、全网主题热点动量、高价值精选 RSS (/rss/curated)、MCP 工具桥接与系统底层监控。' }
};

function switchTab(tabId) {
  if (!TAB_TITLES[tabId]) tabId = 'triage';
  document.querySelectorAll('.tab-view').forEach(el => el.classList.remove('active'));
  document.querySelectorAll('.nav-tab').forEach(el => el.classList.remove('active'));

  const target = document.getElementById('tab-' + tabId);
  const nav = document.querySelector(`.nav-tab[data-tab="${tabId}"]`);
  if (target) target.classList.add('active');
  if (nav) nav.classList.add('active');

  const info = TAB_TITLES[tabId];
  if ($('topbarTitle')) $('topbarTitle').textContent = info.title;
  if ($('topbarDesc')) $('topbarDesc').textContent = info.desc;

  if (location.hash !== '#' + tabId) {
    history.replaceState(null, '', '#' + tabId);
  }
}

window.addEventListener('hashchange', () => {
  const hash = location.hash.replace('#', '');
  if (TAB_TITLES[hash]) switchTab(hash);
});

// Keyboard Navigation Listeners: 1-4 Switch, R Refresh, Esc Close
window.addEventListener('keydown', e => {
  const tag = document.activeElement?.tagName?.toLowerCase();
  if (['input', 'textarea'].includes(tag)) return;
  if (e.key === '1') switchTab('triage');
  else if (e.key === '2') switchTab('rules');
  else if (e.key === '3') switchTab('feeds');
  else if (e.key === '4') switchTab('explore');
  else if (e.key === 'r' || e.key === 'R') {
    e.preventDefault();
    refreshConsole();
  } else if (e.key === 'Escape') {
    if ($('rulesDialog')?.open) $('rulesDialog').close();
    if ($('ruleHitsDrawer')) $('ruleHitsDrawer').hidden = true;
    if ($('healLogsDrawer')) $('healLogsDrawer').hidden = true;
  }
});

/* =========================================================================
   Top Overview Status Bar & Metrics
   ========================================================================= */
async function loadOverview() {
  try {
    const [s, c, h, hl] = await Promise.all([
      api('/api/system-status'),
      api('/api/console/summary'),
      api('/api/scoring/feed-health'),
      api('/api/system-health')
    ]);

    // Metric Grid
    const totalScored = Number(c.articles_scored || 0);
    if ($('metricScored')) $('metricScored').textContent = fmtNum(totalScored);
    const a = c.autonomous || {};
    if ($('metricAuto')) $('metricAuto').textContent = fmtNum(Number(a.priority || 0) + Number(a.keep || 0) + Number(a.skip || 0));

    // Fast-Path Metrics (Token & Compute Savings)
    const fastCount = Number(c.fast_path_intercepted || 0);
    if ($('metricFastPath')) $('metricFastPath').textContent = fmtNum(fastCount) + ' 篇';
    if ($('effFastCount')) $('effFastCount').textContent = fmtNum(fastCount) + ' 篇';
    const llmCount = Math.max(0, totalScored - fastCount);
    if ($('effLlmCount')) $('effLlmCount').textContent = fmtNum(llmCount) + ' 篇';
    const tokensSaved = fastCount * 450;
    if ($('effTokensSaved')) $('effTokensSaved').textContent = `约 ${tokensSaved.toLocaleString()} Tokens`;
    if ($('fastPathRatioBadge')) {
      const ratio = totalScored ? Math.round(fastCount / totalScored * 100) : 0;
      $('fastPathRatioBadge').textContent = `前置节约率 ${ratio}%`;
    }

    // Status items
    const st = s.storage || {}, w = s.writes || {};
    if ($('storageState')) $('storageState').textContent = st.read_source === 'postgres' ? 'PG 主读' : 'JSONL';
    if ($('writeState')) $('writeState').textContent = w.transactional_writes ? '事务' : '—';
    if ($('outboxState')) $('outboxState').textContent = fmtNum(w.outbox_pending);
    if ($('feedState')) $('feedState').textContent = `${s.feed_health?.healthy ?? 0}/${s.feed_health?.feeds ?? 0}`;
    if ($('lastRefresh')) $('lastRefresh').textContent = '最近检查：' + new Date().toLocaleTimeString();

    // Health states
    const llm = hl.llm || {};
    if ($('llmState')) {
      $('llmState').textContent = llm.ok ? '正常' : '异常';
      $('llmState').style.color = llm.ok ? '' : '#d92d20';
    }
    const sm = hl.summary || {};
    if ($('summaryState')) $('summaryState').textContent = sm.summary_entries ? `${sm.summary_entries} 条` : '—';

    const title = $('systemStatusTitle');
    if (title) title.textContent = hl.ok ? '系统运行正常' : (llm.ok === false ? 'LLM 状态异常' : '存储异常');
    const dot = document.querySelector('.status-dot');
    if (dot) dot.style.background = hl.ok ? '#12b76a' : '#d92d20';

    return { summary: c, health: h, system: s, sysHealth: hl };
  } catch (e) {
    console.warn('loadOverview failed', e);
  }
}

/* =========================================================================
   TAB 1: 待办与清理 (Triage & Purge)
   ========================================================================= */
let _trashCandidates = [];
let _boundaryCandidates = [];
let _selectedCandidateId = null;
let _trashFilter = 'all';

async function loadTriageData() {
  try {
    const [ar, pr, sig] = await Promise.all([
      api('/api/console/archive-review'),
      api('/api/benchmark/pre-review'),
      api('/api/scoring/article-signals')
    ]);

    // Signals badge (duplicates)
    const dupCount = sig.duplicate_count || 0;
    if ($('metricDuplicates')) $('metricDuplicates').textContent = fmtNum(dupCount);

    // 1. Trash Candidates: Items flagged for archive or algorithmic archive recommendation
    const arItems = ar.items || [];
    const prArchiveItems = (pr.items || []).filter(x => x.suggestion === 'archive');
    
    const seen = new Set();
    const mergedTrash = [];
    for (const item of [...arItems, ...prArchiveItems]) {
      const eid = Number(item.entry_id);
      if (!seen.has(eid)) {
        seen.add(eid);
        mergedTrash.push(item);
      }
    }
    _trashCandidates = mergedTrash;

    const trashTotal = _trashCandidates.length;
    if ($('trashCount')) $('trashCount').textContent = trashTotal;
    if ($('archiveQueueCount')) $('archiveQueueCount').textContent = trashTotal;
    if ($('metricArchive')) $('metricArchive').textContent = fmtNum(trashTotal);

    // Update filter counts for trash chips
    const ruleCount = _trashCandidates.filter(x => (x.reasons || []).some(r => r.includes('屏蔽') || r.includes('规则')) || x.rule_muted).length;
    const dealCount = _trashCandidates.filter(x => x.content_type === 'deal' || (x.reasons || []).some(r => r.includes('deal') || r.includes('促销') || r.includes('满减'))).length;
    const lowCount = _trashCandidates.filter(x => (x.ai_score ?? x.score ?? 50) < 30).length;
    if ($('trashFilterAll')) $('trashFilterAll').textContent = trashTotal;
    if ($('trashFilterRule')) $('trashFilterRule').textContent = ruleCount;
    if ($('trashFilterDeal')) $('trashFilterDeal').textContent = dealCount;
    if ($('trashFilterLow')) $('trashFilterLow').textContent = lowCount;

    renderTrashList();

    // 2. Boundary Items: Ambiguous signals
    _boundaryCandidates = (pr.items || []).filter(x => x.suggestion === 'boundary');
    const boundaryTotal = _boundaryCandidates.length;
    if ($('metricBoundary')) $('metricBoundary').textContent = fmtNum(boundaryTotal);
    if ($('batchKeepCount')) $('batchKeepCount').textContent = boundaryTotal;
    if ($('batchDiscardCount')) $('batchDiscardCount').textContent = boundaryTotal;
    if ($('boundaryBadge')) {
      $('boundaryBadge').textContent = `${boundaryTotal} 篇需裁决`;
      $('boundaryBadge').className = boundaryTotal ? 'mode-pill warning' : 'mode-pill';
    }
    renderBoundaryList();

    // 3. Navigation badge: total pending triage action
    const navBadge = $('navTriageBadge');
    if (navBadge) {
      const actionCount = trashTotal + boundaryTotal;
      navBadge.textContent = actionCount;
      navBadge.style.display = actionCount > 0 ? 'inline-block' : 'none';
    }
  } catch (e) {
    console.warn('loadTriageData failed', e);
  }
}

function filterTrash(cat, btn) {
  _trashFilter = cat;
  document.querySelectorAll('#trashFilterChips .chip-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  renderTrashList();
}

function renderTrashList() {
  const box = $('archiveReviewList');
  if (!box) return;

  let items = _trashCandidates;
  if (_trashFilter === 'rule') {
    items = items.filter(x => (x.reasons || []).some(r => r.includes('屏蔽') || r.includes('规则')) || x.rule_muted);
  } else if (_trashFilter === 'deal') {
    items = items.filter(x => x.content_type === 'deal' || (x.reasons || []).some(r => r.includes('deal') || r.includes('促销') || r.includes('满减')));
  } else if (_trashFilter === 'low') {
    items = items.filter(x => (x.ai_score ?? x.score ?? 50) < 30);
  }

  if (!items.length) {
    box.innerHTML = `<div class="empty-console"><b>${_trashCandidates.length ? '该分类下无条目' : '🎉 废纸篓为空'}</b><span>${_trashCandidates.length ? '可切换到其他分类查看' : '当前没有待清理的垃圾或广告文章。'}</span></div>`;
    if (!_trashCandidates.length && $('archiveDetail')) {
      $('archiveDetail').innerHTML = '<div class="empty-console"><b>暂无选中文章</b><span>所有低质文章已清理完毕。</span></div>';
    }
    return;
  }

  box.innerHTML = items.map(x => `
    <article class="archive-card ${x.entry_id === _selectedCandidateId ? 'selected' : ''}" onclick="showCandidateDetail(${Number(x.entry_id)})">
      <div>
        <b>${esc(x.title || ('文章 #' + x.entry_id))}</b>
        <small>AI 评分 ${x.ai_score ?? x.score ?? '—'} · ${esc((x.reasons || [x.reason || '待清理']).slice(0, 2).join(' · '))}</small>
      </div>
      <div class="archive-actions">
        <span class="detail-hint">查看详情 →</span>
      </div>
    </article>
  `).join('');

  if (_selectedCandidateId == null && items.length) {
    showCandidateDetail(Number(items[0].entry_id));
  }
}

async function showCandidateDetail(id) {
  _selectedCandidateId = id;
  document.querySelectorAll('.archive-card').forEach(c => {
    c.classList.toggle('selected', c.getAttribute('onclick')?.includes(String(id)));
  });
  const box = $('archiveDetail');
  if (!box) return;
  box.innerHTML = '<div class="loading-row">加载详情与决策溯源…</div>';
  try {
    const d = await api('/api/benchmark/' + id + '/detail');
    const j = d.judge || {};
    const tax = d.taxonomy || j.taxonomy || {};
    const dims = [['信息', 'information'], ['证据', 'evidence'], ['深度', 'depth'], ['时效', 'timeliness'], ['原创', 'originality'], ['实用', 'practicality']];
    const negs = [['营销', 'promotional'], ['纯娱乐', 'entertainment_only'], ['低内容', 'low_content']];
    const topics = Array.isArray(tax.topics) ? tax.topics.slice(0, 6) : [];
    const kws = Array.isArray(tax.matched_keywords) ? tax.matched_keywords.slice(0, 6) : [];

    const renderInteractiveTags = (items, type) => items.map(item => `
      <span class="interactive-tag">
        ${esc(item)}
        <button type="button" title="加为屏蔽" onclick="quickAddRule('mute_kw','${esc(item)}')">🚫</button>
        <button type="button" title="加为关注" onclick="quickAddRule('boost','${esc(item)}')">⭐</button>
      </span>
    `).join('');

    const trace = d.pipeline_trace || {};
    const stageName = trace.stage === 'heuristic_fast_path' ? '⚡ 前置规则启发式快速熔断' : (trace.stage === 'cached' ? '⚡ 结构缓存命中' : '🤖 大模型深度研判');
    const ruleNotes = [];
    if (d.rule_match?.boosted) ruleNotes.push('🟢 规则加权提权 (+15分)');
    if (d.rule_match?.demoted) ruleNotes.push('🟡 轻度降权 (-15分)');
    if (d.rule_match?.muted) ruleNotes.push('🔴 命中静音规则');

    box.innerHTML = `
      <div class="archive-detail-head">
        <div>
          <div class="eyebrow">ARTICLE #${id} · 全链路溯源</div>
          <h3>${esc(d.title || '未命名文章')}</h3>
          <div class="archive-detail-links">
            ${d.url ? `<a href="${esc(d.url)}" target="_blank" rel="noopener noreferrer" class="detail-link-btn ext">🌐 打开源站原文 ↗</a>` : ''}
            <a href="${esc(d.miniflux_url || `${location.protocol}//${location.hostname}:18080/unread/entry/${id}`)}" target="_blank" rel="noopener noreferrer" class="detail-link-btn mf">📖 在 Miniflux 阅读 ↗</a>
          </div>
        </div>
        <div class="archive-detail-score"><b>${d.score ?? '—'}</b><small>/100</small></div>
      </div>
      <div class="archive-detail-meta"><span>溯源路径</span><div class="trace-box"><b>${stageName}</b> ${ruleNotes.length ? '· ' + ruleNotes.join(' · ') : ''} · 基础分: ${trace.base_score ?? d.score} ➔ 最终分: ${d.score}</div></div>
      <div class="archive-detail-meta"><span>评分维度</span><div class="judge-mini">${dims.map(([label, key]) => `<div class="judge-mini-item"><small>${label}</small><b>${j[key] ?? '—'}</b></div>`).join('')}</div></div>
      <div class="archive-detail-meta"><span>负向风险</span><div class="judge-mini">${negs.map(([label, key]) => `<div class="judge-mini-item ${(j[key] || 0) > 0 ? 'risk' : ''}"><small>${label}</small><b>${j[key] ?? '—'}</b></div>`).join('')}</div></div>
      ${topics.length ? `<div class="archive-detail-meta"><span>命中主题</span><div class="archive-tags">${renderInteractiveTags(topics, 'topic')}</div></div>` : ''}
      ${kws.length ? `<div class="archive-detail-meta"><span>命中词条</span><div class="archive-tags">${renderInteractiveTags(kws, 'kw')}</div></div>` : ''}
      ${d.reason ? `<div class="archive-detail-meta"><span>判断依据</span><p class="archive-reason">${esc(d.reason)}</p></div>` : ''}
      <div class="archive-detail-actions">
        <button type="button" class="ghost" onclick="singleCandidateAction(${id}, 'keep', this)">🟢 误判留存 (Keep)</button>
        <button type="button" class="ghost" style="color:#b42318;border-color:#fecdca" onclick="singleCandidateAction(${id}, 'archive', this)">🗑️ 立即归档 (Archive)</button>
        <button type="button" class="ghost" onclick="reEvaluateCandidate(${id}, this)">🔄 重新研判本篇</button>
      </div>
      <div class="level archive-safe-note">提示：点击词条旁的 🚫/⭐ 可快速将该词加入屏蔽/关注规则；修改后点「重新研判本篇」即刻更新。</div>
    `;
  } catch (e) {
    box.innerHTML = '<div class="empty-console">详情加载失败：' + esc(e.message) + '</div>';
  }
}

async function quickAddRule(type, val) {
  addRuleTag(type, val);
  await saveUserRules();
}

async function reEvaluateCandidate(id, btn) {
  if (btn) btn.disabled = true;
  toast('🔄 正在使用最新规则重新研判文章…');
  try {
    const res = await api('/api/benchmark/' + id + '/re-evaluate', { method: 'POST' });
    toast(`✅ ${res.message || '研判已更新'}`);
    await Promise.all([showCandidateDetail(id), loadTriageData(), loadOverview()]);
  } catch (e) {
    toast('重新研判失败: ' + e.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function singleCandidateAction(id, action, btn) {
  if (btn) btn.disabled = true;
  try {
    if (action === 'keep') {
      await api('/api/benchmark/' + id + '/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'keep', category: '人工保留' })
      });
      toast('✅ 已移出废纸篓，正常保留在阅读流');
    } else if (action === 'archive') {
      await api('/api/article-archive/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entry_ids: [id], auto_mark: true })
      });
      toast('🗑️ 已归档入库');
    }
    _selectedCandidateId = null;
    await Promise.all([loadTriageData(), loadRecentActions(), loadOverview()]);
  } catch (e) {
    toast('操作失败: ' + e.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function clearAllArchiveCandidates() {
  if (!_trashCandidates || !_trashCandidates.length) {
    toast('当前废纸篓为空，无需清空');
    return;
  }
  const count = _trashCandidates.length;
  if (!confirm(`确认一键清空全部 ${count} 篇废纸篓垃圾文章？\n\n将在 Miniflux 中执行归档。操作可逆，随时可在下方「最近实际归档」撤销还原。`)) return;

  const ids = _trashCandidates.map(x => x.entry_id).filter(Boolean);
  try {
    const d = await api('/api/article-archive/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entry_ids: ids, auto_mark: true })
    });
    toast(`🗑️ 已一键清空 ${d.executed || ids.length} 篇垃圾文章！`);
    _selectedCandidateId = null;
    await Promise.all([loadTriageData(), loadRecentActions(), loadOverview()]);
  } catch (e) {
    toast('一键清空失败: ' + e.message);
  }
}

function renderBoundaryList() {
  const box = $('boundaryList');
  if (!box) return;
  if (!_boundaryCandidates.length) {
    box.innerHTML = '<div class="empty-console"><b>✅ 无边界冲突文章</b><span>AI 对当前文章的研判高度明确，没有需人工仲裁的条目。</span></div>';
    return;
  }
  box.innerHTML = _boundaryCandidates.map(x => `
    <div class="boundary-item">
      <div class="boundary-info">
        <span class="score-badge s-uncertain">${x.ai_score ?? x.score ?? '—'}</span>
        <div class="boundary-text">
          <b>${esc(x.title || '')}</b>
          <small>${esc((x.reasons || []).slice(0, 3).join(' · ') || '信号冲突')}</small>
        </div>
      </div>
      <div class="boundary-ops">
        <button type="button" class="btn-quick-keep" onclick="quickDecideBoundary(${Number(x.entry_id)}, 'keep', this)">🟢 保留</button>
        <button type="button" class="btn-quick-discard" onclick="quickDecideBoundary(${Number(x.entry_id)}, 'archive', this)">🔴 丢弃</button>
      </div>
    </div>
  `).join('');
}

async function quickDecideBoundary(id, decision, btn) {
  if (btn) btn.disabled = true;
  try {
    if (decision === 'keep') {
      await api('/api/benchmark/' + id + '/review', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'keep', category: '边界保留' })
      });
      toast('✅ 已确认保留');
    } else {
      await api('/api/article-archive/execute', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ entry_ids: [id], auto_mark: true })
      });
      toast('🗑️ 已丢弃归档');
    }
    await Promise.all([loadTriageData(), loadRecentActions(), loadOverview()]);
  } catch (e) {
    toast('操作失败: ' + e.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function batchDecideBoundary(action, btn) {
  if (!_boundaryCandidates.length) {
    toast('当前无待裁决边界文章');
    return;
  }
  const count = _boundaryCandidates.length;
  const verb = action === 'keep' ? '保留' : '丢弃归档';
  if (!confirm(`确认一键将全部 ${count} 篇边界冲突文章【${verb}】？`)) return;

  if (btn) btn.disabled = true;
  toast(`正在批量${verb} ${count} 篇文章…`);
  try {
    for (const item of _boundaryCandidates) {
      if (action === 'keep') {
        await api('/api/benchmark/' + item.entry_id + '/review', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status: 'keep', category: '一键批量保留' })
        }).catch(() => {});
      } else {
        await api('/api/article-archive/execute', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ entry_ids: [item.entry_id], auto_mark: true })
        }).catch(() => {});
      }
    }
    toast(`✅ 已一键批量${verb} ${count} 篇边界文章`);
    await Promise.all([loadTriageData(), loadRecentActions(), loadOverview()]);
  } catch (e) {
    toast('批量裁决失败: ' + e.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

function toggleArchiveQueueDrawer() {
  const d = $('archiveQueueDrawer');
  if (!d) return;
  d.hidden = !d.hidden;
  if (!d.hidden) loadArchiveQueue();
}

async function loadArchiveQueue() {
  try {
    const d = await api('/api/article-archive/queue');
    const items = d.items || [];
    const box = $('archiveQueue');
    if (box) {
      box.innerHTML = items.length ? items.map(x => `
        <div class="action-item archive-queue-item">
          <div><b>🗄 ${esc(x.title || ('文章 #' + x.entry_id))}</b><small>AI ${x.score ?? '—'} · 待执行</small></div>
          <span class="archive-marked">待执行</span>
        </div>
      `).join('') : '<div class="action-empty">暂无单独待执行归档</div>';
    }
  } catch (e) {
    if ($('archiveQueue')) $('archiveQueue').innerHTML = '<div class="action-empty">队列暂不可用</div>';
  }
}

async function executeArchiveQueue() {
  try {
    const d = await api('/api/article-archive/queue');
    const items = d.items || [];
    if (!items.length) { toast('没有待执行归档'); return; }
    if (!confirm(`确认执行 ${items.length} 篇文章的 Miniflux 归档？执行后仍可撤销。`)) return;
    const r = await api('/api/article-archive/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ entry_ids: items.map(x => x.entry_id) })
    });
    toast(r.message || '归档完成');
    await Promise.all([loadTriageData(), loadRecentActions()]);
  } catch (e) {
    toast('归档失败: ' + e.message);
  }
}

async function loadRecentActions() {
  try {
    const d = await api('/api/article-actions/recent');
    const items = d.items || [];
    const box = $('recentActions');
    if (!box) return;
    box.innerHTML = items.length ? items.map(x => `
      <div class="action-item">
        <div>
          <b>🗄 ${esc(x.title || ('文章 #' + x.entry_id))}</b>
          <small>${esc((x.at || '').replace('T', ' ').slice(0, 16))} · 已执行归档</small>
        </div>
        <button class="undo-btn" onclick="undoArchive(${x.entry_id}, this)">↶ 撤销归档</button>
      </div>
    `).join('') : '<div class="action-empty">暂无可撤销的归档操作</div>';
  } catch (e) {
    if ($('recentActions')) $('recentActions').innerHTML = '<div class="action-empty">最近操作暂不可用</div>';
  }
}

async function undoArchive(id, btn) {
  if (!confirm('确定撤销这次归档？文章会恢复到之前的阅读状态。')) return;
  if (btn) btn.disabled = true;
  try {
    const d = await api('/api/article-advice/' + id + '/rollback', { method: 'POST' });
    toast(d.message || '已撤销归档');
    await Promise.all([loadTriageData(), loadRecentActions(), loadOverview()]);
  } catch (e) {
    if (btn) btn.disabled = false;
    toast('撤销失败: ' + e.message);
  }
}

async function batchRollbackAll(btn) {
  if (!confirm('确定撤回最近所有已归档的文章？它们将恢复为未读状态。')) return;
  if (btn) btn.disabled = true;
  toast('正在批量撤销归档…');
  try {
    const res = await api('/api/article-actions/rollback-all', { method: 'POST' });
    toast(res.message || '已撤销');
    await Promise.all([loadTriageData(), loadRecentActions(), loadOverview()]);
  } catch (e) {
    toast('批量撤销失败: ' + e.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

/* =========================================================================
   TAB 2: 偏好与规则 (Rules & Preferences)
   ========================================================================= */
let _userRules = {
  boost_topics: [],
  boost_keywords: [],
  mute_topics: [],
  mute_keywords: [],
  demote_keywords: [],
  mute_content_types: ['deal'],
  auto_star: true,
  auto_silence: true,
};

async function loadUserRules() {
  try {
    const d = await api('/api/preferences/rules');
    if (d) {
      _userRules = d.rules || d;
      renderUserRules();
      loadRuleSuggestions();
    }
  } catch (e) {
    console.warn('loadUserRules failed', e);
  }
}

function renderUserRules() {
  const r = _userRules || {};
  const hits = r.hit_counts || {};
  const boostKwHits = hits.boost_keywords || {};
  const boostTopHits = hits.boost_topics || {};
  const muteKwHits = hits.mute_keywords || {};
  const muteTopHits = hits.mute_topics || {};
  const demoteKwHits = hits.demote_keywords || {};

  const renderTags = (arr, type, hitMap) => (arr || []).map(t => {
    const cnt = hitMap ? (hitMap[t] ?? 0) : 0;
    const isZero = cnt === 0;
    return `
      <span class="rule-tag rule-tag-${type} ${isZero ? 'tag-zero' : ''}" onclick="showRuleHits('${type}','${esc(t)}')">
        ${esc(t)} <small class="tag-count">${cnt}</small>
        <a href="javascript:void(0)" onclick="event.stopPropagation();removeRuleTag('${type}','${esc(t)}')">×</a>
      </span>
    `;
  }).join('');

  const bEl = $('boostTags');
  if (bEl) {
    const boostTerms = [...(r.boost_topics || []), ...(r.boost_keywords || [])];
    bEl.innerHTML = renderTags(boostTerms, 'boost', {...boostTopHits, ...boostKwHits}) || '<span class="empty-tag">暂无关注标签</span>';
  }

  const mKwEl = $('muteKwTags');
  if (mKwEl) mKwEl.innerHTML = renderTags(r.mute_keywords || [], 'mute_kw', muteKwHits) || '<span class="empty-tag">暂无屏蔽词</span>';

  const mTopEl = $('muteTopicTags');
  if (mTopEl) mTopEl.innerHTML = renderTags(r.mute_topics || [], 'mute_topic', muteTopHits) || '<span class="empty-tag">暂无屏蔽主题</span>';

  const dKwEl = $('demoteKwTags');
  if (dKwEl) dKwEl.innerHTML = renderTags(r.demote_keywords || [], 'demote_kw', demoteKwHits) || '<span class="empty-tag">暂无降权词</span>';

  const dealSw = $('muteDealSwitch');
  if (dealSw) dealSw.checked = (r.mute_content_types || []).includes('deal');

  const entSw = $('muteEntertainmentSwitch');
  if (entSw) entSw.checked = (r.mute_content_types || []).includes('entertainment');

  const starSw = $('autoStarSwitch');
  if (starSw) starSw.checked = r.auto_star !== false;

  const silSw = $('autoSilenceSwitch');
  if (silSw) silSw.checked = r.auto_silence !== false;
}

function filterCardTags(input, containerId) {
  const q = (input.value || '').trim().toLowerCase();
  const container = $(containerId);
  if (!container) return;
  container.querySelectorAll('.rule-tag').forEach(tag => {
    const text = tag.textContent.toLowerCase();
    tag.style.display = (!q || text.includes(q)) ? 'inline-flex' : 'none';
  });
}

async function loadRuleSuggestions() {
  try {
    const d = await api('/api/preferences/rules/suggestions');
    const mutes = d.suggested_mutes || [];
    const boosts = d.suggested_boosts || [];

    const mBox = $('muteSuggestions');
    if (mBox) {
      if (mutes.length) {
        mBox.innerHTML = `
          <div class="suggestion-title"><small>💡 AI 建议屏蔽 (高频垃圾词):</small></div>
          <div class="suggestion-chips">
            ${mutes.map(s => `<button type="button" class="suggestion-chip mute-chip" onclick="adoptSuggestion('mute_kw', '${esc(s.keyword)}')">+ ${esc(s.keyword)} (${s.count})</button>`).join('')}
          </div>
        `;
        mBox.hidden = false;
      } else {
        mBox.hidden = true;
      }
    }

    const bBox = $('boostSuggestions');
    if (bBox) {
      if (boosts.length) {
        bBox.innerHTML = `
          <div class="suggestion-title"><small>💡 AI 建议关注 (高分升温主题):</small></div>
          <div class="suggestion-chips">
            ${boosts.map(s => `<button type="button" class="suggestion-chip boost-chip" onclick="adoptSuggestion('boost', '${esc(s.keyword)}')">+ ${esc(s.keyword)} (${s.count})</button>`).join('')}
          </div>
        `;
        bBox.hidden = false;
      } else {
        bBox.hidden = true;
      }
    }
  } catch (e) {
    console.warn('loadRuleSuggestions failed', e);
  }
}

function adoptSuggestion(type, val) {
  addRuleTag(type, val);
  const boxId = type === 'boost' ? 'boostSimBox' : type === 'mute_kw' ? 'muteSimBox' : 'demoteSimBox';
  if ($(boxId)) $(boxId).hidden = true;
}

let _simTimer = null;
function simulateInput(type, val) {
  clearTimeout(_simTimer);
  val = (val || '').trim();
  const boxId = type === 'boost' ? 'boostSimBox' : type === 'mute_kw' ? 'muteSimBox' : 'demoteSimBox';
  const box = $(boxId);
  if (!box) return;
  if (!val) {
    box.hidden = true;
    box.innerHTML = '';
    return;
  }
  _simTimer = setTimeout(async () => {
    try {
      const res = await api('/api/preferences/rules/simulate', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({keyword: val, type: type})
      });
      box.hidden = false;
      let warnHtml = '';
      if (res.warning) {
        warnHtml = `<div class="sim-warn">${esc(res.warning)}</div>`;
      }
      box.innerHTML = `
        <div class="sim-content">
          <div class="sim-stats">
            <span>实时测算：历史匹配 <b>${res.total_hits}</b> 篇</span>
            ${res.high_score_count ? `<span class="sim-high">高分 ${res.high_score_count} 篇</span>` : ''}
            ${res.low_score_count ? `<span class="sim-low">低质 ${res.low_score_count} 篇</span>` : ''}
          </div>
          ${warnHtml}
          ${res.sample_titles && res.sample_titles.length ? `<div class="sim-samples">示例: ${res.sample_titles.slice(0, 2).map(t => esc(t)).join('； ')}</div>` : ''}
        </div>
      `;
    } catch (e) {
      box.hidden = true;
    }
  }, 280);
}

async function showRuleHits(type, keyword) {
  const drawer = $('ruleHitsDrawer');
  if (!drawer) return;
  drawer.hidden = false;
  drawer.innerHTML = `<div class="rule-hits-head"><b>🔍 规则命中反查: "${esc(keyword)}"</b><button class="ghost" onclick="$('ruleHitsDrawer').hidden=true">关闭 ✕</button></div><div class="loading-row">检索中…</div>`;
  drawer.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  try {
    const res = await api(`/api/preferences/rules/preview-hits?type=${encodeURIComponent(type)}&keyword=${encodeURIComponent(keyword)}`);
    const items = res.items || [];
    drawer.innerHTML = `
      <div class="rule-hits-head">
        <b>🔍 规则命中反查: "${esc(keyword)}" (历史匹配 ${items.length} 篇)</b>
        <button class="ghost" onclick="$('ruleHitsDrawer').hidden=true">关闭 ✕</button>
      </div>
      <div class="rule-hits-list">
        ${items.length ? items.map(x => `
          <div class="rule-hit-row">
            <span class="score-badge s-${(x.score||0)>=70?'high':(x.score||0)<30?'archive':'uncertain'}">${x.score ?? '—'}</span>
            <div class="rule-hit-info">
              <b>${esc(x.title || '')}</b>
              <small>Feed #${x.feed_id || '—'} · ${esc((x.published_at || '').replace('T', ' ').slice(0, 16))}</small>
            </div>
          </div>
        `).join('') : '<div class="empty-console">无匹配历史文章</div>'}
      </div>
    `;
  } catch (e) {
    drawer.innerHTML = `<div class="empty-console">加载失败: ${esc(e.message)}</div>`;
  }
}

// Rules Export & Import Modal Logic
let _dialogMode = 'export';
function openRulesExportModal() {
  _dialogMode = 'export';
  $('dialogTitle').textContent = '📤 导出规则备份 (JSON)';
  $('dialogDesc').textContent = '你可以复制以下 JSON 代码备份保存，或在其他部署中导入：';
  $('rulesJsonArea').value = JSON.stringify(_userRules, null, 2);
  $('rulesJsonArea').readOnly = true;
  $('dialogSubmitBtn').textContent = '📋 复制到剪贴板';
  $('rulesDialog').showModal();
}

function openRulesImportModal() {
  _dialogMode = 'import';
  $('dialogTitle').textContent = '📥 导入规则配置 (JSON)';
  $('dialogDesc').textContent = '请将导出的规则 JSON 粘贴在下方，导入将覆盖生效当前规则：';
  $('rulesJsonArea').value = '';
  $('rulesJsonArea').readOnly = false;
  $('dialogSubmitBtn').textContent = '📥 确认导入覆盖';
  $('rulesDialog').showModal();
}

async function submitDialogAction() {
  if (_dialogMode === 'export') {
    navigator.clipboard.writeText($('rulesJsonArea').value).then(() => {
      toast('📋 已复制规则 JSON 到剪贴板！');
      $('rulesDialog').close();
    });
  } else {
    try {
      const parsed = JSON.parse($('rulesJsonArea').value);
      if (!parsed || typeof parsed !== 'object') throw Error('JSON 格式不正确');
      _userRules = parsed;
      toast('正在保存导入的规则…');
      await saveUserRules();
      $('rulesDialog').close();
    } catch (e) {
      toast('导入失败: ' + e.message);
    }
  }
}

async function pruneZeroHitRules(btn) {
  if (!_userRules || !_userRules.hit_counts) {
    toast('暂无命中统计数据');
    return;
  }
  const hits = _userRules.hit_counts || {};
  const muteKwHits = hits.mute_keywords || {};
  const boostKwHits = hits.boost_keywords || {};
  const demoteKwHits = hits.demote_keywords || {};

  const zeroMutes = (_userRules.mute_keywords || []).filter(k => (muteKwHits[k] ?? 0) === 0);
  const zeroBoosts = (_userRules.boost_keywords || []).filter(k => (boostKwHits[k] ?? 0) === 0);
  const zeroDemotes = (_userRules.demote_keywords || []).filter(k => (demoteKwHits[k] ?? 0) === 0);

  const totalZero = zeroMutes.length + zeroBoosts.length + zeroDemotes.length;
  if (totalZero === 0) {
    toast('🎉 所有规则标签均有实际命中，规则库非常精炼！');
    return;
  }
  if (!confirm(`检测到 ${totalZero} 个从未命中过的冷门规则词（屏蔽 ${zeroMutes.length} 个，关注 ${zeroBoosts.length} 个，降权 ${zeroDemotes.length} 个）。\n\n确认一键清理这些 0 命中标签以瘦身规则库？`)) return;

  _userRules.mute_keywords = (_userRules.mute_keywords || []).filter(k => (muteKwHits[k] ?? 0) > 0);
  _userRules.boost_keywords = (_userRules.boost_keywords || []).filter(k => (boostKwHits[k] ?? 0) > 0);
  _userRules.demote_keywords = (_userRules.demote_keywords || []).filter(k => (demoteKwHits[k] ?? 0) > 0);

  toast(`已清理 ${totalZero} 个冷门规则词，正在保存…`);
  await saveUserRules(btn);
}

function toggleAutoAction(key, checked) {
  if (!_userRules) return;
  if (key === 'auto_star') {
    _userRules.auto_star = checked;
    toast(`已${checked ? '开启' : '关闭'} 高分好文自动加星 (点击"保存规则"生效)`);
  } else if (key === 'auto_silence') {
    _userRules.auto_silence = checked;
    toast(`已${checked ? '开启' : '关闭'} 垃圾广告自动标已读 (点击"保存规则"生效)`);
  }
}

function addRuleTag(type, val) {
  val = (val || '').trim();
  if (!val) return;
  if (!_userRules) _userRules = { boost_topics: [], boost_keywords: [], mute_topics: [], mute_keywords: [], demote_keywords: [], mute_content_types: ['deal'] };

  if (type === 'boost') {
    if (!_userRules.boost_keywords.includes(val)) _userRules.boost_keywords.push(val);
  } else if (type === 'mute_kw') {
    if (!_userRules.mute_keywords.includes(val)) _userRules.mute_keywords.push(val);
  } else if (type === 'mute_topic') {
    if (!_userRules.mute_topics.includes(val)) _userRules.mute_topics.push(val);
  } else if (type === 'demote_kw') {
    if (!_userRules.demote_keywords) _userRules.demote_keywords = [];
    if (!_userRules.demote_keywords.includes(val)) _userRules.demote_keywords.push(val);
  }
  renderUserRules();
  toast(`已添加：${val} (点击"保存规则"生效)`);
}

function removeRuleTag(type, val) {
  if (!_userRules) return;
  if (type === 'boost') {
    _userRules.boost_topics = (_userRules.boost_topics || []).filter(x => x !== val);
    _userRules.boost_keywords = (_userRules.boost_keywords || []).filter(x => x !== val);
  } else if (type === 'mute_kw') {
    _userRules.mute_keywords = (_userRules.mute_keywords || []).filter(x => x !== val);
  } else if (type === 'mute_topic') {
    _userRules.mute_topics = (_userRules.mute_topics || []).filter(x => x !== val);
  } else if (type === 'demote_kw') {
    _userRules.demote_keywords = (_userRules.demote_keywords || []).filter(x => x !== val);
  }
  renderUserRules();
  toast(`已移除：${val} (点击"保存规则"生效)`);
}

function toggleMuteType(ctype, checked) {
  if (!_userRules) return;
  if (!_userRules.mute_content_types) _userRules.mute_content_types = [];
  if (checked) {
    if (!_userRules.mute_content_types.includes(ctype)) _userRules.mute_content_types.push(ctype);
  } else {
    _userRules.mute_content_types = _userRules.mute_content_types.filter(x => x !== ctype);
  }
  toast(`已切换 ${ctype} 屏蔽状态 (点击"保存规则"生效)`);
}

async function saveUserRules(btn) {
  if (btn) btn.disabled = true;
  try {
    await api('/api/preferences/rules', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rules: _userRules })
    });
    toast('✅ 偏好与过滤规则已保存！AI 将按新规则自动分流');
    await Promise.all([loadTriageData(), loadAutonomous(), loadUserRules()]);
  } catch (e) {
    toast('保存规则失败: ' + e.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function loadAutonomous() {
  try {
    const d = await api('/api/scoring/autonomous');
    const c = d.counts || {};
    const total = Number(c.priority || 0) + Number(c.keep || 0) + Number(c.skip || 0) + Number(c.review || 0);
    const auto = Number(c.priority || 0) + Number(c.keep || 0) + Number(c.skip || 0);
    const b = $('autonomousBadge'), s = $('autonomousSummary');
    if (b) {
      b.textContent = `AI 自动分流 ${auto}/${total} 篇 (${total ? Math.round(auto / total * 100) : 0}%)`;
      b.className = 'mode-pill';
    }
    if (s) {
      s.innerHTML = `
        <div class="autonomous-grid">
          <div><small>优先阅读</small><b>${fmtNum(c.priority || 0)}</b></div>
          <div><small>正常保留</small><b>${fmtNum(c.keep || 0)}</b></div>
          <div><small>建议跳过</small><b>${fmtNum(c.skip || 0)}</b></div>
          <div><small>边界复核</small><b>${fmtNum(c.review || 0)}</b></div>
        </div>
        <div class="level">AI 自主分流率达 ${total ? Math.round(auto / total * 100) : 0}%。命中静音词直接沉底，无需人工逐篇翻查。</div>
      `;
    }
    const r = $('autonomousReasons');
    if (r) {
      const items = (d.items || []).filter(x => x.decision !== 'review').slice(0, 8);
      r.innerHTML = items.length ? `
        <div class="decision-title"><small>最近自主研判示例</small></div>
        ${items.map(x => `
          <div class="decision-row">
            <span class="decision-tag d-${esc(x.decision)}">${esc(x.label || x.decision)}</span>
            <span class="decision-text">${esc(x.title || '')}</span>
            <span class="decision-meta">${esc((x.reasons || []).slice(0, 2).join(' · '))}</span>
          </div>
        `).join('')}
      ` : '<div class="empty-console">暂无记录</div>';
    }
  } catch (e) {
    if ($('autonomousSummary')) $('autonomousSummary').textContent = '自主分流态势暂不可用';
  }
}

/* =========================================================================
   TAB 3: 订阅源综合治理 (Feed Governance - 三合一)
   ========================================================================= */
let _allFeeds = [];
let _feedStatusFilter = 'all';
let _feedKeyword = '';

async function loadFeedsGovernance() {
  try {
    const d = await api('/api/feed-policy');
    _allFeeds = d.items || [];
    renderFeedsList();
  } catch (e) {
    if ($('unifiedFeedList')) $('unifiedFeedList').innerHTML = '<div class="empty-console">订阅源数据暂不可用</div>';
  }
}

function filterFeedsStatus(status, btn) {
  _feedStatusFilter = status;
  document.querySelectorAll('#feedStatusChips .chip-btn').forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  renderFeedsList();
}

function filterFeedsList() {
  _feedKeyword = ($('feedSearchInput')?.value || '').trim().toLowerCase();
  renderFeedsList();
}

function renderFeedsList() {
  const b = $('feedPolicyBadge'), l = $('unifiedFeedList');
  if (!l) return;

  const total = _allFeeds.length;
  const warns = _allFeeds.filter(x => x.quality_action === 'deprioritize' || x.health_action === 'investigate').length;
  const disabled = _allFeeds.filter(x => x.disabled).length;
  const healthy = _allFeeds.filter(x => !x.disabled && x.quality_action !== 'deprioritize' && x.health_action !== 'investigate').length;

  if ($('feedCountAll')) $('feedCountAll').textContent = total;
  if ($('feedCountWarn')) $('feedCountWarn').textContent = warns;
  if ($('feedCountHealthy')) $('feedCountHealthy').textContent = healthy;
  if ($('feedCountDisabled')) $('feedCountDisabled').textContent = disabled;

  if (b) {
    b.textContent = `${total} 个订阅源${warns ? ` · ${warns} 个需关注` : ' · 运行健康'}`;
    b.className = warns ? 'mode-pill warning' : 'mode-pill';
  }

  let items = _allFeeds;
  if (_feedStatusFilter === 'warn') {
    items = items.filter(x => x.quality_action === 'deprioritize' || x.health_action === 'investigate');
  } else if (_feedStatusFilter === 'healthy') {
    items = items.filter(x => !x.disabled && x.quality_action !== 'deprioritize' && x.health_action !== 'investigate');
  } else if (_feedStatusFilter === 'disabled') {
    items = items.filter(x => x.disabled);
  }

  if (_feedKeyword) {
    items = items.filter(x => (x.title || '').toLowerCase().includes(_feedKeyword) || (x.feed_url || '').toLowerCase().includes(_feedKeyword));
  }

  const actionNames = { maintain: '正常维持', observe: '继续观察', deprioritize: '建议降权' };
  const actionClass = { maintain: 'ok', observe: 'warn', deprioritize: 'bad' };

  l.innerHTML = items.map(x => {
    const weight = x.weight ?? 100;
    const series = x.series || [];
    const maxLat = Math.max(1, ...series.map(s => s.average_latency_ms || 0));
    const sparklines = series.slice(-12).map(s => {
      const rate = s.success_rate == null ? 0 : s.success_rate;
      const pct = Math.round(rate * 100);
      const lat = s.average_latency_ms || 0;
      const h = Math.max(2, Math.round(lat / maxLat * 20));
      const cls = rate >= 0.9 ? 'tr-ok' : rate >= 0.5 ? 'tr-warn' : 'tr-bad';
      return `<div class="trend-cell ${cls}" title="${esc(s.bucket)} 成功率${pct}% 延迟${Math.round(lat)}ms"><div class="trend-bar" style="height:${h}px"></div><small>${pct}%</small></div>`;
    }).join('');

    return `
      <article class="feed-governance-card ${actionClass[x.quality_action] || 'ok'}">
        <div class="fg-header">
          <div>
            <b>Feed #${esc(x.feed_id)} ${esc(x.title || '')}</b>
            <div class="fg-urls">
              ${x.feed_url ? `<a href="${esc(x.feed_url)}" target="_blank" class="text-link">源: ${esc(x.feed_url.replace(/^https?:\/\//, '').slice(0, 45))}</a>` : ''}
              ${x.next_check_at ? `<span>下次抓取: ${esc((x.next_check_at || '').replace('T', ' ').slice(0, 16))}</span>` : ''}
              ${x.disabled ? `<span style="color:#d92d20;font-weight:700">已停用</span>` : ''}
              ${x.parsing_error ? `<span style="color:#d92d20">⚠ 解析错误</span>` : ''}
            </div>
          </div>
          <div class="fg-badge-wrap">
            <span class="mode-pill ${x.quality_action === 'deprioritize' ? 'warning' : ''}">${esc(actionNames[x.quality_action] || x.quality_action)}</span>
            <strong class="fp-weight">推荐权重 ${weight}</strong>
          </div>
        </div>

        <div class="fg-metrics-grid">
          <div><small>平均质量</small><b>${x.average_score ?? '—'}</b></div>
          <div><small>低质率</small><b>${Math.round(Number(x.low_rate || 0) * 100)}%</b></div>
          <div><small>营销率</small><b>${Math.round(Number(x.high_rate || 0) * 100)}%</b></div>
          <div><small>抓取成功率</small><b>${fmtRate(x.success_rate)}</b></div>
          <div><small>平均延迟</small><b>${fmtMs(x.average_latency_ms)}</b></div>
          <div><small>P95 延迟</small><b>${fmtMs(x.p95_latency_ms)}</b></div>
        </div>

        ${sparklines ? `<div class="fg-sparkline-wrap"><small>24h 抓取时序 (成功率/延迟)：</small><div class="trend-cells">${sparklines}</div></div>` : ''}

        <div class="fg-footer">
          <div class="fg-reasons">${(x.quality_reasons || []).map(r => `<span>${esc(r)}</span>`).join('')}</div>
          <div class="fp-controls">
            <div class="fp-slider">
              <input type="range" min="0" max="100" step="5" value="${weight}" data-feed="${esc(x.feed_id)}" data-action="fp-weight" oninput="this.nextElementSibling.textContent=this.value" aria-label="Feed ${esc(x.feed_id)} 权重">
              <output>${weight}</output>
            </div>
            <button type="button" class="ghost" onclick="setFeedWeight('${esc(x.feed_id)}', this)">应用权重</button>
            ${(x.previous_weight != null && x.weight !== 100) ? `<button type="button" class="ghost" onclick="rollbackFeedWeight('${esc(x.feed_id)}', this)">↶ 回滚</button>` : ''}
          </div>
        </div>
      </article>
    `;
  }).join('') || '<div class="empty-console">没有匹配的订阅源</div>';
}

async function triggerHealNow(btn) {
  if (btn) btn.disabled = true;
  toast('🩺 正在对所有订阅源执行网络体检与阶梯自愈…');
  try {
    const res = await api('/api/feed-health/heal-now', { method: 'POST' });
    const healed = res.healed_feeds || 0;
    const checked = res.checked_feeds || 0;
    if (healed > 0) {
      toast(`🩺 体检完成：${checked} 个源中已自动修复 ${healed} 个异常源！`);
    } else {
      toast(`🩺 体检完成：${checked} 个订阅源均处于正常可用状态。`);
    }
    await loadFeedsGovernance();
    toggleHealLogsDrawer(true);
  } catch (e) {
    toast('自愈执行失败: ' + e.message);
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function toggleHealLogsDrawer(forceOpen = false) {
  const drawer = $('healLogsDrawer');
  if (!drawer) return;
  if (forceOpen) drawer.hidden = false;
  else drawer.hidden = !drawer.hidden;

  if (!drawer.hidden) {
    drawer.innerHTML = '<div class="loading-row">加载自愈巡检日志…</div>';
    try {
      const res = await api('/api/feed-health/heal-logs');
      const logs = res.logs || [];
      drawer.innerHTML = `
        <div class="rule-hits-head">
          <b>🩺 订阅源自动巡检与自愈流水 (最近 ${logs.length} 条记录)</b>
          <button class="ghost" onclick="$('healLogsDrawer').hidden=true">关闭 ✕</button>
        </div>
        <div class="rule-hits-list">
          ${logs.length ? logs.map(l => `
            <div class="rule-hit-row">
              <span class="score-badge s-${l.success ? 'high' : 'archive'}">${l.success ? '成功' : '失败'}</span>
              <div class="rule-hit-info">
                <b>Feed #${l.feed_id} · ${esc(l.details)}</b>
                <small>${esc((l.healed_at || '').replace('T', ' ').slice(0, 16))} · 操作: ${esc(l.action)}</small>
              </div>
            </div>
          `).join('') : '<div class="empty-console">暂无自愈操作记录（所有源运行正常）</div>'}
        </div>
      `;
    } catch (e) {
      drawer.innerHTML = `<div class="empty-console">加载日志失败: ${esc(e.message)}</div>`;
    }
  }
}

async function setFeedWeight(fid, btn) {
  const row = btn.closest('.feed-governance-card') || btn.closest('.feed-policy-card');
  const slider = row.querySelector('[data-action="fp-weight"]');
  const weight = Number(slider.value);
  if (!confirm(`确认将 Feed #${fid} 的 AI 推荐权重调整为 ${weight}？仅影响 AI Worker 本地精选推荐，不修改 Miniflux。`)) return;
  btn.disabled = true;
  try {
    const d = await api('/api/feed-policy/' + fid + '/weight', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ weight })
    });
    toast(d.message || '权重已更新');
    await loadFeedsGovernance();
  } catch (e) {
    btn.disabled = false;
    toast('更新失败: ' + e.message);
  }
}

async function rollbackFeedWeight(fid, btn) {
  if (!confirm(`确认回滚 Feed #${fid} 的推荐权重？`)) return;
  btn.disabled = true;
  try {
    const d = await api('/api/feed-policy/' + fid + '/rollback', { method: 'POST' });
    toast(d.message || '已回滚');
    await loadFeedsGovernance();
  } catch (e) {
    btn.disabled = false;
    toast('回滚失败: ' + e.message);
  }
}

/* =========================================================================
   TAB 4: 探索与系统 (Explore & System)
   ========================================================================= */
async function doSearch() {
  const q = ($('searchInput').value || '').trim();
  const box = $('searchResults');
  if (!q) {
    box.innerHTML = '<div class="empty-console"><b>输入关键词开始搜索</b><span>支持标题与正文混合检索</span></div>';
    return;
  }
  box.innerHTML = '<div class="loading-row">检索中…</div>';
  try {
    const d = await api('/api/search?q=' + encodeURIComponent(q) + '&limit=30');
    const hits = d.items || [];
    box.innerHTML = hits.length ? `
      <div class="decision-title"><small>找到 ${hits.length} 条结果（"${esc(d.query)}"）</small></div>
      ${hits.map(x => {
        const s = x.ai_score;
        const badge = s == null ? '—' : s >= 80 ? 'high' : s >= 60 ? 'keep' : s < 20 ? 'archive' : 'uncertain';
        return `
          <div class="search-row">
            <span class="score-badge s-${badge}">${s ?? '—'}</span>
            <div class="search-main">
              <b>${esc(x.title || '')}</b>
              <small>${esc(x.source === 'local' ? 'AI 评分库' : 'Miniflux 全文')} · ${esc((x.published_at || x.ai_scored_at || '').replace('T', ' ').slice(0, 16))}${x.ai_reason ? ' · ' + esc(x.ai_reason) : ''}</small>
            </div>
            ${x.url ? `<a class="text-link" href="${esc(x.url)}" target="_blank">阅读 ›</a>` : ''}
          </div>
        `;
      }).join('')}
    ` : '<div class="empty-console"><b>没有找到匹配文章</b><span>换个词试试</span></div>';
  } catch (e) {
    box.innerHTML = '<div class="empty-console">搜索失败: ' + esc(e.message) + '</div>';
  }
}

async function loadTrends() {
  try {
    const d = await api('/api/scoring/trends');
    const b = $('trendsBadge'), c = $('trendsContent');
    if (!b || !c) return;
    b.textContent = `${d.scored_total} 篇文章分析`;
    const topics = d.topic_trends || [], kws = d.top_keywords || [], cts = d.content_types || [];
    const rising = topics.filter(x => x.trending).length;
    const typeNames = { news: '新闻', analysis: '深度', tutorial: '教程', review: '评测', opinion: '观点', announcement: '公告', deal: '促销', entertainment: '娱乐', other: '其他' };

    c.innerHTML = `
      <div class="trends-grid">
        <div class="trends-card trend-wide">
          <div class="trends-head"><b>主题趋势</b><small>近 7 天 vs 全量动量 · ${rising} 个上升热点</small></div>
          <div class="trend-tags">${topics.length ? topics.slice(0, 14).map(t => `<span class="trend-tag ${t.trending ? 'trend-up' : ''}" title="全部 ${t.count} 篇 · 近7天 ${t.recent7} 篇">${esc(t.topic)} <em>${t.count}</em>${t.trending ? ' ↑' : ''}</span>`).join('') : '<span class="level">暂无主题</span>'}</div>
        </div>
        <div class="trends-card">
          <div class="trends-head"><b>热门关键词 TOP 15</b><small>词频统计</small></div>
          <div class="trend-tags">${kws.length ? kws.slice(0, 15).map(k => `<span class="trend-tag">${esc(k.keyword)} <em>${k.count}</em></span>`).join('') : '<span class="level">暂无</span>'}</div>
        </div>
        <div class="trends-card">
          <div class="trends-head"><b>内容类型分布</b><small>AI 分类占比</small></div>
          <div class="ctype-list">${cts.length ? cts.map(x => {
            const pct = Math.round(x.count / d.scored_total * 100);
            return `<div class="ctype-row"><span class="ctype-name">${typeNames[x.type] || esc(x.type)}</span><div class="ctype-bar"><div class="ctype-fill" style="width:${pct}%"></div></div><b>${x.count} (${pct}%)</b></div>`;
          }).join('') : '<span class="level">暂无数据</span>'}</div>
        </div>
      </div>
    `;
  } catch (e) {
    if ($('trendsContent')) $('trendsContent').innerHTML = '<div class="empty-console">趋势暂不可用</div>';
  }
}

function copyCuratedUrl(btn) {
  const url = `${location.origin}/rss/curated?min_score=70`;
  navigator.clipboard.writeText(url).then(() => {
    toast('📋 已复制精选 RSS 订阅链接！可粘贴至任何阅读器');
  }).catch(() => {
    toast('复制失败，请手动选择复制');
  });
}

async function loadMcp() {
  try {
    const m = await api('/api/mcp/manifest');
    const c = $('mcpContent');
    if (!c) return;
    const tools = m.tools || [];
    c.innerHTML = `
      <div class="mcp-grid">${tools.map(t => `
        <div class="mcp-tool">
          <div class="mcp-tool-head"><b>${esc(t.name)}</b><span class="mcp-method">${esc(t.method)}</span></div>
          <p>${esc(t.description)}</p>
          <code>${esc(t.path)}</code>
        </div>
      `).join('')}</div>
    `;
  } catch (e) {
    if ($('mcpContent')) $('mcpContent').innerHTML = '<div class="empty-console">MCP 工具暂不可用</div>';
  }
}

function toggleAuditDetails(btn) {
  const p = $('auditDetails');
  if (!p) return;
  p.hidden = !p.hidden;
  if (btn) btn.textContent = p.hidden ? '展开审计细节' : '收起审计细节';
}

async function loadAudit() {
  try {
    const [s, c, hl] = await Promise.all([
      api('/api/storage-consistency'),
      api('/api/system-status'),
      api('/api/system-health')
    ]);
    if ($('auditConsistency')) $('auditConsistency').textContent = s.ok ? '正常' : '异常';
    if ($('auditFeed')) $('auditFeed').textContent = `${c.feed_health?.healthy ?? 0}/${c.feed_health?.feeds ?? 0} 正常`;
    const bk = hl.backup || {};
    const bkEl = $('auditBackup');
    if (bkEl) {
      if (bk.available && bk.last_backup) {
        const ts = bk.last_backup.replace(/^(\d{4})(\d{2})(\d{2})T(\d{2})(\d{2})/, '$1-$2-$3 $4:$5');
        bkEl.textContent = ts + ' UTC';
      } else {
        bkEl.textContent = '每日';
      }
    }
    if ($('auditImages')) $('auditImages').textContent = '当前+回滚';
    if ($('auditDetails')) $('auditDetails').textContent = JSON.stringify({ storage: s, system: c, backup: bk }, null, 2);
  } catch (e) {
    if ($('auditDetails')) $('auditDetails').textContent = '审计数据暂不可用';
  }
}

/* =========================================================================
   Global Refresh Dispatcher
   ========================================================================= */
async function refreshConsole() {
  const btn = $('refreshBtn');
  if (btn) btn.classList.add('spinning');
  try {
    await loadOverview();
    await Promise.all([
      loadTriageData(),
      loadUserRules(),
      loadAutonomous(),
      loadFeedsGovernance(),
      loadTrends(),
      loadMcp(),
      loadAudit()
    ]);
    toast('控制台已刷新');
  } catch (e) {
    toast('部分数据刷新失败');
  } finally {
    if (btn) setTimeout(() => btn.classList.remove('spinning'), 500);
  }
}

// Initial Boot
if ($('curatedUrlText')) $('curatedUrlText').textContent = `${location.origin}/rss/curated?min_score=70`;
const initialHash = location.hash.replace('#', '');
if (TAB_TITLES[initialHash]) {
  switchTab(initialHash);
} else {
  switchTab('triage');
}

refreshConsole();
setInterval(refreshConsole, 60000);
