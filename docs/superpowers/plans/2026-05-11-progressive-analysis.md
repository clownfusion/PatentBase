# AI分析 段階表示 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI 分析結果を発明の概要 → 権利化ポイント → 請求項構造の順にセクション単位で完了次第表示し、体感待ち時間を短縮する。

**Architecture:** Claude API 呼び出しを 3 回に分割して順次実行し、各完了後に即座に DB へ保存・commit する。フロントエンドの既存ポーリング（2 秒ごと）を活用し、`#analysis-section` 要素のみを部分更新することでスクロール位置を維持しながら逐次描画する。

**Tech Stack:** FastAPI, SQLAlchemy + SQLite, Anthropic Python SDK (prompt caching 有効), Vanilla JS

---

## ファイル構成

| 操作 | パス | 変更内容 |
|------|------|---------|
| 新規 | `backend/app/prompts/analyze_summary.txt` | summary 専用プロンプト |
| 新規 | `backend/app/prompts/analyze_key_points.txt` | key_points 専用プロンプト |
| 新規 | `backend/app/prompts/analyze_claims.txt` | claims_structured + mermaid 専用プロンプト |
| 削除 | `backend/app/prompts/analyze_patent.txt` | 上記 3 ファイルに分割 |
| 変更 | `backend/app/services/ai_analyzer.py` | 3 関数に分割 |
| 変更 | `backend/app/api/analyze_router.py` | 順次呼び出し + 都度 commit |
| 変更 | `frontend/static/style.css` | skeleton アニメーション CSS |
| 変更 | `frontend/static/app.js` | 部分描画 + skeleton + 進捗ステップ更新 |

---

## Task 1: プロンプトファイルを 3 分割する

**Files:**
- 新規: `backend/app/prompts/analyze_summary.txt`
- 新規: `backend/app/prompts/analyze_key_points.txt`
- 新規: `backend/app/prompts/analyze_claims.txt`
- 削除: `backend/app/prompts/analyze_patent.txt`

- [ ] **Step 1: analyze_summary.txt を作成する**

`backend/app/prompts/analyze_summary.txt` の内容:

```
以下の特許文書（書誌情報・要約・請求項・詳細説明）を分析してください。

# 分析指示

発明の概要を分析し、必ず指定の JSON 形式のみで回答してください。JSON ブロック以外の説明文・前置きは不要です。

### summary
以下の5項目を箇条書きで記述してください。
各項目は核心を伝えることを優先し、複数文になることを許容します。

・技術分野：どの分野の発明か
・課題　　：何を解決するか
・手段　　：独立請求項ごとに1文以上。請求項番号を（請求項N）の形で明示し、
            「何の発明か（装置・方法・プログラム等）」と
            「他の請求項と区別できる核心的な技術的特徴」を記述すること
・効果　　：どのような効果が得られるか
・権利　　：権利範囲は広いか狭いか、注意すべき特徴

---

必ず以下の JSON 形式のみで回答してください（JSON ブロック以外の出力は禁止）:

```json
{
  "summary": "・技術分野：...\n・課題：...\n・手段：（請求項1）...\n・効果：...\n・権利：..."
}
```

---

【特許文書】
```

- [ ] **Step 2: analyze_key_points.txt を作成する**

`backend/app/prompts/analyze_key_points.txt` の内容:

