# PatentBase — Claude Code 向けプロジェクト指示

## プロジェクト概要

特許業務（先行文献調査・任意特許確認・明細書作成資料）を段階的にツール化する Web アプリ。  
各担当者がローカル環境で独立して起動・利用する構成（認証不要）。

詳細な要件・フェーズ計画: [`docs/PatentBase効率化計画.md`](docs/PatentBase効率化計画.md)

---

## 起動方法

```bat
start.bat
```

または直接:

```powershell
uv run uvicorn backend.app.main:app --port 8765
```

ブラウザで `http://127.0.0.1:8765` を開く。

### 初回セットアップ（Playwright ブラウザ）

**重要**: Playwright のブラウザインストールは必ずユーザー自身のコマンドプロンプトで行うこと。  
Claude Code ツールから実行しても、サーバープロセスには反映されない（Windowsのユーザーコンテキスト分離のため）。

```cmd
uv run playwright install chromium
```

---

## アーキテクチャ

```
ブラウザ (HTML/JS)
    ↓ HTTP (port 8765)
FastAPI (backend/app/main.py)
    ├── /patents/*       特許管理エンドポイント
    ├── /analyze/*       AI 分析エンドポイント
    └── /reports/*       レポート生成エンドポイント
         ↓
    services/
    ├── jplatpat_scraper.py      J-PlatPat スクレイピング (Playwright sync API)
    ├── pdf_importer.py          PDF テキスト抽出 (pdfplumber / PyMuPDF)
    ├── word_importer.py         Word (.docx) テキスト抽出・セクション分割
    ├── ai_analyzer.py           AI 分析統合（プロバイダー切り替え対応）
    ├── claude_code_provider.py  Claude Code CLI プロバイダー
    └── document_generator.py   Word/Excel 出力 (python-docx, openpyxl)
         ↓
    SQLite (data/patents.db)
```

---

## ディレクトリ構造

```
PatentBase/
├── CLAUDE.md                    # このファイル
├── start.bat                    # サーバー起動バッチ
├── pyproject.toml               # 依存関係 (uv 管理)
├── backend/
│   └── app/
│       ├── main.py              # FastAPI アプリ・lifespan
│       ├── core/
│       │   ├── config.py        # 設定 (APIキー・DBパス)
│       │   └── database.py      # SQLite 接続
│       ├── models/
│       │   └── patent.py        # SQLAlchemy モデル
│       ├── api/
│       │   ├── patents_router.py
│       │   ├── analyze_router.py
│       │   └── reports_router.py
│       └── services/
│           ├── jplatpat_scraper.py
│           ├── pdf_importer.py
│           ├── word_importer.py         # Word セクション分割
│           ├── ai_analyzer.py
│           ├── claude_code_provider.py  # Claude Code CLI プロバイダー
│           └── document_generator.py
├── frontend/
│   ├── static/                  # CSS / JS
│   └── templates/               # Jinja2 HTML テンプレート
├── docs/
│   └── PatentBase効率化計画.md  # フェーズ別要件・設計方針
└── data/                        # SQLite DB（.gitignore 対象）
```

---

## AI プロバイダー設定

`backend/app/core/config.py` の `ai_provider_type` で AI 分析に使うプロバイダーを制御する。

| 値 | 動作 |
|---|---|
| `"auto"`（デフォルト） | `ANTHROPIC_API_KEY` があれば API、なければ Claude Code CLI にフォールバック |
| `"api"` | Anthropic API のみ使用（キーがなければエラー） |
| `"claude_code"` | Claude Code CLI のみ使用 |

### API 呼び出しパラメータ（`claude_provider.py`）

```python
response = await client.messages.create(
    model=settings.anthropic_model,   # claude-sonnet-4-latest
    max_tokens=16000,                 # 長い特許・多請求項に対応
    temperature=0,                    # 再現性確保（毎回同じ結果）
    system=system_prompt,
    messages=[{"role": "user", "content": content}],
    extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
)
```

**system prompt**（両プロバイダー共通）:  
「エンジニア向けに特許を説明するアナリスト」として設定。弁理士向けの硬い表現を平易な日本語に言い換えるよう指示している。`claude_provider.py` と `claude_code_provider.py` の `_DEFAULT_SYSTEM` を同一内容に保つこと。

### AI 分析の非同期パターン（`analyze_router.py`）

