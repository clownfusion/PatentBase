/* ===== PatentBase App JS ===== */
"use strict";

// ─── State ────────────────────────────────────────────────────────────────
const state = {
  patents: [],
  selectedId: null,
  pollingTimer: null,
};

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
  count.textContent = state.patents.length;

  if (state.patents.length === 0) {
    list.innerHTML = `<div class="empty-list">
      <div style="font-size:28px;margin-bottom:8px">📄</div>
      <div>特許が登録されていません</div>
      <div style="font-size:12px;margin-top:4px">「＋ 新規登録」から追加してください</div>
    </div>`;
    return;
  }

  list.innerHTML = state.patents.map(p => `
    <div class="patent-item ${p.id === state.selectedId ? 'active' : ''}" data-id="${p.id}">
      <div class="number">${p.patent_number || '番号未設定'}</div>
      <div class="title">${p.title || '（タイトルなし）'}</div>
      <div class="meta">
        ${statusBadge(p.analysis_status)}
        ${sourceBadge(p.source)}
      </div>
    </div>
  `).join("");

  list.querySelectorAll(".patent-item").forEach(el => {
    el.addEventListener("click", () => selectPatent(el.dataset.id));
  });
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

function sourceBadge(source) {
  const map = { jplatpat: ["badge-jplatpat", "J-PlatPat"], pdf: ["badge-pdf", "PDF"], word: ["badge-word", "Word"] };
  const [cls, label] = map[source] || ["badge-pending", source];
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

  el.innerHTML = `
    <div class="detail-header">
      <div class="detail-title">
        <h1>${escHtml(patent.title || '（タイトルなし）')}</h1>
        <div class="number" style="margin-top:6px;display:flex;gap:8px;align-items:center">
          ${escHtml(patent.patent_number || '番号未設定')}
          ${sourceBadge(patent.source)}
          <span style="font-size:12px;color:var(--c-text-muted)">${fmtDate(patent.created_at)}</span>
        </div>
      </div>
      <div class="detail-actions">
        ${patent.analysis_status !== 'analyzing'
          ? `<button class="btn btn-primary" id="btn-analyze" onclick="runAnalysis('${patent.id}')">
               <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5"/></svg>
               AI 分析実行
             </button>`
          : `<button class="btn btn-secondary" disabled>
               <span class="spinner-sm spinner" style="display:inline-block;width:14px;height:14px;border-width:2px;border-color:rgba(0,0,0,.1);border-top-color:var(--c-text-muted)"></span>
               分析中...
             </button>`
        }
      </div>
    </div>

    <!-- 書誌情報 -->
    <div class="card">
      <div class="card-header"><h3>書誌情報</h3></div>
      <div class="card-body">
        <div class="biblio-grid">
          ${biblioRow("出願人", patent.applicant || patent.metadata?.applicant)}
          ${biblioRow("IPC 分類", patent.ipc_codes)}
          ${biblioRow("データソース", patent.source)}
          ${biblioRow("ステータス", patent.analysis_status)}
        </div>
        ${patent.abstract ? `
          <hr class="divider" style="margin:14px 0">
          <div>
            <label style="font-size:11px;color:var(--c-text-muted);text-transform:uppercase;letter-spacing:.4px;display:block;margin-bottom:6px">要約</label>
            <div class="abstract-text">${escHtml(patent.abstract)}</div>
          </div>` : ""}
      </div>
    </div>

    <!-- AI 分析 -->
    <div id="analysis-section">
      ${renderAnalysisSection(patent)}
    </div>

    <!-- エクスポート -->
    ${patent.analysis_status === 'done' ? `
    <div class="export-bar">
      <span>エクスポート：</span>
      ${patent.drawio_xml
        ? `<a href="/reports/${patent.id}/drawio" class="btn btn-secondary btn-sm" download>
             📐 Draw.io XML
           </a>`
        : ""}
      <a href="/reports/${patent.id}/word" class="btn btn-secondary btn-sm" id="btn-word">
        📄 Word
      </a>
      <a href="/reports/${patent.id}/excel" class="btn btn-secondary btn-sm" id="btn-excel">
        📊 Excel
      </a>
    </div>` : ""}
  `;

  // Render mermaid if present
  if (patent.analysis_status === "done" && patent.mermaid_diagram) {
    renderMermaid(patent.mermaid_diagram);
  }
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
      <div class="spinner"></div>
      <div>
        <p>分析中です...</p>
        <small>Claude API が特許を解析しています。しばらくお待ちください。</small>
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
    const keyPoints = (() => {
      try { return JSON.parse(patent.key_points || "[]"); } catch { return []; }
    })();
    const claims = patent.claims_structured || [];

    return `
      <!-- サマリー -->
      ${patent.summary ? `
      <div class="card">
        <div class="card-header"><h3>📝 発明の概要</h3></div>
        <div class="card-body">
          <div class="summary-text">${escHtml(patent.summary)}</div>
        </div>
      </div>` : ""}

      <!-- 権利化ポイント -->
      ${keyPoints.length ? `
      <div class="card">
        <div class="card-header"><h3>🎯 権利化ポイント</h3></div>
        <div class="card-body" style="padding-top:8px;padding-bottom:8px">
          <ul class="key-points-list">
            ${keyPoints.map(kp => `<li>${escHtml(kp)}</li>`).join("")}
          </ul>
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
  const typeLabel = c.claim_type === "independent" ? "独立項" : `従属項（→請求項${c.depends_on}）`;
  const components = c.components || [];
  return `
    <div class="claim-card ${typeClass}">
      <div class="claim-header">
        <span class="claim-num">請求項 ${c.claim_number}</span>
        <span class="badge ${c.claim_type === 'independent' ? 'badge-jplatpat' : 'badge-pending'}">${typeLabel}</span>
        ${c.summary ? `<span class="claim-summary">— ${escHtml(c.summary)}</span>` : ""}
      </div>
      <div class="claim-body">
        ${c.text ? `<div class="claim-text">${escHtml(c.text).substring(0, 200)}${c.text.length > 200 ? "…" : ""}</div>` : ""}
        ${components.length ? `
          <div class="claim-components">
            ${components.map(comp => `
              <span class="claim-comp"><span class="id">${escHtml(comp.id)}.</span>${escHtml(comp.description)}</span>
            `).join("")}
          </div>` : ""}
      </div>
    </div>`;
}

