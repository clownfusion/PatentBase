# PatentBase フロントエンド実装設計

CLAUDE.md の「フロントエンド設計」補足資料。実装パターン・CSS クラス設計の詳細を記載する。

---

## detail-header のスティッキー固定

詳細画面のタブ切り替えボタン行（`.detail-header`）はスクロールしても常に画面上部に表示されるよう `position: sticky` を設定している。

```css
.detail-header {
    position: sticky;
    top: 0;
    z-index: 5;
    background: var(--c-bg);
    padding-top: 10px;
    margin-top: -10px;
    padding-bottom: 10px;
    box-shadow: 0 2px 6px rgba(0,0,0,.06);
}
```

---

## ファミリー情報パネル（`renderFamilyPanel`）

`family` モード（書誌情報タブ）では `family-panel-wrapper` に書誌情報カードとファミリー情報を表示する。

**アコーディオン構成:**
各ファミリー出願（例: JP・US・EP）ごとに折りたたみ可能なセクションを生成する。

```javascript
// app.js の主要関数
renderFamilyPanel(patent)               // ファミリー情報全体の HTML を生成
toggleFamilyDocSection(labelEl)         // 個別セクションの展開/折りたたみ
toggleAllFamilyDocSections(btn, expand) // 全セクション一括操作
```

**提出日列の折り返し防止:**
列ヘッダーに `"提出日"` を含む場合に `class="family-doc-date"` を付与する。

```javascript
const cls = (headers[i] || '').includes('提出日') ? ' class="family-doc-date"' : '';
```

```css
.family-doc-date { white-space: nowrap; }
```

**CSS アコーディオン構造:**

```css
.family-doc-section { border-top: 1px solid var(--c-border); }
.family-doc-label   { display:flex; align-items:center; justify-content:space-between;
                      padding:10px 20px; cursor:pointer; }
.family-doc-label:hover { background: #f4f5f7; }
.family-doc-body    { padding: 0 20px 16px; overflow-x: auto; }
```

---

## 原文タブパネル（`renderSourcePanel`）

### DOM 構造

```html
<div class="source-panel">
  <div class="source-tabs">          <!-- スクロール範囲外。常に表示 -->
    <button data-mode="claims">請求の範囲</button>
    <button data-mode="desc">詳細な説明</button>
  </div>
  <div class="source-pane-container">  <!-- flex: 1; overflow-y: auto のスクロール容器 -->
    <div class="source-pane active" id="source-claims">...</div>
    <div class="source-pane"        id="source-desc">...</div>
  </div>
</div>
```

### CSS 構造

```css
.source-panel          { display: flex; flex-direction: column; flex: 1; min-height: 0; overflow: hidden; }
.source-tabs           { flex-shrink: 0; }
.source-pane-container { flex: 1; overflow-y: auto; min-height: 0; }
```

### スクロール位置の保存・復元

`sourceScroll = { claims: 0, desc: 0 }` でタブごとのスクロール位置を保持する。
スクロール対象は `.source-pane-container`（`.compare-right` ではない）。

```javascript
// switchSourceTab の処理順
// 1. panel.querySelector(".source-pane-container").scrollTop を sourceScroll[currentMode] に保存
// 2. 新タブの DOM を active に切り替え
// 3. source-pane-container の scrollTop を sourceScroll[newMode] に復元
```

---

## compare/source モードのパネル高さ管理（`applyPanelLayout`）

CSS の `position: sticky` や `max-height` に依存せず JS で高さを設定する。`max-height` のみで `height` がない flex コンテナ内では子要素の `flex: 1` が展開できないため。

```javascript
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
```

**呼び出しタイミング:**
- `switchViewMode(mode)` → `setTimeout(applyPanelLayout, 0)`
- `renderDetail(patent)` → `setTimeout(applyPanelLayout, 0)`
- `window.addEventListener('resize', applyPanelLayout)`

**compare モードの CSS:**