AI 分析は最大数分かかるため、HTTP リクエストをブロックしないよう FastAPI の `BackgroundTasks` を使う。

**フロー:**
1. `POST /analyze/{id}` → DB の `analysis_status` を `"analyzing"` にして即座に返す
2. バックグラウンドで `_run_analysis_task()` が非同期に実行
3. フロントエンドは `GET /patents/{id}` を 2 秒ごとにポーリング
4. `analysis_status` が `"done"` または `"error"` になったらポーリング停止

```python
@router.post("/{patent_id}")
async def analyze_patent(patent_id, background_tasks: BackgroundTasks, db=Depends(get_db)):
    # テキストを事前に構築（background task では DB セッションが無効なため）
    full_text = ai_analyzer.compose_patent_text(...)
    patent.analysis_status = "analyzing"
    db.commit()
    background_tasks.add_task(_run_analysis_task, patent_id, full_text)
    return {"id": patent_id, "analysis_status": "analyzing"}

async def _run_analysis_task(patent_id: str, full_text: str) -> None:
    db = SessionLocal()   # background task 専用の DB セッション
    try:
        result = await ai_analyzer.analyze_patent(text=full_text)
        # ... 結果を DB に保存 ...
        patent.analysis_status = "done"
        db.commit()
    except Exception:
        patent.analysis_status = "error"
        db.commit()
    finally:
        db.close()
```

**注意:** background task のテキスト構築は HTTP ハンドラ内で行う。`BackgroundTasks` 関数内では元の `db` セッションが無効になっているため、テキストを事前に渡す必要がある。

---

### Claude Code CLI プロバイダー（`claude_code_provider.py`）

`claude -p --output-format json` をサブプロセスとして起動し、プロンプトを stdin で渡して結果を取得する。

```python
proc = await asyncio.create_subprocess_exec(
    "claude", "-p", "--output-format", "json",
    stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE)
stdout, stderr = await asyncio.wait_for(proc.communicate(input=full_prompt.encode("utf-8")), timeout=300)
data = json.loads(stdout)
content = data.get("result", stdout.decode())
```

- `is_available`: `shutil.which("claude")` で CLI の存在を確認
- タイムアウト: 300 秒（長い特許テキストを考慮）
- CLI が見つからない場合: `RuntimeError` でわかりやすいエラーメッセージを返す

### Claude Code CLI のインストール

**重要**: Claude.ai Web アプリやデスクトップアプリとは別物。CLI は npm でインストールする。

```cmd
npm install -g @anthropic-ai/claude-code
```

インストール後、`claude --version` で動作確認すること。  
CLI が正常にインストールされていれば、`ANTHROPIC_API_KEY` なしで AI 分析が利用できる。

---

## Windows 固有の注意点

### Playwright と asyncio

Windows の `ProactorEventLoop` は `add_reader()` を実装していないため、  
`async_playwright` を FastAPI のハンドラから直接呼ぶと `NotImplementedError` が発生する。

対策として `jplatpat_scraper.py` では `sync_playwright` を `ThreadPoolExecutor` 内で実行している。  
この構造を変更しないこと。

```python
# fetch_patent → run_in_executor → _run_playwright_in_thread → sync_playwright
loop = asyncio.get_event_loop()
with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
    return await loop.run_in_executor(pool, _run_playwright_in_thread, query)
```

### Playwright ブラウザパス

`PLAYWRIGHT_BROWSERS_PATH` を `os.environ` で明示的にセットし、  
`chromium-1217/chrome-win64/chrome.exe` が存在する場合は `executable_path` で指定する。  
headless shell（`chromium_headless_shell-1217`）ではなく通常の chromium を使用している。

### J-PlatPat: 特許公報(B) 優先取得

検索結果に登録番号リンク (`p[id*='regNumNum'] a`) が存在する場合は、公開番号リンクではなく  
**登録番号リンクをクリック**して特許公報(B) を取得する。  
公開公報(A) を取得した場合、登録日・特許権者・特許番号が含まれない。

B 公報ページは自動的に `wsp1201` を呼ぶため、そのリクエストをインターセプトして  
B 公報用の `DOCU_KEY` を取得する（URL パラメータには含まれない）。

```python
captured_docu_key: list[str] = []
detail_page.on("request", _capture_docu_key)  # /wsp1201 の POST body から DOCU_KEY を取得
```

