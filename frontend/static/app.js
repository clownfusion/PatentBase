/* ===== PatentBase App JS ===== */
"use strict";

// ─── State ────────────────────────────────────────────────────────────────
const state = {
  patents: [],
  selectedId: null,
  pollingTimer: null,
  progressTimer: null,
  analysisStartTime: null,
  pollingPatentId: null,   // どの特許をポーリング中か（タブ切り替え後の再開判定）
  selectMode: false,
  selectedIds: new Set(),
  viewMode: "analysis",
  sidebarAutoCollapsed: false,
};

// タブごとのスクロール位置を保持（特許切り替え時にリセット）
const sourceScroll = { claims: 0, desc: 0 };

// ─── API helpers ──────────────────────────────────────────────────────────
async function api(method, path, body) {
  const opts = { method, headers: {} };
  if (body instanceof FormData) {
    opts.body = body;
  } else if (body) {
    opts.headers["Content-Type"] = "application/json";
    opts.body = JSON.stringify(body);
  }
  const res = await fetch(path, opts);
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

// ─── Toast notifications ──────────────────────────────────────────────────
function toast(message, type = "info") {
  const icons = { success: "✓", error: "✕", info: "ℹ" };
  const el = document.createElement("div");
  el.className = `toast toast-${type}`;
  el.innerHTML = `<span>${icons[type]}</span><span>${message}</span>`;
  document.getElementById("toast-container").appendChild(el);
  setTimeout(() => {
    el.style.animation = "slideOut .2s ease forwards";
    el.addEventListener("animationend", () => el.remove());
  }, 4000);
}

// ─── Patent list (sidebar) ────────────────────────────────────────────────
async function loadPatents() {
  try {
    state.patents = await api("GET", "/patents/");
    renderSidebar();
  } catch (e) {
    toast("特許一覧の取得に失敗しました: " + e.message, "error");
  }
}

function renderSidebar() {
  const list = document.getElementById("patent-list");
  const count = document.getElementById("patent-count");
  const controls = document.getElementById("sidebar-delete-controls");
  if (!list || !count) return;
  count.textContent = state.patents.length;

  // 削除コントロールの描画
  if (controls) {
    if (state.patents.length === 0) {
      controls.innerHTML = "";
    } else if (state.selectMode) {
      const n = state.selectedIds.size;
      controls.innerHTML = `
        <button class="sb-btn sb-btn-danger" onclick="deleteSelected()" ${n === 0 ? "disabled" : ""}>削除（${n}件）</button>
        <button class="sb-btn sb-btn-cancel" onclick="exitSelectMode()">キャンセル</button>`;
    } else {
      controls.innerHTML = `
        <button class="sb-btn sb-btn-select" onclick="enterSelectMode()">選択</button>
        <button class="sb-btn sb-btn-danger" onclick="deleteAll()">全件削除</button>`;
    }
  }

  if (state.patents.length === 0) {
    list.innerHTML = `<div class="empty-list">
      <div style="font-size:28px;margin-bottom:8px">📄</div>
      <div>特許が登録されていません</div>
      <div style="font-size:12px;margin-top:4px">「＋ 新規登録」から追加してください</div>
    </div>`;
    return;
  }

  list.innerHTML = state.patents.map(p => {
    const isActive = p.id === state.selectedId;
    const isChecked = state.selectedIds.has(p.id);
    return `
      <div class="patent-item ${isActive ? "active" : ""} ${state.selectMode ? "select-mode" : ""}" data-id="${p.id}">
        ${state.selectMode
          ? `<input type="checkbox" class="patent-checkbox" data-id="${p.id}" ${isChecked ? "checked" : ""}>`
          : ""}
        <div class="patent-item-body">
          <div class="number">${escHtml(p.patent_number || "番号未設定")}</div>
          <div class="title">${escHtml(p.title || "（タイトルなし）")}</div>
          <div class="meta">
            ${statusBadge(p.analysis_status)}
            ${sourceBadge(p.source)}
          </div>
        </div>
        ${!state.selectMode
          ? `<button class="patent-delete-btn" data-id="${p.id}" title="削除">✕</button>`
          : ""}
      </div>`;
  }).join("");

  list.querySelectorAll(".patent-item").forEach(el => {
    el.addEventListener("click", e => {
      if (e.target.closest(".patent-delete-btn") || e.target.closest(".patent-checkbox")) return;
      if (state.selectMode) {
        toggleSelectId(el.dataset.id);
      } else {
        selectPatent(el.dataset.id);
      }
    });
  });
  list.querySelectorAll(".patent-delete-btn").forEach(btn => {
    btn.addEventListener("click", e => { e.stopPropagation(); deleteSingle(btn.dataset.id); });
  });
  list.querySelectorAll(".patent-checkbox").forEach(cb => {
    cb.addEventListener("change", () => toggleSelectId(cb.dataset.id));
  });
}

// ─── 削除操作 ─────────────────────────────────────────────────────────────

function enterSelectMode() {
  state.selectMode = true;
  state.selectedIds = new Set();
  renderSidebar();
}

function exitSelectMode() {
  state.selectMode = false;
  state.selectedIds = new Set();
  renderSidebar();
}

function toggleSelectId(id) {
  if (state.selectedIds.has(id)) state.selectedIds.delete(id);
  else state.selectedIds.add(id);
  renderSidebar();
}

function _clearDetailIfDeleted(deletedIds) {
  if (deletedIds.includes(state.selectedId)) {
    state.selectedId = null;
    document.getElementById("detail").style.display = "none";
    document.getElementById("welcome").style.display = "flex";
  }
}

async function deleteSingle(id) {
  const patent = state.patents.find(p => p.id === id);
  const label = patent ? (patent.patent_number || patent.title || "この特許") : "この特許";
  if (!confirm(`「${label}」を削除しますか？`)) return;
  try {
    await api("DELETE", `/patents/${id}`);
    state.patents = state.patents.filter(p => p.id !== id);
    _clearDetailIfDeleted([id]);
    renderSidebar();
    toast("削除しました", "success");
  } catch (e) {
    toast("削除に失敗しました: " + e.message, "error");
  }
}

async function deleteSelected() {
  const ids = [...state.selectedIds];
  if (ids.length === 0) return;
  if (!confirm(`選択した ${ids.length} 件を削除しますか？`)) return;
  try {
    await api("DELETE", "/patents/bulk", ids);
    state.patents = state.patents.filter(p => !state.selectedIds.has(p.id));
    _clearDetailIfDeleted(ids);
    exitSelectMode();
    toast(`${ids.length} 件を削除しました`, "success");
  } catch (e) {
    toast("削除に失敗しました: " + e.message, "error");
  }
}

async function deleteAll() {
  if (state.patents.length === 0) return;
  if (!confirm(`全 ${state.patents.length} 件を削除しますか？この操作は取り消せません。`)) return;
  const ids = state.patents.map(p => p.id);
  try {
    await api("DELETE", "/patents/bulk", ids);
    state.patents = [];
    state.selectedId = null;
    document.getElementById("detail").style.display = "none";
    document.getElementById("welcome").style.display = "flex";
    renderSidebar();
    toast("全件削除しました", "success");
  } catch (e) {
    toast("削除に失敗しました: " + e.message, "error");
  }
}

function statusBadge(status) {
  const map = {
    pending:   ["badge-pending",   "未分析"],
    analyzing: ["badge-analyzing", "分析中"],
    done:      ["badge-done",      "分析済"],
    error:     ["badge-error",     "エラー"],
  };
  const [cls, label] = map[status] || ["badge-pending", status];
  return `<span class="badge ${cls}">${label}</span>`;
}

function sourceBadge(source, url) {
  const map = { jplatpat: ["badge-jplatpat", "J-PlatPat"], pdf: ["badge-pdf", "PDF"], word: ["badge-word", "Word"] };
  const [cls, label] = map[source] || ["badge-pending", source];
  if (url) {
    return `<a href="${escHtml(url)}" target="_blank" rel="noopener noreferrer" class="badge ${cls} detail-jplatpat-link">${label} ↗</a>`;
  }
  return `<span class="badge ${cls}">${label}</span>`;
}

// ─── Patent detail ────────────────────────────────────────────────────────
async function selectPatent(id) {
  state.selectedId = id;
  stopPolling();
  renderSidebar(); // update active state

  const main = document.getElementById("main");
  document.getElementById("welcome").style.display = "none";
  document.getElementById("detail").style.display = "none";

  // show loading
  let loadingEl = document.getElementById("loading-detail");
  if (!loadingEl) {
    loadingEl = document.createElement("div");
    loadingEl.id = "loading-detail";
    loadingEl.innerHTML = `<div class="spinner" style="border-color:rgba(37,99,235,.2);border-top-color:var(--c-primary)"></div><span>読み込み中...</span>`;
    main.appendChild(loadingEl);
  }
  loadingEl.style.display = "flex";

  try {
    const patent = await api("GET", `/patents/${id}`);
    loadingEl.style.display = "none";
    renderDetail(patent);
    if (patent.analysis_status === "analyzing") startPolling(id);
  } catch (e) {
    loadingEl.style.display = "none";
    toast("詳細の取得に失敗しました: " + e.message, "error");
  }
}

function renderDetail(patent) {
  const el = document.getElementById("detail");
  el.style.display = "block";

  // Update patent in state
  const idx = state.patents.findIndex(p => p.id === patent.id);
  if (idx >= 0) state.patents[idx] = patent;
  renderSidebar();

  // 特許が切り替わったときはスクロール位置をリセット
  sourceScroll.claims = 0;
  sourceScroll.desc = 0;

  el.classList.toggle("detail-compare-mode", state.viewMode === "compare" || state.viewMode === "family");

  const analysisBtn = patent.analysis_status !== 'analyzing'
    ? `<button class="btn btn-primary" id="btn-analyze" onclick="runAnalysis('${patent.id}')">
         <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
         AI 分析実行
       </button>`
    : `<button class="btn btn-secondary" disabled>
         <span class="spinner-sm spinner" style="display:inline-block;width:14px;height:14px;border-width:2px;border-color:rgba(0,0,0,.1);border-top-color:var(--c-text-muted)"></span>
         分析中...
       </button>`;

  const jplatpatUrl = (patent.metadata || {}).jplatpat_url;

  el.innerHTML = `
    <div class="detail-header">
      <div class="detail-title">
        <h1>${escHtml(patent.title || '（タイトルなし）')}</h1>
        <div class="number" style="margin-top:6px;display:flex;gap:8px;align-items:center;flex-wrap:wrap">
          ${escHtml(patent.patent_number || '番号未設定')}
          ${sourceBadge(patent.source, jplatpatUrl)}
          <span style="font-size:12px;color:var(--c-text-muted)">${fmtDate(patent.created_at)}</span>
        </div>
      </div>
      <div class="detail-actions">
        <div class="view-mode-toggle">
          <button class="mode-btn ${state.viewMode === 'family' ? 'active' : ''}" data-mode="family" onclick="switchViewMode('family')">書誌情報</button>
          <button class="mode-btn ${state.viewMode === 'analysis' ? 'active' : ''}" data-mode="analysis" onclick="switchViewMode('analysis')">AI分析</button>
          <button class="mode-btn ${state.viewMode === 'source' ? 'active' : ''}" data-mode="source" onclick="switchViewMode('source')">原文</button>
          <button class="mode-btn ${state.viewMode === 'compare' ? 'active' : ''}" data-mode="compare" onclick="switchViewMode('compare')">AI分析・原文</button>
        </div>
        ${analysisBtn}
      </div>
    </div>

    <div class="detail-content" data-view-mode="${state.viewMode}">
      <div class="compare-left">
        <!-- AI 分析 -->
        <div id="analysis-section">
          ${renderAnalysisSection(patent)}
        </div>

        <!-- エクスポート -->
        ${patent.analysis_status === 'done' ? `
        <div class="export-bar">
          <span>エクスポート：</span>
          ${patent.drawio_xml
            ? `<a href="/reports/${patent.id}/drawio" class="btn btn-secondary btn-sm" download>📐 Draw.io XML</a>`
            : ""}
          <a href="/reports/${patent.id}/word" class="btn btn-secondary btn-sm" id="btn-word">📄 Word</a>
          <a href="/reports/${patent.id}/excel" class="btn btn-secondary btn-sm" id="btn-excel">📊 Excel</a>
        </div>` : ""}
      </div>

      <div class="compare-right">
        ${renderSourcePanel(patent)}
      </div>
      <div class="family-panel-wrapper">
        <!-- 書誌情報 -->
        <div class="card">
          <div class="card-header"><h3>書誌情報${(patent.metadata || {}).publication_type ? '：' + escHtml((patent.metadata || {}).publication_type) : ''}</h3></div>
          <div class="card-body">
            ${renderBiblio(patent)}
            ${patent.abstract ? `
              <hr class="divider" style="margin:14px 0">
              <div>
                <label style="font-size:11px;color:var(--c-text-muted);text-transform:uppercase;letter-spacing:.4px;display:block;margin-bottom:6px">要約</label>
                <div class="abstract-text">${escHtml(patent.abstract)}</div>
              </div>` : ""}
          </div>
        </div>
        <!-- ファミリー情報 -->
        ${renderFamilyPanel(patent)}
      </div>
    </div>
  `;

  // Render mermaid if present
  if (patent.analysis_status === "done" && patent.mermaid_diagram) {
    renderMermaid(patent.mermaid_diagram);
  }

  setTimeout(applyPanelLayout, 0);
}

function renderSourcePanel(patent) {
  const claimsText = patent.claims_text || "";
  const descText = patent.description_text || "";
  return `
    <div class="source-panel">
      <div class="source-tabs">
        <button class="source-tab-btn active" data-mode="claims" onclick="switchSourceTab(this)">請求の範囲</button>
        <button class="source-tab-btn" data-mode="desc" onclick="switchSourceTab(this)">詳細な説明</button>
      </div>
      <div class="source-pane-container">
        <div class="source-pane active" id="source-claims">
          ${claimsText
            ? `<div class="source-text">${escHtml(claimsText)}</div>`
            : `<div class="source-empty">データがありません</div>`}
        </div>
        <div class="source-pane" id="source-desc">
          ${descText
            ? `<div class="source-text">${escHtml(descText)}</div>`
            : `<div class="source-empty">データがありません</div>`}
        </div>
      </div>
    </div>`;
}

function switchSourceTab(btn) {
  const panel = btn.closest(".source-panel");
  const scrollEl = panel.querySelector(".source-pane-container");

  // 現在のタブのスクロール位置を保存
  const currentBtn = panel.querySelector(".source-tab-btn.active");
  if (currentBtn && scrollEl) {
    sourceScroll[currentBtn.dataset.mode] = scrollEl.scrollTop;
  }

  panel.querySelectorAll(".source-tab-btn").forEach(b => b.classList.remove("active"));
  panel.querySelectorAll(".source-pane").forEach(p => p.classList.remove("active"));
  btn.classList.add("active");
  const targetId = "source-" + btn.dataset.mode;
  const pane = document.getElementById(targetId);
  if (pane) pane.classList.add("active");

  // 切り替え先タブのスクロール位置を復元
  if (scrollEl) scrollEl.scrollTop = sourceScroll[btn.dataset.mode] || 0;
}

function applyPanelLayout() {
  const viewMode = state.viewMode;
  const detailContent = document.querySelector('.detail-content');
  const left = detailContent && detailContent.querySelector('.compare-left');
  const right = detailContent && detailContent.querySelector('.compare-right');
  if (!right) return;

  if (viewMode === 'compare' || viewMode === 'source') {
    const rect = detailContent.getBoundingClientRect();
    const availH = Math.floor(window.innerHeight - rect.top - 24);
    if (availH < 100) return;
    if (viewMode === 'compare' && left) left.style.height = availH + 'px';
    right.style.height = availH + 'px';
  } else {
    if (left) left.style.height = '';
    right.style.height = '';
  }
}

function _applySidebarCollapsed(collapsed) {
  const sidebar = document.getElementById("sidebar");
  const btn = document.getElementById("sidebar-toggle");
  if (!sidebar) return;
  sidebar.classList.toggle("collapsed", collapsed);
  if (btn) {
    btn.innerHTML = collapsed ? "&#8250;" : "&#8249;";
    btn.title = collapsed ? "サイドバーを表示" : "サイドバーを非表示";
  }
}

function toggleSidebar() {
  const sidebar = document.getElementById("sidebar");
  if (!sidebar) return;
  state.sidebarAutoCollapsed = false;
  _applySidebarCollapsed(!sidebar.classList.contains("collapsed"));
}

function switchViewMode(mode) {
  state.viewMode = mode;
  const content = document.querySelector(".detail-content");
  if (content) content.dataset.viewMode = mode;
  document.querySelectorAll(".mode-btn").forEach(btn => {
    btn.classList.toggle("active", btn.dataset.mode === mode);
  });
  const detail = document.getElementById("detail");
  if (detail) detail.classList.toggle("detail-compare-mode", mode === "compare" || mode === "family");

  // 比較モード時のみサイドバーを自動折りたたみ、他モードで自動復元
  if (mode === "compare") {
    const sidebar = document.getElementById("sidebar");
    if (sidebar && !sidebar.classList.contains("collapsed")) {
      state.sidebarAutoCollapsed = true;
      _applySidebarCollapsed(true);
    }
  } else if (state.sidebarAutoCollapsed) {
    state.sidebarAutoCollapsed = false;
    _applySidebarCollapsed(false);
  }
  setTimeout(applyPanelLayout, 0);
}

function renderAnalysisSection(patent) {
  const status = patent.analysis_status;

  if (status === "pending") {
    return `<div class="analysis-pending">
      <div style="font-size:36px;margin-bottom:8px">🔬</div>
      <h3>AI 分析が未実行です</h3>
      <p>「AI 分析実行」ボタンを押すと、Claude が特許を解析して要約・権利化ポイント・請求項構造・図解を生成します。</p>
    </div>`;
  }

  if (status === "analyzing") {
    return `<div class="analysis-analyzing">
      <div class="progress-card">
        <div class="progress-header">
          <div class="spinner" style="width:20px;height:20px;border-width:3px;flex-shrink:0"></div>
          <span class="progress-title">AI 分析中</span>
        </div>
        <div class="progress-steps">
          <span class="progress-step done">✓ テキスト送信</span>
          <span class="progress-step-arrow">→</span>
          <span class="progress-step active">⟳ Claude 解析中</span>
          <span class="progress-step-arrow">→</span>
          <span class="progress-step pending">構造化・保存</span>
        </div>
        <div class="progress-bar-wrapper">
          <div id="analysis-progress-bar" class="progress-bar-fill" style="width:0%"></div>
        </div>
        <div class="progress-time-row">
          <span>経過時間：<strong id="analysis-elapsed-time">0:00</strong></span>
          <span id="analysis-remaining-time" class="progress-remaining">推定残り 2:00</span>
        </div>
        <p class="progress-note">分析はサーバー側で実行中です。他の特許を確認してから戻っても、経過時間・分析結果はそのまま表示されます。</p>
      </div>
    </div>`;
  }

  if (status === "error") {
    return `<div class="analysis-error">
      <div style="font-size:36px;margin-bottom:8px">⚠️</div>
      <h3>分析エラー</h3>
      <p>分析中にエラーが発生しました。API キーの設定を確認して再試行してください。</p>
    </div>`;
  }

  if (status === "done") {
    const claims = patent.claims_structured || [];
    const kpHtml = renderKeyPoints(patent.key_points);

    return `
      <!-- サマリー -->
      ${patent.summary ? `
      <div class="card">
        <div class="card-header"><h3>📝 発明の概要</h3></div>
        <div class="card-body summary-card-body">
          ${renderSummaryText(patent.summary)}
        </div>
      </div>` : ""}

      <!-- 権利化ポイント -->
      ${kpHtml ? `
      <div class="card">
        <div class="card-header"><h3>🎯 権利化ポイント</h3></div>
        <div class="card-body kp-card-body">
          ${kpHtml}
        </div>
      </div>` : ""}

      <!-- 請求項構造 -->
      ${claims.length ? `
      <div class="card">
        <div class="card-header"><h3>📋 請求項の構造</h3></div>
        <div class="card-body">
          <div class="claims-list">
            ${claims.map(c => renderClaimCard(c)).join("")}
          </div>
        </div>
      </div>` : ""}

      <!-- Mermaid 図 -->
      ${patent.mermaid_diagram ? `
      <div class="card">
        <div class="card-header">
          <h3>🔷 構成図（Mermaid）</h3>
        </div>
        <div class="card-body">
          <div id="mermaid-container"></div>
          <details class="mermaid-source">
            <summary>Mermaid ソースを表示</summary>
            <pre>${escHtml(patent.mermaid_diagram)}</pre>
          </details>
        </div>
      </div>` : ""}
    `;
  }

  return "";
}

function renderClaimCard(c) {
  const typeClass = c.claim_type === "independent" ? "independent" : "dependent";
  const typeLabel = c.claim_type === "independent"
    ? "独立項"
    : `従属項<span class="claim-dep-ref">（→請求項${c.depends_on}）</span>`;
  const components = c.components || [];
  return `
    <div class="claim-card ${typeClass}">
      <div class="claim-header">
        <span class="claim-num">請求項${c.claim_number}</span>
        <span class="claim-type-tag ${c.claim_type === 'independent' ? 'claim-type-ind' : 'claim-type-dep'}">${typeLabel}</span>
        ${c.summary ? `<span class="claim-summary">— ${escHtml(c.summary)}</span>` : ""}
      </div>
      <div class="claim-body">
        ${c.text ? `<div class="claim-text">${escHtml(c.text).replace(/\n/g, "<br>")}</div>` : ""}
        ${components.length ? `
          <table class="claim-components-table">
            <thead>
              <tr><th>構成</th><th>請求項の表現</th><th>平易な説明</th></tr>
            </thead>
            <tbody>
              ${components.map(comp => `
                <tr>
                  <td class="comp-id">${escHtml(comp.id)}</td>
                  <td class="comp-original">${escHtml(comp.original || comp.description || "")}</td>
                  <td class="comp-plain">${escHtml(comp.plain || "")}</td>
                </tr>
              `).join("")}
            </tbody>
          </table>` : ""}
      </div>
    </div>`;
}

function renderFamilyPanel(patent) {
  const fi = (patent.metadata || {}).family_info;

  if (!fi || fi.source === "unknown") {
    return `
      <div class="family-unknown">
        <div style="font-size:48px;margin-bottom:16px">🌐</div>
        <h3>ファミリー情報を取得できません</h3>
        <p>Word / PDF インポートでは J-PlatPat への照会を行いません。<br>
        J-PlatPat から登録するとファミリー情報が取得されます。</p>
      </div>`;
  }

  if (!fi || !fi.families || fi.families.length === 0) {
    return `
      <div class="card">
        <div class="card-header"><h3>🌐 ファミリー情報</h3></div>
        <div class="card-body">
          <div class="source-empty">ファミリー情報が見つかりませんでした。</div>
        </div>
      </div>`;
  }

  const familyRows = fi.families.map(f => `
    <tr>
      <td>${escHtml(f.country || '-')}</td>
      <td class="family-num-cell">${escHtml(f.application_number || '-')}</td>
      <td>${escHtml(f.filing_date || '-')}</td>
      <td class="family-num-cell">${escHtml(f.publication_number || '-')}</td>
      <td class="family-num-cell">${escHtml(f.registration_number || '-')}</td>
    </tr>`).join('');

  const docSections = fi.document_sections || [];
  const docSectionsHtml = docSections.map(sec => {
    const headerHtml = (sec.headers || []).map(h => `<th>${escHtml(h)}</th>`).join('');
    const headers = sec.headers || [];
    const rowsHtml = (sec.rows || []).map(row =>
      `<tr>${row.map((cell, i) => {
        const cls = (headers[i] || '').includes('提出日') ? ' class="family-doc-date"' : '';
        return `<td${cls}>${escHtml(cell)}</td>`;
      }).join('')}</tr>`
    ).join('');
    return `
      <div class="family-doc-section">
        <div class="family-doc-label" onclick="toggleFamilyDocSection(this)">
          <span>${escHtml(sec.label || '')}</span>
          <button class="btn btn-secondary btn-sm family-doc-toggle" onclick="event.stopPropagation();toggleFamilyDocSection(this.closest('.family-doc-label'))">開く ▼</button>
        </div>
        <div class="family-doc-body" style="display:none">
          <table class="family-doc-table">
            <thead><tr>${headerHtml}</tr></thead>
            <tbody>${rowsHtml}</tbody>
          </table>
        </div>
      </div>`;
  }).join('');

  return `
    <div class="card">
      <div class="card-header">
        <h3>🌐 ファミリー一覧</h3>
        <span class="family-count-badge">${fi.families.length}件</span>
      </div>
      <div class="card-body" style="padding:0;overflow-x:auto">
        <table class="family-table">
          <thead>
            <tr>
              <th>国・地域</th>
              <th>出願番号</th>
              <th>出願日</th>
              <th>公開番号</th>
              <th>登録番号</th>
            </tr>
          </thead>
          <tbody>${familyRows}</tbody>
        </table>
      </div>
    </div>

    ${docSections.length ? `
    <div class="card">
      <div class="card-header">
        <h3>書類情報</h3>
        <div style="display:flex;gap:6px">
          <button class="btn btn-secondary btn-sm" onclick="toggleAllFamilyDocSections(this, true)">全て開く</button>
          <button class="btn btn-secondary btn-sm" onclick="toggleAllFamilyDocSections(this, false)">全て閉じる</button>
        </div>
      </div>
      <div style="padding:0 0 8px">
        ${docSectionsHtml}
      </div>
    </div>` : ''}`;
}

function toggleFamilyDocSection(labelEl) {
  const section = labelEl.closest('.family-doc-section');
  const body = section ? section.querySelector('.family-doc-body') : null;
  const btn = section ? section.querySelector('.family-doc-toggle') : null;
  if (!body) return;
  const open = body.style.display === 'none';
  body.style.display = open ? 'block' : 'none';
  if (btn) btn.textContent = open ? '閉じる ▲' : '開く ▼';
}

function toggleAllFamilyDocSections(btn, expand) {
  const card = btn.closest('.card');
  if (!card) return;
  card.querySelectorAll('.family-doc-body').forEach(b => {
    b.style.display = expand ? 'block' : 'none';
  });
  card.querySelectorAll('.family-doc-toggle').forEach(t => {
    t.textContent = expand ? '閉じる ▲' : '開く ▼';
  });
}

function biblioRow(label, value) {
  if (!value) return "";
  return `<div class="biblio-item">
    <label>${label}</label>
    <span>${escHtml(String(value))}</span>
  </div>`;
}

function renderBiblio(patent) {
  const m = patent.metadata || {};
  const isRegistered = !!m.registration_number;
  const applicantLabel = (isRegistered && m.patentee) ? "特許権者" : "出願人";
  const applicantValue = (isRegistered && m.patentee) ? m.patentee : (patent.applicant || m.applicant || "");

  const urlHtml = "";

  // 特許権者
  const applicantHtml = `<div class="biblio-entry"><span class="biblio-key">【${applicantLabel}】</span><span class="biblio-val">${applicantValue ? escHtml(applicantValue) : "-"}</span></div>`;

  // 番号と日付テーブル
  const pubNumber = m.publication_number || (!isRegistered ? patent.patent_number : "");
  const numDateRows = [
    ["出願", m.app_number, patent.filing_date || m.filing_date],
    ["公開", pubNumber, patent.publication_date || m.publication_date],
    ...(isRegistered ? [["登録", m.registration_number, m.registration_date]] : []),
  ];
  const numDateTable = `<div class="biblio-entry biblio-numdate" style="align-items:flex-start">
    <span class="biblio-key">【番号・日付】</span>
    <table class="numdate-table">
      <thead><tr><th></th><th>番号</th><th>日付</th></tr></thead>
      <tbody>${numDateRows.map(([label, num, date]) =>
        `<tr><th>${label}</th><td>${num ? escHtml(num) : "—"}</td><td>${date ? escHtml(date) : "—"}</td></tr>`
      ).join("")}</tbody>
    </table>
  </div>`;

  // 経過情報（ラベルと値を分離して他の行と位置を揃える）
  const progressHtml = (() => {
    const statusVal = m.status ? `<span class="biblio-val">${escHtml(m.status)}</span>` : "";
    if (!m.progress_info) {
      return m.status
        ? `<div class="biblio-entry"><span class="biblio-key">【経過情報】</span>${statusVal}</div>`
        : "";
    }
    let innerContent;
    try {
      const parsed = JSON.parse(m.progress_info);
      if (parsed && Array.isArray(parsed.rows) && parsed.rows.length > 0) {
        const HEADERS = ["日付", "", "内容", "カテゴリ"];
        const headerRow = `<tr>${HEADERS.map(h => `<th>${h}</th>`).join("")}</tr>`;
        const dataRows = parsed.rows
          .map(row => {
            const rev = [...row].reverse();
            return `<tr>${rev.map(cell => `<td>${escHtml(cell)}</td>`).join("")}</tr>`;
          })
          .join("");
        innerContent = `<table class="progress-table"><thead>${headerRow}</thead><tbody>${dataRows}</tbody></table>`;
      } else {
        innerContent = `<pre class="progress-text">${escHtml(m.progress_info)}</pre>`;
      }
    } catch (_) {
      innerContent = `<pre class="progress-text">${escHtml(m.progress_info)}</pre>`;
    }
    return `<div class="biblio-entry" style="align-items:flex-start">
      <span class="biblio-key">【経過情報】</span>
      <div>${statusVal}<details style="margin-top:4px">
        <summary>詳細情報表示</summary>
        ${innerContent}
      </details></div>
     </div>`;
  })();

  // 表示順に組み立て（3セクションを1グループにまとめて区切り線を除去）
  const sec1 = [urlHtml, applicantHtml].filter(Boolean).join("");
  let inner = "";
  if (sec1) inner += sec1;
  inner += numDateTable;
  if (progressHtml) inner += progressHtml;
  return `<div class="biblio-group">${inner}</div>`;
}

// ─── Mermaid rendering ────────────────────────────────────────────────────
let mermaidReady = false;
function initMermaid() {
  if (typeof mermaid !== "undefined") {
    mermaid.initialize({ startOnLoad: false, theme: "default", securityLevel: "loose", fontFamily: "inherit" });
    mermaidReady = true;
  }
}

async function renderMermaid(code) {
  const container = document.getElementById("mermaid-container");
  if (!container) return;
  if (!mermaidReady) { container.textContent = code; return; }
  try {
    const id = "mermaid-" + Date.now();
    const { svg } = await mermaid.render(id, code);
    container.innerHTML = svg;
  } catch (e) {
    container.innerHTML = `<pre style="font-size:12px;color:var(--c-error)">${escHtml(e.message)}</pre>
      <pre style="font-size:11px;margin-top:8px">${escHtml(code)}</pre>`;
  }
}

// ─── AI Analysis ──────────────────────────────────────────────────────────
async function runAnalysis(patentId) {
  // 新規分析開始 → 前回の経過時間をリセット（同じ特許の再分析も含む）
  state.pollingPatentId = null;
  state.analysisStartTime = null;
  const btn = document.getElementById("btn-analyze");
  if (btn) { btn.disabled = true; btn.innerHTML = `<span class="spinner-sm spinner" style="display:inline-block;width:14px;height:14px;border-width:2px;border-color:rgba(255,255,255,.3);border-top-color:#fff"></span> 開始中...`; }
  try {
    await api("POST", `/analyze/${patentId}`);
    // POST は即座に返る。selectPatent で "analyzing" 状態を描画 → startPolling が走る
    await selectPatent(patentId);
  } catch (e) {
    if (e.message.includes("503") || e.message.includes("API キー")) {
      toast("Claude API キーが設定されていません。.env ファイルを確認してください。", "error");
    } else {
      toast("分析中にエラーが発生しました: " + e.message, "error");
    }
    await loadPatents();
    if (state.selectedId === patentId) await selectPatent(patentId);
  }
}

function startPolling(patentId) {
  // 同じ特許に戻った場合は analysisStartTime を引き継ぐ（タブ切り替え対応）
  const resuming = state.pollingPatentId === patentId && state.analysisStartTime !== null;
  stopPolling();
  state.pollingPatentId = patentId;
  if (!resuming) state.analysisStartTime = Date.now();

  // 1秒ごとに経過時間・進捗バーを更新（描画直後に即時呼び出しで 0:00 フラッシュを防ぐ）
  updateProgressUI();
  state.progressTimer = setInterval(() => updateProgressUI(), 1000);

  // 2秒ごとに完了チェック
  state.pollingTimer = setInterval(async () => {
    try {
      const patent = await api("GET", `/patents/${patentId}`);
      if (patent.analysis_status !== "analyzing") {
        stopPolling(true);  // 完了 → タイマー状態をクリア
        renderDetail(patent);
        if (patent.analysis_status === "done") toast("AI 分析が完了しました", "success");
        if (patent.analysis_status === "error") toast("分析中にエラーが発生しました", "error");
        await loadPatents();
      }
    } catch (e) {
      stopPolling(true);
    }
  }, 2000);
}

function stopPolling(clearState = false) {
  if (state.pollingTimer) { clearInterval(state.pollingTimer); state.pollingTimer = null; }
  if (state.progressTimer) { clearInterval(state.progressTimer); state.progressTimer = null; }
  if (clearState) {
    // 完了・エラー時のみリセット（ナビゲーション離脱時は引き継ぐため残す）
    state.analysisStartTime = null;
    state.pollingPatentId = null;
  }
}

function updateProgressUI() {
  if (!state.analysisStartTime) return;
  const elapsed = Math.floor((Date.now() - state.analysisStartTime) / 1000);
  const estimatedTotal = 120;
  const pct = Math.min(Math.floor((elapsed / estimatedTotal) * 95), 95);

  const elapsedEl = document.getElementById("analysis-elapsed-time");
  const barEl = document.getElementById("analysis-progress-bar");
  const remainingEl = document.getElementById("analysis-remaining-time");

  if (elapsedEl) elapsedEl.textContent = formatTime(elapsed);
  if (barEl) barEl.style.width = pct + "%";
  if (remainingEl) {
    const remaining = Math.max(0, estimatedTotal - elapsed);
    remainingEl.textContent = elapsed < estimatedTotal
      ? `推定残り ${formatTime(remaining)}`
      : "もうすぐ完了します...";
  }
}

function formatTime(seconds) {
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}:${s.toString().padStart(2, "0")}`;
}

// ─── Key Points rendering ─────────────────────────────────────────────────

function _normalizeText(raw) {
  if (!raw || typeof raw !== "string") return "";
  return raw
    .replace(/\\n/g, "\n")   // リテラル \n (バックスラッシュ+n) → 実際の改行
    .replace(/^["'\s]+/, "") // 先頭の " や空白（ダブルエンコード残骸）を除去
    .replace(/["'\s]+$/, "") // 末尾の " や空白を除去
    .trim();
}

function renderKeyPoints(rawKeyPoints) {
  if (!rawKeyPoints) return "";

  // 配列形式（旧フォーマット）
  if (Array.isArray(rawKeyPoints)) {
    if (!rawKeyPoints.length) return "";
    return `<ul class="key-points-list">${rawKeyPoints.map(kp => `<li>${escHtml(kp)}</li>`).join("")}</ul>`;
  }

  // 文字列形式（新フォーマット: 【...】セクション）
  if (typeof rawKeyPoints === "string") {
    const str = _normalizeText(rawKeyPoints);
    if (!str) return "";
    const sections = parseKpSections(str);
    if (sections.length) {
      return sections.map(renderKpSection).join("");
    }
    return `<div class="key-points-text">${escHtml(str).replace(/\n/g, "<br>")}</div>`;
  }

  return "";
}

function parseKpSections(text) {
  const sections = [];
  const parts = text.split(/(?=【[^】]*】)/);
  for (const part of parts) {
    const m = part.match(/^【([^】]*)】\s*([\s\S]*)/);
    if (m) {
      sections.push({ header: m[1].trim(), body: m[2].trim() });
    } else if (part.trim()) {
      sections.push({ header: "", body: part.trim() });
    }
  }
  return sections;
}

function _parseKpLine(line) {
  const clean = line.replace(/^\\n/, "").replace(/^[・•\-]\s*/, "");
  if (!clean) return null;
  const m = clean.match(/^([^：:]{1,20})[：:]\s*(.+)/);
  if (m && m[2].trim()) return { type: "labeled", label: m[1].trim(), content: m[2].trim() };
  return { type: "plain", content: clean };
}

function renderKpSection(sec) {
  const lines = sec.body.split(/\n+/).filter(l => l.trim());
  const parsed = lines.map(_parseKpLine).filter(Boolean);
  if (!parsed.length) return "";

  let bodyHtml;
  if (parsed.every(l => l.type === "labeled")) {
    // 全行ラベル付き → 同じラベルをまとめてテーブルで文頭揃え
    const labelOrder = [];
    const labelMap = new Map();
    for (const l of parsed) {
      if (!labelMap.has(l.label)) {
        labelMap.set(l.label, []);
        labelOrder.push(l.label);
      }
      labelMap.get(l.label).push(l.content);
    }
    const rows = labelOrder.map(label => {
      const items = labelMap.get(label);
      const contentHtml = items.map(item => `<div class="kp-content-item">${escHtml(item)}</div>`).join("");
      return `<tr>
        <td class="kp-label-cell"><span class="kp-label-badge">${escHtml(label)}</span></td>
        <td class="kp-content-cell">${contentHtml}</td>
      </tr>`;
    }).join("");
    bodyHtml = `<table class="kp-labeled-table">${rows}</table>`;
  } else {
    // 混在 → リスト（連続する同ラベルをグループ化）
    const items = parsed.map(l =>
      l.type === "labeled"
        ? `<li class="kp-labeled-item"><span class="kp-label-badge">${escHtml(l.label)}</span><span class="kp-label-content">${escHtml(l.content)}</span></li>`
        : `<li>${escHtml(l.content)}</li>`
    ).join("");
    bodyHtml = `<ul class="kp-section-body">${items}</ul>`;
  }

  return `
    <div class="kp-section">
      ${sec.header ? `<div class="kp-section-header">${escHtml(sec.header)}</div>` : ""}
      ${bodyHtml}
    </div>`;
}

// ─── Summary rendering ────────────────────────────────────────────────────

function renderSummaryValue(value) {
  // （請求項N）パターンを含む場合はバッジ付きリストに分割
  if (/（請求項\d+）/.test(value)) {
    const parts = value.split(/(?=（請求項\d+）)/).filter(p => p.trim());
    return parts.map(part => {
      const m = part.match(/^（請求項(\d+)）\s*([\s\S]*)/);
      if (m) {
        return `<div class="summary-claim-item">
          <span class="summary-claim-badge">請求項${escHtml(m[1])}</span>
          <span class="summary-claim-text">${escHtml(m[2].trim())}</span>
        </div>`;
      }
      return `<div class="summary-claim-item"><span class="summary-claim-text">${escHtml(part.trim())}</span></div>`;
    }).join("");
  }
  return escHtml(value);
}

function renderSummaryText(raw) {
  if (!raw) return "";
  const text = _normalizeText(raw);
  if (!text) return "";

  const lines = text.split(/\n+/).filter(l => l.trim());
  if (!lines.length) return "";

  // ・label：value 形式（発明の概要の5項目）を2列テーブルで表示
  const hasLabels = lines.some(l => /^[・•]?\s*[^\s：:]+[：:]/.test(l));
  if (hasLabels) {
    const rows = lines.map(line => {
      const clean = line.replace(/^[・•]\s*/, "");
      const m = clean.match(/^([^：:]+)[：:]\s*([\s\S]*)/);
      if (m) {
        const label = m[1].trim();
        const value = m[2].trim();
        const hasClaimRefs = /（請求項\d+）/.test(value);
        const labelHtml = hasClaimRefs
          ? `${escHtml(label)}<span class="summary-label-note">独立項のみ</span>`
          : escHtml(label);
        return `<tr>
          <td class="summary-label-cell">${labelHtml}</td>
          <td class="summary-value-cell">${renderSummaryValue(value)}</td>
        </tr>`;
      }
      return `<tr><td colspan="2" class="summary-value-cell">${escHtml(clean)}</td></tr>`;
    }).join("");
    return `<table class="summary-table">${rows}</table>`;
  }

  return `<div class="summary-text">${escHtml(text).replace(/\n/g, "<br>")}</div>`;
}

// ─── Registration Modal ───────────────────────────────────────────────────
function openModal() {
  document.getElementById("modal").classList.remove("hidden");
  document.getElementById("register-number-input").focus();
}

function closeModal() {
  document.getElementById("modal").classList.add("hidden");
  resetModal();
}

function resetModal() {
  document.getElementById("register-number-input").value = "";
  document.getElementById("word-filename").textContent = "";
  document.getElementById("word-file-input").value = "";
  setActiveTab("tab-number");
  setRegisterLoading(false);
}

function setActiveTab(tabId) {
  document.querySelectorAll(".tab-btn").forEach(btn => btn.classList.remove("active"));
  document.querySelectorAll(".tab-pane").forEach(pane => pane.classList.remove("active"));
  document.getElementById(tabId + "-btn").classList.add("active");
  document.getElementById(tabId + "-pane").classList.add("active");
}

function setRegisterLoading(loading, msg) {
  const btn = document.getElementById("btn-register");
  if (loading) {
    btn.disabled = true;
    btn.innerHTML = `<span class="spinner-sm spinner" style="display:inline-block;width:14px;height:14px;border-width:2px;border-color:rgba(255,255,255,.3);border-top-color:#fff"></span> ${msg || '登録中...'}`;
  } else {
    btn.disabled = false;
    btn.innerHTML = "登録";
  }
}

async function submitRegister() {
  const activePane = document.querySelector(".tab-pane.active");
  const tabId = activePane.id;
  let registeredId = null;

  try {
    if (tabId === "tab-number-pane") {
      const num = document.getElementById("register-number-input").value.trim();
      if (!num) { toast("特許番号を入力してください", "error"); return; }
      setRegisterLoading(true, "J-PlatPat から取得中...");
      const form = new FormData();
      form.append("patent_number", num);
      const res = await api("POST", "/patents/from-number", form);
      toast(`「${res.title || res.patent_number}」を登録しました`, "success");
      registeredId = res.id;

    } else if (tabId === "tab-word-pane") {
      const fileInput = document.getElementById("word-file-input");
      if (!fileInput.files.length) { toast("Word ファイルを選択してください", "error"); return; }
      setRegisterLoading(true, "Word を読み込み中...");
      const form = new FormData();
      form.append("file", fileInput.files[0]);
      const res = await api("POST", "/patents/from-word", form);
      toast("Word から特許を登録しました", "success");
      registeredId = res.id;
    }
  } catch (e) {
    setRegisterLoading(false);
    toast("登録に失敗しました: " + e.message, "error");
    return;
  }

  if (registeredId) {
    closeModal();
    await loadPatents();
    selectPatent(registeredId);
  }
}

function setupFileUpload(inputId, labelId) {
  const input = document.getElementById(inputId);
  const label = document.getElementById(labelId);
  const area = label.closest(".upload-area");

  input.addEventListener("change", () => {
    if (input.files.length) {
      label.textContent = input.files[0].name;
      area.style.borderStyle = "solid";
    }
  });

  area.addEventListener("dragover", e => { e.preventDefault(); area.classList.add("drag-over"); });
  area.addEventListener("dragleave", () => area.classList.remove("drag-over"));
  area.addEventListener("drop", e => {
    e.preventDefault();
    area.classList.remove("drag-over");
    if (e.dataTransfer.files.length) {
      const dt = new DataTransfer();
      dt.items.add(e.dataTransfer.files[0]);
      input.files = dt.files;
      label.textContent = e.dataTransfer.files[0].name;
      area.style.borderStyle = "solid";
    }
  });
}

// ─── Utilities ────────────────────────────────────────────────────────────
function escHtml(str) {
  return String(str ?? "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}

function fmtDate(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.getFullYear()}/${String(d.getMonth()+1).padStart(2,"0")}/${String(d.getDate()).padStart(2,"0")}`;
}

// ─── Init ─────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  initMermaid();

  // Register button
  document.getElementById("btn-new").addEventListener("click", openModal);

  // Modal close
  document.getElementById("btn-close-modal").addEventListener("click", closeModal);
  document.getElementById("btn-cancel").addEventListener("click", closeModal);
  document.getElementById("modal").addEventListener("click", e => {
    if (e.target === e.currentTarget) closeModal();
  });

  // Register submit
  document.getElementById("btn-register").addEventListener("click", submitRegister);
  document.getElementById("register-number-input").addEventListener("keydown", e => {
    if (e.key === "Enter") submitRegister();
  });

  // Tabs
  ["tab-number", "tab-word"].forEach(tabId => {
    document.getElementById(tabId + "-btn").addEventListener("click", () => setActiveTab(tabId));
  });

  // File uploads
  setupFileUpload("word-file-input", "word-filename");

  // Re-apply panel height on window resize
  window.addEventListener('resize', applyPanelLayout);

  // Load initial data
  loadPatents();
});