```
以下の特許文書（書誌情報・要約・請求項・詳細説明）を分析してください。

# 分析指示

権利化ポイントを分析し、必ず指定の JSON 形式のみで回答してください。JSON ブロック以外の説明文・前置きは不要です。

### key_points
以下の5つのセクション見出しをそのまま使い、各セクションに箇条書きで記述してください。
各項目は核心を伝えることを優先し、箇条書きの数は必要な分だけ記載します。

【発明の核心的な技術構成】
・この特許固有の技術構成を具体的に記述

【権利範囲に含まれるもの・含まれないもの】
・含まれる：〜
・含まれない：〜

【自社技術と比較すべきポイント】
・抵触判断（自社技術が権利範囲に入るか）と
  出願可否判断（自社技術が差別化できるか）の両面から記述

【権利範囲の外側・出願余地】
・この特許の権利が及ばない領域と、自社出願の可能性がある方向性を記述

【明細書の構成】
・実施形態・図面・注目箇所など、この特許の明細書に
  具体的に何が書かれているかを記述（どの図が何を示すか等）

---

必ず以下の JSON 形式のみで回答してください（JSON ブロック以外の出力は禁止）:

```json
{
  "key_points": "【発明の核心的な技術構成】\n・...\n\n【権利範囲に含まれるもの・含まれないもの】\n・含まれる：...\n・含まれない：...\n\n【自社技術と比較すべきポイント】\n・...\n\n【権利範囲の外側・出願余地】\n・...\n\n【明細書の構成】\n・..."
}
```

---

【特許文書】
```

- [ ] **Step 3: analyze_claims.txt を作成する**

`backend/app/prompts/analyze_claims.txt` の内容:

```
以下の特許文書（書誌情報・要約・請求項・詳細説明）を分析してください。

# 分析指示

請求項の構造化と Mermaid 図を生成し、必ず指定の JSON 形式のみで回答してください。JSON ブロック以外の説明文・前置きは不要です。

### claims_structured
請求項を構造化してください。

- claim_type: 独立請求項は "independent"、従属請求項は "dependent"
- text: 請求項の全文。構成要素の区切り（「〜を有し、」「〜を備え、」等）で
        改行を入れて読みやすくすること
- summary: その請求項が保護する技術的特徴の核心を記述。
           理解しやすさを優先し、複数文になることを許容する
- components: 請求項を構成する主要要素のリスト
  - id: "A", "B", "C"... の識別子
  - original: 請求項原文から該当する構成要素のフレーズをそのまま抜粋
  - plain: originalを非専門家でもイメージしやすい平易な言葉で説明
- depends_on: 従属先の請求項番号（独立項は null）

### mermaid_diagram
請求項の構成要素と依存関係を Mermaid の flowchart TD 形式で表現してください。
- 主要な構成要素をノードとして表現（必要最小限に絞ること）
- 構成要素間の関係を矢印で表現
- 請求項間の従属関係も表現（点線等で区別可）
- ノードラベルは日本語で、簡潔に（10〜15文字以内）
- ノード数は必要最小限とし、最大10ノードを目安とする

---

必ず以下の JSON 形式のみで回答してください（JSON ブロック以外の出力は禁止）:

```json
{
  "claims_structured": [
    {
      "claim_number": 1,
      "claim_type": "independent",
      "text": "情報処理装置であって、\nデータを取得する取得部と、\n取得したデータを処理する処理部と、\nを備える情報処理装置。",
      "summary": "〜の核心的な特徴を記述。複数文可。",
      "components": [
        {
          "id": "A",
          "original": "データを取得する取得部",
          "plain": "外部からデータを受け取る入口"
        }
      ],
      "depends_on": null
    },
    {
      "claim_number": 2,
      "claim_type": "dependent",
      "text": "請求項1に記載の情報処理装置であって、\nさらに〜を備える情報処理装置。",
      "summary": "請求項1に〜を追加した限定。",
      "components": [],
      "depends_on": 1
    }
  ],
  "mermaid_diagram": "flowchart TD\n  A[構成A] --> B[構成B]"
}
```

---

【特許文書】
```

- [ ] **Step 4: analyze_patent.txt を削除する**

```bash
cd "c:\Users\MotomoraAkira\Desktop\DOC\30 Tool\PatentBase"
git rm backend/app/prompts/analyze_patent.txt
```

- [ ] **Step 5: 3 ファイルが存在し analyze_patent.txt が消えたことを確認する**

```bash
dir backend\app\prompts\
```

期待出力: `analyze_summary.txt`, `analyze_key_points.txt`, `analyze_claims.txt` の 3 ファイルのみ