### J-PlatPat: 経過情報テーブルの抽出

経過情報ページ（`_progReferenceInfo0` リンクから開く新タブ）には複数のテーブルが存在する。  
ページ上部のステータス行（「登録XXXXXXX 本権利は抹消されていない」）も別テーブルに入っているため、  
**最初のテーブルではなく、ページ内で最も行数が多いテーブルを選択する**。

また、デフォルト表示が「カテゴリ別表示」のため、抽出前に **「時系列表示」ラジオボタンをクリック**してから取得する。

```python
# _extract_progress_table() の方針
# 1. label:has-text('時系列表示') をクリック
# 2. page.locator("table").all() で全テーブルを取得
# 3. 行数が最多のテーブルを選択（best_row_count < 3 はフォールバック）
# 4. {"headers": [...], "rows": [[...], ...]} の JSON 文字列として返す
# 5. テーブル未発見・行ゼロ時は body_text[:8000] にフォールバック
```

`progress_info` フィールドのデータ形式:
- **新規取得（成功）**: `{"headers": [...], "rows": [[...], ...]}` の JSON 文字列
- **テーブル未発見 / 旧データ**: プレーンテキスト（最大 8000 文字）

フロントエンド（`app.js` の `renderBiblio`）は `JSON.parse` を try/catch し、  
失敗時は `<pre class="progress-text">` にフォールバックする（後方互換）。

### J-PlatPat: Angular Material ダイアログとオーバーレイ

J-PlatPat の検索結果行にある **URL ボタン** (`a[id*='_url0']`) は新タブを開かず、  
Angular Material ダイアログ（`cdk-overlay-backdrop`）を同一ページ上に表示する。

`context.expect_page()` でタイムアウトしてもダイアログは閉じられず、  
`cdk-overlay-backdrop` が残存して後続の全クリックをブロックする。

対策: クリック後にダイアログ内テキストから URL を抽出し、**必ず `Escape` キーで閉じる**。  
次のステップへ進む前に残存オーバーレイの有無を確認すること。

```python
url_btn.first.click()
page.wait_for_timeout(1500)
# ダイアログ内テキストから URL を正規表現で抽出
page.keyboard.press("Escape")   # 必須: 閉じないと後続クリックが全てブロックされる
page.wait_for_timeout(800)
```

### J-PlatPat: OPD ファミリー情報取得

OPD（出願経過・ファミリー情報）は特許詳細ページ内の「OPD」ボタン（`button.opd-btn` 等）をクリックすると  
新しいタブで `https://www.j-platpat.inpit.go.jp/h0200` が開く。

**URL リダイレクト問題（重要）:**  
Playwright が新タブを捕捉した直後の URL が `/?uri=/h0200` になることがある（Angular SPA の初期リダイレクト）。  
この場合 J-PlatPat は `mainte.html` にリダイレクトしてしまう。

対策: `domcontentloaded` 後に URL を検査し、`?uri=` または `mainte` を含む場合は  
`/h0200` へ直接ナビゲートし直す。同一 Playwright コンテキスト内なのでセッションクッキーは引き継がれる。

```python
opd_page.wait_for_load_state("domcontentloaded", timeout=15000)
initial_url = opd_page.url
if "mainte" in initial_url or "?uri=" in initial_url:
    logger.info("OPD URL が不正なため /h0200 へ直接ナビゲートします")
    opd_page.goto("https://www.j-platpat.inpit.go.jp/h0200",
        wait_until="domcontentloaded", timeout=30000)
opd_page.wait_for_load_state("networkidle", timeout=30000)
opd_page.wait_for_selector("table", timeout=30000)  # Angular 非同期レンダリング待機
```

**ファミリー一覧テーブルの tbody 問題:**  
J-PlatPat の OPD ページは Angular で構築されており、`<tbody>` を **行ごとに1つずつ**生成する。  
`querySelector('tbody')` で取得できるのは最初の tbody のみ（= 1行分）。  
すべての行を取得するには `querySelectorAll('tbody tr')` を使う。

```javascript
// NG: 最初の tbody しか取れない
const rows = mainTable.querySelector('tbody').querySelectorAll('tr');

// OK: すべての tbody にまたがる tr を取得
const allBodyRows = Array.from(mainTable.querySelectorAll('tbody tr'));
```

**書類情報テーブルの後処理:**  
各ファミリー出願の書類情報テーブルには不要な列と装飾文字が含まれる。