function biblioRow(label, value) {
  if (!value) return "";
  return `<div class="biblio-item">
    <label>${label}</label>
    <span>${escHtml(String(value))}</span>
  </div>`;
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
  const btn = document.getElementById("btn-analyze");
  if (btn) { btn.disabled = true; btn.innerHTML = `<span class="spinner-sm spinner" style="display:inline-block;width:14px;height:14px;border-width:2px;border-color:rgba(255,255,255,.3);border-top-color:#fff"></span> 開始中...`; }
  try {
    await api("POST", `/analyze/${patentId}`);
    toast("AI 分析が完了しました", "success");
    await selectPatent(patentId);
  } catch (e) {
    if (e.message.includes("503") || e.message.includes("API キー")) {
      toast("Claude API キーが設定されていません。.env ファイルを確認してください。", "error");
    } else {
      toast("分析中にエラーが発生しました: " + e.message, "error");
    }
    // Refresh to show error state
    await loadPatents();
    if (state.selectedId === patentId) await selectPatent(patentId);
  }
}

function startPolling(patentId) {
  stopPolling();
  state.pollingTimer = setInterval(async () => {
    try {
      const patent = await api("GET", `/patents/${patentId}`);
      if (patent.analysis_status !== "analyzing") {
        stopPolling();
        renderDetail(patent);
        if (patent.analysis_status === "done") toast("AI 分析が完了しました", "success");
        if (patent.analysis_status === "error") toast("分析中にエラーが発生しました", "error");
        await loadPatents();
      }
    } catch (e) {
      stopPolling();
    }
  }, 3000);
}

function stopPolling() {
  if (state.pollingTimer) { clearInterval(state.pollingTimer); state.pollingTimer = null; }
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
  document.getElementById("pdf-filename").textContent = "";
  document.getElementById("word-filename").textContent = "";
  document.getElementById("pdf-file-input").value = "";
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

  try {
    if (tabId === "tab-number-pane") {
      const num = document.getElementById("register-number-input").value.trim();
      if (!num) { toast("特許番号を入力してください", "error"); return; }
      setRegisterLoading(true, "J-PlatPat から取得中...");
      const form = new FormData();
      form.append("patent_number", num);
      const res = await api("POST", "/patents/from-number", form);
      toast(`「${res.title || res.patent_number}」を登録しました`, "success");
      closeModal();
      await loadPatents();
      selectPatent(res.id);

    } else if (tabId === "tab-pdf-pane") {
      const fileInput = document.getElementById("pdf-file-input");
      if (!fileInput.files.length) { toast("PDF ファイルを選択してください", "error"); return; }
      setRegisterLoading(true, "PDF を読み込み中...");
      const form = new FormData();
      form.append("file", fileInput.files[0]);
      const res = await api("POST", "/patents/from-pdf", form);
      toast("PDF から特許を登録しました", "success");
      closeModal();
      await loadPatents();
      selectPatent(res.id);

    } else if (tabId === "tab-word-pane") {
      const fileInput = document.getElementById("word-file-input");
      if (!fileInput.files.length) { toast("Word ファイルを選択してください", "error"); return; }
      setRegisterLoading(true, "Word を読み込み中...");
      const form = new FormData();
      form.append("file", fileInput.files[0]);
      const res = await api("POST", "/patents/from-word", form);
      toast("Word から特許を登録しました", "success");
      closeModal();
      await loadPatents();
      selectPatent(res.id);
    }
  } catch (e) {
    setRegisterLoading(false);
    toast("登録に失敗しました: " + e.message, "error");
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
      input.files = e.dataTransfer.files;
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
  ["tab-number", "tab-pdf", "tab-word"].forEach(tabId => {
    document.getElementById(tabId + "-btn").addEventListener("click", () => setActiveTab(tabId));
  });

  // File uploads
  setupFileUpload("pdf-file-input", "pdf-filename");
  setupFileUpload("word-file-input", "word-filename");

  // Load initial data
  loadPatents();
});