- [ ] **Step 6: コミットする**

```bash
git add backend/app/prompts/analyze_summary.txt backend/app/prompts/analyze_key_points.txt backend/app/prompts/analyze_claims.txt
git commit -m "feat: AI分析プロンプトをセクション別に3分割"
```

---

## Task 2: ai_analyzer.py を 3 関数に分割する

**Files:**
- 変更: `backend/app/services/ai_analyzer.py`

- [ ] **Step 1: analyze_patent() を削除し 3 関数に置き換える**

`backend/app/services/ai_analyzer.py` の `analyze_patent()` 関数（72〜105行）を以下の 3 関数に置き換える:

```python
async def analyze_summary(text: str) -> dict:
    """Step 1: 発明の概要（summary）を生成する。"""
    provider = _get_provider()
    prompt = _load_prompt("analyze_summary")
    output = await provider.complete(
        prompt=prompt,
        input=AnalysisInput(text=text),
    )
    result = _parse_analysis_response(output.content)
    return {"summary": result.get("summary", "")}


async def analyze_key_points(text: str) -> dict:
    """Step 2: 権利化ポイント（key_points）を生成する。"""
    provider = _get_provider()
    prompt = _load_prompt("analyze_key_points")
    output = await provider.complete(
        prompt=prompt,
        input=AnalysisInput(text=text),
    )
    result = _parse_analysis_response(output.content)
    return {"key_points": result.get("key_points", [])}


async def analyze_claims(text: str) -> dict:
    """Step 3: 請求項構造と Mermaid 図を生成する。"""
    provider = _get_provider()
    prompt = _load_prompt("analyze_claims")
    output = await provider.complete(
        prompt=prompt,
        input=AnalysisInput(text=text),
    )
    result = _parse_analysis_response(output.content)
    return {
        "claims_structured": result.get("claims_structured", []),
        "mermaid_diagram": result.get("mermaid_diagram", ""),
    }
```

- [ ] **Step 2: インポートに変更がないことを確認する**

`ai_analyzer.py` の先頭 10 行を確認し、`analyze_patent` への外部参照が `analyze_router.py` のみであることを確認する（`grep -r "analyze_patent" backend/` で検索）。

```bash
grep -r "analyze_patent" backend/
```

期待出力: `analyze_router.py` 1 箇所のみ（次の Task で修正する）

- [ ] **Step 3: コミットする**

```bash
git add backend/app/services/ai_analyzer.py
git commit -m "feat: ai_analyzer を3関数(analyze_summary/key_points/claims)に分割"
```

---

## Task 3: analyze_router.py を順次呼び出しに変更する

**Files:**
- 変更: `backend/app/api/analyze_router.py`

- [ ] **Step 1: `_run_analysis_task()` を順次 3 ステップに書き換える**

`analyze_router.py` の `_run_analysis_task()` 関数（61〜87行）全体を以下に置き換える:

```python
async def _run_analysis_task(patent_id: str, full_text: str) -> None:
    """バックグラウンドで AI 分析を 3 ステップ順次実行し、各完了後に DB へ保存する。"""
    db = SessionLocal()
    try:
        # Step 1: 発明の概要
        result = await ai_analyzer.analyze_summary(full_text)
        patent = db.query(Patent).filter(Patent.id == patent_id).first()
        if not patent:
            return
        patent.summary = result.get("summary", "")
        db.commit()

        # Step 2: 権利化ポイント
        result = await ai_analyzer.analyze_key_points(full_text)
        patent = db.query(Patent).filter(Patent.id == patent_id).first()
        patent.key_points = json.dumps(
            result.get("key_points", []), ensure_ascii=False
        )
        db.commit()

        # Step 3: 請求項構造 + Mermaid 図
        result = await ai_analyzer.analyze_claims(full_text)
        patent = db.query(Patent).filter(Patent.id == patent_id).first()
        patent.claims_structured = result.get("claims_structured")
        patent.mermaid_diagram = result.get("mermaid_diagram", "")
        patent.analysis_status = "done"
        db.commit()

    except Exception:
        try:
            patent = db.query(Patent).filter(Patent.id == patent_id).first()
            if patent:
                patent.analysis_status = "error"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
```