```python
EXCLUDE_COLS = {"PDFダウンロード", "書類出力"}
clean_headers = [
    re.sub(r'["""「」]?[■▲▼]+["""「」]?', '', h).strip()
    for h in sec["headers"]
]
keep = [i for i, h in enumerate(clean_headers) if h not in EXCLUDE_COLS]
filtered_headers = [clean_headers[i] for i in keep]
filtered_rows = [[row[i] for i in keep if i < len(row)] for row in sec["rows"]]
```

### J-PlatPat: デバッグログの設定

`jplatpat_scraper.py` は FastAPI のルートロガー（デフォルト WARNING）に依存しないよう、  
モジュールレベルで明示的に `StreamHandler` を追加している。

```python
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setLevel(logging.DEBUG)
    logger.addHandler(_handler)
    logger.propagate = False
```

`logger.setLevel(logging.DEBUG)` だけではルートロガーが WARNING のままだと DEBUG ログが出力されない。  
`logger.propagate = False` で親ロガーへの伝播を切り、独立して動作させる。

---

## FastAPI ルーティング注意点

### `_patent_to_dict()` に含めるフィールドの管理

`patents_router.py` の `_patent_to_dict()` が返す dict がそのまま API レスポンスになる。  
DB に保存されていても、この関数に含めなければフロントエンドで参照できない。

現在レスポンスに含まれる主なフィールド:

| フィールド | 説明 |
|---|---|
| `abstract` | 要約 |
| `claims_text` | 請求の範囲（全文） |
| `description_text` | 詳細な説明（全文） |
| `claims_structured` | AI 分析で構造化した請求項（JSON） |
| `metadata` | 書誌情報・経過情報・図面等の補助情報 |

新しいフィールドを DB モデルに追加した場合は、`_patent_to_dict()` への追記も忘れないこと。

### `key_points` の保存・取得パターン（二重エンコード問題）

AI が返す `key_points` は**文字列**（`str`）になることがある（`【セクション】\n・項目` 形式）。  
これを `json.dumps()` で DB に保存すると `'"text\\n..."'` という二重エンコード状態になる。

`_patent_to_dict()` で `json.loads()` せずにそのまま返すと、フロントエンドが  
先頭に `"` が付いた生の JSON 文字列を受け取り、表示が壊れる。

**対策:** `_parse_key_points()` を経由して返す:

```python
def _parse_key_points(raw: str | None):
    if not raw:
        return []
    try:
        return json.loads(raw)   # list[str] または str を返す
    except (json.JSONDecodeError, TypeError):
        return raw               # パース失敗時は生テキストをそのまま返す

# _patent_to_dict() 内
"key_points": _parse_key_points(p.key_points),
```

**DB のデータ形式（2種類が混在する）:**
- 旧形式: `["ポイント1", "ポイント2"]` → `json.loads` で `list[str]`
- 新形式: `"【技術分野】\n・..." ` → `json.loads` で `str`

フロントエンドの `renderKeyPoints()` は両形式を `Array.isArray()` で判定して処理する。

### 静的パスは動的パスより前に定義する

`/{patent_id}` のような動的パスは、同名の静的パスをすべて吸収してしまう。  
例: `DELETE /patents/bulk` を `DELETE /patents/{patent_id}` より後に定義すると、  
`patent_id="bulk"` として処理され 404 になる。

**必ず静的パス（`/bulk` 等）を動的パス（`/{patent_id}`）より前に定義すること。**

```python
# ✅ 正しい順序
@router.delete("/bulk")         # 静的パスを先に
def delete_patents_bulk(...): ...

@router.delete("/{patent_id}")  # 動的パスを後に
def delete_patent(...): ...
```

---

## フロントエンド設計

### サイドバー折りたたみ

左サイドバーは手動トグル + **compare モードのみ**自動折りたたみに対応している。  
`family`（書誌情報）モードでは自動折りたたみしない。

```javascript
// state オブジェクト内
sidebarAutoCollapsed: false   // compare モードで自動折りたたみしたかを追跡

// 主要関数
_applySidebarCollapsed(collapsed)  // #sidebar に .collapsed クラスを付与/除去、ボタン表示を ‹/› で切り替え
toggleSidebar()                    // 手動トグル（sidebarAutoCollapsed をクリア）
switchViewMode(mode)               // compare 時のみ自動折りたたみ、compare 解除時に自動復元
```