```css
.detail-content[data-view-mode="compare"] .compare-left {
  flex: 1; min-width: 0; overflow-y: auto;  /* height は JS で設定 */
}
.detail-content[data-view-mode="compare"] .compare-right {
  flex: 1; min-width: 0; overflow: hidden; display: flex; flex-direction: column;
  /* position: sticky は使わない。height は JS で設定 */
}
```

---

## AI 分析プログレッシブ表示（`renderAnalysisSection`）

### analyzing 状態の部分表示

`analysis_status === "analyzing"` の間、完了したステップの結果と未完了のスケルトンカードを並べて表示する。

**ステップ判定:**

```javascript
const hasSummary  = !!(patent.summary && patent.summary.length > 0);
const hasKeyPoints = Array.isArray(patent.key_points)
  ? patent.key_points.length > 0
  : !!(patent.key_points && patent.key_points.length > 0);
const hasClaims   = !!(patent.claims_structured && patent.claims_structured.length);

// 現在実行中のステップ番号（1=概要, 2=権利化ポイント, 3=請求項）
const step = !hasSummary ? 1 : !hasKeyPoints ? 2 : 3;
```

**注意:** `_parse_key_points(None)` は `[]` を返すため API レスポンスが空配列になる。`!![]` は `true` なので、`!!patent.key_points` では未取得を検知できない。必ず `length` チェックを使う（上記コード参照）。

**ステップインジケーター（`stepTag`）:**

```javascript
const stepTag = (label, n) => {
  if (n < step)   return `<span class="progress-step done">✓ ${label}</span>`;
  if (n === step) return `<span class="progress-step active">⟳ ${label}</span>`;
  return `<span class="progress-step pending">${label}</span>`;
};
```

```css
.progress-step        { display: inline-flex; align-items: center; padding: 2px 10px;
                        border-radius: 20px; font-size: 12px; gap: 4px; }
.progress-step.done   { background: #f0fdf4; color: #16a34a; }
.progress-step.active { background: #eff6ff; color: #2563eb; }
.progress-step.pending{ background: var(--c-bg-alt); color: var(--c-text-muted); }
```

**スケルトンカード（未完了ステップ用）:**

```html
<div class="card skeleton-card">
  <div class="skeleton-lines">
    <div class="skeleton-line"></div>
    <div class="skeleton-line short"></div>
    <div class="skeleton-line"></div>
  </div>
</div>
```

```css
.skeleton-card { opacity: 0.6; }
.skeleton-lines { display: flex; flex-direction: column; gap: 10px; padding: 8px 0; }
.skeleton-line  { height: 14px; background: linear-gradient(90deg,
                  var(--c-border) 25%, #e2e4e9 50%, var(--c-border) 75%);
                  background-size: 200% 100%; border-radius: 6px;
                  animation: shimmer 1.4s infinite; }
.skeleton-line.short { width: 60%; }
@keyframes shimmer { 0% { background-position: 200% 0; } 100% { background-position: -200% 0; } }
```

### ポーリングの部分更新

`analysis_status === "analyzing"` 中は `#detail` 全体を再レンダリングせず、`#analysis-section` のみ更新する。これにより他タブのスクロール位置が失われない。

```javascript
// startPolling の else branch（analyzing 中の更新）
const analysisEl = document.getElementById('analysis-section');
if (analysisEl) {
  analysisEl.innerHTML = renderAnalysisSection(patent);
  updateProgressUI();  // タイマー即時更新（ちらつき防止）
}
```

---

## AI 分析結果の表示ロジック

### `renderSummaryText(text)` — 発明の概要

`・label：content` 形式の箇条書きを 2 列テーブルに変換する。

- `・手段：（請求項1）...（請求項2）...` のように `（請求項N）` を含む場合:
  - value セル: 各請求項ごとにバッジ付きブロック（`summary-claim-item`）に分割
  - label セル: `<span class="summary-label-note">独立項のみ</span>` を追記