- [ ] **Step 2: `analyze_router.py` の import を確認・修正する**

`from backend.app.services import ai_analyzer` の行が残っていることを確認する（インポート変更は不要）。

- [ ] **Step 3: サーバーを起動して構文エラーがないことを確認する**

```bash
uv run uvicorn backend.app.main:app --port 8765
```

起動ログに `Application startup complete.` が出れば OK（Ctrl+C で停止）。

- [ ] **Step 4: コミットする**

```bash
git add backend/app/api/analyze_router.py
git commit -m "feat: AI分析をsummary→key_points→claimsの3ステップ順次実行に変更"
```

---

## Task 4: skeleton CSS を追加する

**Files:**
- 変更: `frontend/static/style.css`

- [ ] **Step 1: `style.css` の末尾に skeleton スタイルを追加する**

`style.css` の末尾に以下を追記する:

```css
/* Skeleton loading */
@keyframes skeleton-shimmer {
  0%   { background-position: -400px 0; }
  100% { background-position: 400px 0; }
}

.skeleton-line {
  height: 14px;
  border-radius: 4px;
  background: linear-gradient(90deg, #e8eaed 25%, #f5f5f5 50%, #e8eaed 75%);
  background-size: 800px 100%;
  animation: skeleton-shimmer 1.4s infinite linear;
  margin-bottom: 10px;
}

.skeleton-lines {
  padding: 4px 0;
}

.skeleton-card .card-header h3 {
  color: var(--c-text-muted);
}

.analysis-error-partial {
  background: #fff8f0;
  border: 1px solid #f5a623;
  border-radius: 8px;
  padding: 10px 16px;
  font-size: 13px;
  color: #92400e;
  margin-bottom: 12px;
}
```

- [ ] **Step 2: コミットする**

```bash
git add frontend/static/style.css
git commit -m "feat: AI分析skeleton表示用のCSSを追加"
```

---

## Task 5: renderAnalysisSection を部分描画対応に書き換える

**Files:**
- 変更: `frontend/static/app.js`

- [ ] **Step 1: `renderAnalysisSection()` の `"analyzing"` ブランチを書き換える**

`app.js` の `renderAnalysisSection()` 関数内、`if (status === "analyzing")` ブロック（474〜498行）を以下に置き換える:

```javascript
  if (status === "analyzing") {
    const hasSummary  = !!patent.summary;
    const hasKeyPoints = !!patent.key_points;
    const hasClaims   = !!(patent.claims_structured && patent.claims_structured.length);

    // 現在実行中のステップを判定
    const step = !hasSummary ? 1 : !hasKeyPoints ? 2 : 3;

    const stepTag = (label, n) => {
      if (n < step)  return `<span class="progress-step done">✓ ${label}</span>`;
      if (n === step) return `<span class="progress-step active">⟳ ${label}</span>`;
      return `<span class="progress-step pending">${label}</span>`;
    };

    const skeletonLines = `<div class="skeleton-lines">
      <div class="skeleton-line"></div>
      <div class="skeleton-line" style="width:85%"></div>
      <div class="skeleton-line" style="width:92%"></div>
    </div>`;

    const summaryCard = hasSummary
      ? `<div class="card">
           <div class="card-header"><h3>📝 発明の概要</h3></div>
           <div class="card-body summary-card-body">${renderSummaryText(patent.summary)}</div>
         </div>`
      : `<div class="card skeleton-card">
           <div class="card-header"><h3>📝 発明の概要</h3></div>
           <div class="card-body">${skeletonLines}</div>
         </div>`;

    const kpCard = hasKeyPoints
      ? `<div class="card">
           <div class="card-header"><h3>🎯 権利化ポイント</h3></div>
           <div class="card-body kp-card-body">${renderKeyPoints(patent.key_points)}</div>
         </div>`
      : `<div class="card skeleton-card">
           <div class="card-header"><h3>🎯 権利化ポイント</h3></div>
           <div class="card-body">${skeletonLines}</div>
         </div>`;

    const claimsCard = hasClaims
      ? `<div class="card">
           <div class="card-header"><h3>📋 請求項の構造</h3></div>
           <div class="card-body">
             <div class="claims-list">${patent.claims_structured.map(c => renderClaimCard(c)).join("")}</div>
           </div>
         </div>`
      : `<div class="card skeleton-card">
           <div class="card-header"><h3>📋 請求項の構造</h3></div>
           <div class="card-body">${skeletonLines}</div>
         </div>`;

    return `<div class="analysis-analyzing">
      <div class="progress-card">
        <div class="progress-header">
          <div class="spinner" style="width:20px;height:20px;border-width:3px;flex-shrink:0"></div>
          <span class="progress-title">AI 分析中</span>
        </div>
        <div class="progress-steps">
          <span class="progress-step done">✓ テキスト送信</span>
          <span class="progress-step-arrow">→</span>
          ${stepTag("発明の概要", 1)}
          <span class="progress-step-arrow">→</span>
          ${stepTag("権利化ポイント", 2)}
          <span class="progress-step-arrow">→</span>
          ${stepTag("請求項構造・保存", 3)}
        </div>
        <div class="progress-bar-wrapper">
          <div id="analysis-progress-bar" class="progress-bar-fill" style="width:0%"></div>
        </div>
        <div class="progress-time-row">
          <span>経過時間：<strong id="analysis-elapsed-time">0:00</strong></span>
          <span id="analysis-remaining-time" class="progress-remaining">推定残り 3:00</span>
        </div>
        <p class="progress-note">分析はサーバー側で実行中です。他の特許を確認してから戻っても、経過時間・分析結果はそのまま表示されます。</p>
      </div>
      ${summaryCard}
      ${kpCard}
      ${claimsCard}
    </div>`;
  }
```

- [ ] **Step 2: `"error"` ブランチを部分結果表示対応に書き換える**

`if (status === "error")` ブロック（500〜506行）を以下に置き換える:

```javascript
  if (status === "error") {
    const hasSummary   = !!patent.summary;
    const hasKeyPoints = !!patent.key_points;
    const hasClaims    = !!(patent.claims_structured && patent.claims_structured.length);
    const hasAny = hasSummary || hasKeyPoints || hasClaims;

    const errorNotice = hasAny
      ? `<div class="analysis-error-partial">⚠️ 分析中にエラーが発生しました。取得済みの結果のみ表示しています。</div>`
      : `<div class="analysis-error">
           <div style="font-size:36px;margin-bottom:8px">⚠️</div>
           <h3>分析エラー</h3>
           <p>分析中にエラーが発生しました。API キーの設定を確認して再試行してください。</p>
         </div>`;

    return `${errorNotice}
      ${hasSummary ? `<div class="card">
        <div class="card-header"><h3>📝 発明の概要</h3></div>
        <div class="card-body summary-card-body">${renderSummaryText(patent.summary)}</div>
      </div>` : ""}
      ${hasKeyPoints ? `<div class="card">
        <div class="card-header"><h3>🎯 権利化ポイント</h3></div>
        <div class="card-body kp-card-body">${renderKeyPoints(patent.key_points)}</div>
      </div>` : ""}
      ${hasClaims ? `<div class="card">
        <div class="card-header"><h3>📋 請求項の構造</h3></div>
        <div class="card-body">
          <div class="claims-list">${patent.claims_structured.map(c => renderClaimCard(c)).join("")}</div>
        </div>
      </div>` : ""}`;
  }
```

- [ ] **Step 3: `updateProgressUI()` の `estimatedTotal` を 180 に変更する**

`updateProgressUI()` 内（878行付近）の:

```javascript
  const estimatedTotal = 120;
```