- **compare モードのみ**遷移時: サイドバーが開いていれば自動で折りたたみ、`sidebarAutoCollapsed = true` を記録
- compare モード解除時: `sidebarAutoCollapsed` が true なら自動で展開してフラグをクリア
- 手動でトグルした場合は `sidebarAutoCollapsed` をクリアし、以降の自動復元を抑制

CSS: `#sidebar { transition: width .2s ease; }` / `#sidebar.collapsed { width: 0; border-right-width: 0; }`

### detail-header のスティッキー固定

詳細画面のタブ切り替えボタン行（`.detail-header`）はスクロールしても常に画面上部に表示されるよう  
`position: sticky` を設定している。

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

### 詳細画面の4モード切り替え

特許詳細画面には「書誌情報 / AI分析 / 原文 / AI分析・原文」の4モードがある。  
`state.viewMode`（`"family"` | `"analysis"` | `"source"` | `"compare"`）で管理する。

```
[ 書誌情報 | AI分析 | 原文 | AI分析・原文 ]  ← detail-header 内のトグルボタン

<div class="detail-content" data-view-mode="${state.viewMode}">
  <div class="compare-left">          ← AI分析（family/source モードで非表示）
  <div class="compare-right">         ← 請求の範囲・詳細な説明タブ（family/analysis モードで非表示）
  <div class="family-panel-wrapper">  ← 書誌情報 + ファミリー情報（family モードのみ表示）
```

CSS は `data-view-mode` 属性で4レイアウトを切り替える:
- `family`: `.compare-left/.compare-right { display: none }` → `.family-panel-wrapper` を表示
- `analysis`: `.compare-right { display: none }` → 左ペインのみ全幅
- `source`: `.compare-left { display: none }` + `.compare-right` に `overflow-y: auto; max-height`
- `compare`: `display: flex` で左右並列。`.compare-right` は `position: sticky`

#### タブと表示内容の対応

| タブ名 | viewMode | 表示内容 |
|---|---|---|
| 書誌情報 | `family` | 書誌情報カード + ファミリー情報 |
| AI分析 | `analysis` | AI分析結果 + エクスポートボタン |
| 原文 | `source` | 請求の範囲・詳細な説明 |
| AI分析・原文 | `compare` | 左: AI分析、右: 原文（サイドバー自動折りたたみ） |

### ファミリー情報パネル（`renderFamilyPanel`）

`family` モード（書誌情報タブ）では `family-panel-wrapper` に書誌情報カードとファミリー情報を表示する。

**アコーディオン構成:**  
各ファミリー出願（例: JP・US・EP）ごとに折りたたみ可能なセクションを生成する。  
ヘッダークリックで個別に展開/折りたたみ、全展開/全折りたたみの一括ボタンも提供する。

```javascript
// app.js の主要関数
renderFamilyPanel(patent)              // ファミリー情報全体の HTML を生成
toggleFamilyDocSection(labelEl)        // 個別セクションの展開/折りたたみ
toggleAllFamilyDocSections(btn, expand) // 全セクション一括操作
```

**提出日列の折り返し防止:**  
書類情報テーブルの「提出日」列は `white-space: nowrap` で1行に収める。  
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

### 原文タブパネル（`renderSourcePanel`）

`compare-right` 内に `source-panel` として配置する。

```javascript
// app.js の主要関数
renderSourcePanel(patent)   // 請求の範囲・詳細な説明のタブ HTML を生成
switchViewMode(mode)        // data-view-mode 属性の切り替え + detail-compare-mode クラス
switchSourceTab(btn)        // タブ切り替え + スクロール位置の保存・復元
```

**スクロール位置の保存・復元:**  
`sourceScroll = { claims: 0, desc: 0 }` でタブごとのスクロール位置を保持する。  
タブ切り替え時に現在の `scrollTop` を保存し、切り替え先の `scrollTop` を復元する。  
特許をサイドバーから切り替えたとき（`renderDetail` 呼び出し時）に両値を 0 にリセットする。

```javascript
// switchSourceTab の処理順
// 1. 現タブの scrollTop を sourceScroll[currentMode] に保存
// 2. 新タブの DOM を active に切り替え
// 3. compare-right の scrollTop を sourceScroll[newMode] に復元
```