CSS クラス:
- `.summary-table` — 発明の概要全体テーブル
- `.summary-label-cell` — ラベル列（70px 固定幅、改行なし）
- `.summary-label-note` — 「独立項のみ」注記（グレー、10px）
- `.summary-claim-item` — 請求項バッジ + テキストの flex ブロック
- `.summary-claim-badge` — 「請求項N」バッジ

### `renderKeyPoints(kp)` — 権利化ポイント

`kp` が配列（旧形式）か文字列（新形式）かを判定して処理する。

新形式（`【セクション名】\n・項目` 構造）の処理フロー:
1. `_normalizeText(text)` — リテラル `\n` を実際の改行に変換、前後の `"` を除去
2. `parseKpSections(text)` — `【...】` 境界でセクション分割
3. 各セクション内の行を `_parseKpLine()` で `{type, label, content}` に分類
4. 全行がラベル付きなら **同じラベルを `Map` でグループ化**し `<table class="kp-labeled-table">` でレンダリング（ラベルは1行に1つ、複数内容は `.kp-content-item` で列挙）
5. 混在なら `<ul>` でレンダリング

**`_normalizeText(text)` の必要性:**
AI が JSON に出力する `\n` が、JSON パース後にリテラルの `\\n` として残ることがある。JS の `/\\n/g` 正規表現で実際の改行に置換する。

**ラベルグループ化（`renderKpSection` 内）:**

```javascript
const labelMap = new Map();
for (const l of parsed) {
  if (!labelMap.has(l.label)) { labelMap.set(l.label, []); labelOrder.push(l.label); }
  labelMap.get(l.label).push(l.content);
}
const rows = labelOrder.map(label => {
  const items = labelMap.get(label);
  const contentHtml = items.map(item => `<div class="kp-content-item">${escHtml(item)}</div>`).join("");
  return `<tr><td class="kp-label-cell">...</td><td class="kp-content-cell">${contentHtml}</td></tr>`;
}).join("");
```

**`.kp-content-item` の CSS:**

```css
.kp-content-item { padding: 2px 0 2px 16px; position: relative; line-height: 1.6; }
.kp-content-item::before {
  content: ''; position: absolute; left: 3px; top: 9px;
  width: 5px; height: 5px; background: var(--c-primary); border-radius: 50%;
}
```

### `renderClaimCard(c)` — 請求項構造

`patent.claims_structured` (JSON) から請求項カードを生成する。
各コンポーネントの `original`（原文）と `plain`（平易な説明）を並べて表示する。

**請求項番号・タイプバッジの実装:**

```javascript
<span class="claim-num">請求項${c.claim_number}</span>
<span class="claim-type-tag claim-type-ind">独立項</span>
<span class="claim-type-tag claim-type-dep">従属項<span class="claim-dep-ref">（→請求項N）</span></span>
```

```css
.claim-type-tag { display: inline-block; flex-shrink: 0; border-radius: 10px; text-align: center; }
.claim-type-ind { background: #f0f9ff; color: #0369a1; }
.claim-type-dep { background: var(--c-bg); color: var(--c-text-muted); border: 1px solid var(--c-border); }
.claim-dep-ref  { display: block; font-size: 11px; }
```

---

## 書誌情報カード（`renderBiblio`）

書誌情報カードには「発明の名称」行を表示しない（詳細画面ヘッダーにタイトルが既に表示されているため重複を避ける）。

J-PlatPat リンクは `renderBiblio` 内ではなく、詳細画面ヘッダーの `sourceBadge(source, url)` で表示する。
`patent.metadata.jplatpat_url` を URL として渡すと、バッジ自体がリンクになる。

```javascript
function sourceBadge(source, url) {
  const map = { jplatpat: ["badge-jplatpat", "J-PlatPat"], pdf: ["badge-pdf", "PDF"], word: ["badge-word", "Word"] };
  const [cls, label] = map[source] || ["badge-pending", source];
  if (url) {
    return `<a href="${escHtml(url)}" target="_blank" rel="noopener noreferrer"
              class="badge ${cls} detail-jplatpat-link">${label} ↗</a>`;
  }
  return `<span class="badge ${cls}">${label}</span>`;
}
```