を以下に変更する:

```javascript
  const estimatedTotal = 180;
```

- [ ] **Step 4: コミットする（まだ JS バージョン番号は上げない）**

```bash
git add frontend/static/app.js
git commit -m "feat: AI分析中にskeletonと部分結果を表示するよう描画ロジックを更新"
```

---

## Task 6: ポーリングループを部分更新対応に変更する

**Files:**
- 変更: `frontend/static/app.js`

- [ ] **Step 1: `startPolling()` のポーリングタイマー部分を書き換える**

`app.js` の `startPolling()` 内、`state.pollingTimer = setInterval(...)` ブロック（849〜862行）を以下に置き換える:

```javascript
  // 2秒ごとに完了チェック（analyzing 中は analysis-section のみ部分更新）
  state.pollingTimer = setInterval(async () => {
    try {
      const patent = await api("GET", `/patents/${patentId}`);
      if (patent.analysis_status !== "analyzing") {
        stopPolling(true);
        renderDetail(patent);
        if (patent.analysis_status === "done") toast("AI 分析が完了しました", "success");
        if (patent.analysis_status === "error") toast("分析中にエラーが発生しました", "error");
        await loadPatents();
      } else {
        // スクロール位置を保持したまま分析セクションのみ更新
        const analysisEl = document.getElementById("analysis-section");
        if (analysisEl) {
          analysisEl.innerHTML = renderAnalysisSection(patent);
        }
      }
    } catch (e) {
      stopPolling(true);
    }
  }, 2000);
```

- [ ] **Step 2: JS と CSS のキャッシュバスター番号をインクリメントする**

`frontend/templates/` 内の HTML テンプレートを探し、`style.css` と `app.js` の `?v=` パラメータを +1 する。

```bash
grep -r "?v=" frontend/templates/
```

出力されたファイルで `style.css?v=X` と `app.js?v=Y` を探し、それぞれ X+1, Y+1 に変更する。

- [ ] **Step 3: コミットする**

```bash
git add frontend/static/app.js frontend/templates/
git commit -m "feat: ポーリング中にanalysis-sectionを部分更新してスクロール位置を保持"
```

---

## Task 7: 手動統合テスト

テスト環境: `uv run uvicorn backend.app.main:app --port 8765` でサーバー起動、ブラウザで `http://127.0.0.1:8765` を開く。

- [ ] **Step 1: 正常系テスト — 3 ステップが順番に現れることを確認する**

1. 任意の登録済み特許を開き「AI 分析実行」をクリックする
2. 「AI 分析中」カードのステップインジケーターが `✓テキスト送信 → ⟳発明の概要 → 権利化ポイント → 請求項構造・保存` と表示されることを確認する
3. 3 つの skeleton カードが表示されることを確認する
4. 約 30〜60 秒後に「📝 発明の概要」カードが skeleton からリアルタイムの内容に切り替わることを確認する
5. さらに 30〜60 秒後に「🎯 権利化ポイント」カードが切り替わることを確認する
6. 最後に「📋 請求項の構造」カードが切り替わり、ステータスが `done` になることを確認する
7. スクロール位置が各更新で維持されることを確認する

- [ ] **Step 2: 別特許に移動して戻る動作を確認する**

1. 分析開始後、「AI 分析中」の途中で別の特許を選択する
2. 元の特許に戻ったとき、取得済みのセクションが表示され続けていることを確認する
3. ポーリングが再開して残りのセクションが順次表示されることを確認する

- [ ] **Step 3: ブラウザの開発者ツールでネットワークタブを確認する**

1. DevTools の Network タブを開き、`/analyze/{id}` のリクエストが 1 回だけ行われることを確認する
2. その後 `/patents/{id}` が 2 秒ごとにポーリングされることを確認する

- [ ] **Step 4: 最終コミット**

```bash
git add -A
git status
git commit -m "feat: AI分析の段階表示を実装 (summary→key_points→claims順次表示)"
```