### CSS: `position: sticky` と `overflow` の制約

`position: sticky` は、親要素のいずれかに `overflow: hidden` または `overflow: auto/scroll` が  
設定されていると、そのコンテナの外側では機能しない（スクロール不能になる）。

**`.source-panel` では `overflow: hidden` を使用しない。**  
border-radius の角丸クリップ目的で `overflow: hidden` を付けると `.source-tabs` の sticky が無効になる。  
代わりに `.source-tabs` 自体に `border-radius: var(--radius-lg) var(--radius-lg) 0 0` を付与する。

```css
/* NG: overflow: hidden が sticky を破壊する */
.source-panel { border-radius: 12px; overflow: hidden; }

/* OK: タブ自体に角丸を付ける */
.source-panel { border-radius: 12px; }  /* overflow 指定なし */
.source-tabs  { border-radius: 12px 12px 0 0; position: sticky; top: 0; }
```

### AI 分析進捗・経過時間の管理（ポーリング）

分析中は `GET /patents/{id}` を 2 秒ごとにポーリングし、経過時間を 1 秒ごとに更新する。  
別の特許タブに移動してから戻っても経過時間がリセットされないよう設計している。

```javascript
// state オブジェクト内の関連フィールド
pollingPatentId: null,        // ポーリング中の特許ID（別タブに移動しても保持）
analysisStartTime: null,      // タイマー開始時刻（別タブに移動しても保持）
pollingTimer: null,           // setInterval ID（API ポーリング用）
progressTimer: null,          // setInterval ID（経過時間表示更新用）
```

**`startPolling(patentId)`:**
```javascript
function startPolling(patentId) {
  const resuming = state.pollingPatentId === patentId && state.analysisStartTime !== null;
  stopPolling();  // タイマーのみクリア（state は保持）
  state.pollingPatentId = patentId;
  if (!resuming) state.analysisStartTime = Date.now();  // 同じ特許なら時刻を引き継ぐ
  updateProgressUI();  // 即時呼び出し（0:00 フラッシュ防止）
  state.progressTimer = setInterval(() => updateProgressUI(), 1000);
  state.pollingTimer = setInterval(async () => { /* GET /patents/... */ }, 2000);
}
```

**`stopPolling(clearState = false)`:**  
- `clearState=false`（デフォルト）: タイマーのみ停止、`pollingPatentId`/`analysisStartTime` は保持
- `clearState=true`: 分析完了/エラー時に state も完全にクリア

**新規分析開始時:** `runAnalysis()` が `clearState=true` 相当のリセットを行ってから POST。

### AI 分析結果の表示ロジック

#### `renderSummaryText(text)` — 発明の概要

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

#### `renderKeyPoints(kp)` — 権利化ポイント

`kp` が配列（旧形式）か文字列（新形式）かを判定して処理する。

新形式（`【セクション名】\n・項目` 構造）の処理フロー:
1. `_normalizeText(text)` — リテラル `\n` を実際の改行に変換、前後の `"` を除去
2. `parseKpSections(text)` — `【...】` 境界でセクション分割
3. 各セクション内の行を `_parseKpLine()` で `{type, label, content}` に分類
4. 全行がラベル付きなら `<table class="kp-labeled-table">` でレンダリング（列幅自動揃え）
5. 混在なら `<ul>` でレンダリング

**`_normalizeText(text)` の必要性:**  
AI が JSON に出力する `\n` が、JSON パース後に実際の改行（`\n`）ではなく  
リテラルの `\\n`（バックスラッシュ + n）として残ることがある。  
JS の `/\\n/g` 正規表現で実際の改行に置換する。

#### `renderClaimCard(patent)` — 請求項構造

`patent.claims_structured` (JSON) から請求項カードを生成する。  
各コンポーネントの `original`（原文）と `plain`（平易な説明）を並べて表示する。

### 書誌情報カード（`renderBiblio`）

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

### 静的ファイルのキャッシュバスター

`index.html` で JS・CSS をバージョン付きクエリパラメータで読み込んでいる。

```html
<link rel="stylesheet" href="/static/style.css?v=10">
<script src="/static/app.js?v=22"></script>
```

**JS または CSS を変更したら、対応するバージョン番号をインクリメントすること。**  
変更しないとブラウザキャッシュにより古いファイルが使われ続ける。

---

## Word インポート設計（`word_importer.py`）

### `【書類名】` セクション分割

Word 特許書類は `【書類名】セクション名` マーカーで章を区切る構造になっている。  
段落単位ではなく**全文に対して正規表現を適用**してセクションを分割する。  
（段落オブジェクト内に soft return `<w:br/>` で複数行が含まれることがあるため）

```python
_SECTION_SPLIT_RE = re.compile(r"【書類名】([^\n【]+)", re.MULTILINE)

def _split_sections(full_text: str) -> dict[str, str]:
    matches = list(_SECTION_SPLIT_RE.finditer(full_text))
    # 各セクションの内容は次の【書類名】マーカーの直前まで
    sections[key] = full_text[content_start:content_end].strip()
```

### セクション → フィールドのマッピング

| `【書類名】` のセクション名 | 格納先フィールド |
|---|---|
| 要約書 | `abstract` |
| 特許請求の範囲 | `claims_text` |
| 明細書 | `description_text` |
| 特許願 | biblio 解析のソース |

マーカーが1つも見つからない場合は全文を `description_text` に格納する（`claims_text` ではない）。

### タイトル・出願人フォールバック

1. **タイトル**: `parse_biblio` が `【発明の名称】` を見つけられなかった場合、`description_text` 内を検索する
   ```python
   m = re.search(r"【発明の名称】\s*(.+)", description_text)
   ```

2. **出願人**: Word 書式では `【特許出願人】` を使う（J-PlatPat の `【出願人】` とは異なる）
   ```python
   m = re.search(r"【特許出願人】.*?【氏名又は名称】\s*([^\n]+)", source, re.DOTALL)
   ```
   `[^\n]+` で1行分のみキャプチャ（`re.DOTALL` と `.+` の組み合わせは残り全文を吸い込むので使わない）。

---

## レポートエクスポート注意点

### RFC 5987 ファイル名エンコーディング

ダウンロード時の `Content-Disposition` ヘッダーに日本語を含む場合、  
HTTP ヘッダーの latin-1 制約により `UnicodeEncodeError` が発生する。

`filename*=UTF-8''...` 形式（RFC 5987）でパーセントエンコードすること。

```python
def _content_disposition(patent: Patent, ext: str) -> str:
    num = (patent.patent_number or patent.id).replace("/", "-").replace(" ", "_")
    filename = f"patent_{num}.{ext}"
    encoded = urllib.parse.quote(filename.encode("utf-8"), safe="")
    return f"attachment; filename*=UTF-8''{encoded}"
```

`filename=` だけでなく必ず `filename*=UTF-8''` 形式を使うこと。

---

## 実装状況

| フェーズ | 内容 | 状態 |
|---|---|---|
| Phase 1 | 基盤構築 + 任意特許確認 | **完了** |
| Phase 2 | 先行文献調査ワークフロー | 未着手 |
| Phase 3 | 出願前調査 + React UI | 未着手 |
| Phase 4 | 明細書作成資料自動生成 | 未着手 |
| Phase 5 | 中間処理支援 | 未着手 |

Phase 2 以降の要件詳細は `docs/PatentBase効率化計画.md` を参照。

---

## Skills 候補

PatentBase の操作は現在 Web UI 経由が主だが、以下の2つは CLI から実行したいユースケースが出てきたタイミングで Skills 化すると効果的。

| Skill 名 | 概要 | 主な用途 |
|---|---|---|
| `/analyze-patent` | 指定特許の AI 分析を実行し、完了まで待って結果を表示 | ブラウザを開かず CLI から分析を確認したいとき |
| `/register-patent` | 特許番号を受け取り `POST /patents/from-number` で登録し書誌情報を確認 | 複数特許をまとめて CLI から登録したいとき |

現時点では Web UI で十分なため未実装。需要が出てから作成すること。

---

## 開発規約

- **パッケージ管理**: `uv` を使用（`pip` は使わない）
- **依存追加**: `uv add <package>`
- **実行**: `uv run <command>`
- **AI モデル**: `claude-sonnet-4-latest`（`backend/app/core/config.py` で管理）
- **DBファイル・キャッシュ**: `data/` は `.gitignore` 対象。コミットしない
- **仮想環境**: `.venv/` も `.gitignore` 対象。コミットしない
- **J-PlatPat**: 入力値を解析せずそのまま簡易検索に渡す（`特許第5305285号` 等どんな形式でも動作）
