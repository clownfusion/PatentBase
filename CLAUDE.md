# PatentBase — Claude Code 向けプロジェクト指示

## プロジェクト概要

特許業務（先行文献調査・任意特許確認・明細書作成資料）を段階的にツール化する Web アプリ。  
各担当者がローカル環境で独立して起動・利用する構成（認証不要）。

詳細な要件・フェーズ計画: [`docs/PatentBase効率化計画.md`](docs/PatentBase効率化計画.md)  
フロントエンド実装パターン詳細: [`docs/frontend-design.md`](docs/frontend-design.md)

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
│   ├── PatentBase効率化計画.md  # フェーズ別要件・設計方針
│   └── frontend-design.md       # フロントエンド実装パターン詳細
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
「エンジニア向けに特許を説明するアナリスト」として設定。`claude_provider.py` と `claude_code_provider.py` の `_DEFAULT_SYSTEM` を**必ず同一内容**に保つこと。

### AI 分析の非同期パターン（`analyze_router.py`）

AI 分析は最大数分かかるため、HTTP リクエストをブロックしないよう FastAPI の `BackgroundTasks` を使う。

**フロー:**
1. `POST /analyze/{id}` → DB の `analysis_status` を `"analyzing"` にして即座に返す
2. バックグラウンドで `_run_analysis_task()` が非同期に実行
3. フロントエンドは `GET /patents/{id}` を 2 秒ごとにポーリング
4. `analysis_status` が `"done"` または `"error"` になったらポーリング停止

**注意:** background task のテキスト構築は HTTP ハンドラ内で行う。`BackgroundTasks` 関数内では元の `db` セッションが無効になっているため、テキストを事前に渡す必要がある。

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

### Claude Code CLI のインストール

**重要**: Claude.ai Web アプリやデスクトップアプリとは別物。CLI は npm でインストールする。

```cmd
npm install -g @anthropic-ai/claude-code
```

---

## Windows 固有の注意点

### Playwright と asyncio

Windows の `ProactorEventLoop` は `add_reader()` を実装していないため、  
`async_playwright` を FastAPI のハンドラから直接呼ぶと `NotImplementedError` が発生する。

対策として `jplatpat_scraper.py` では `sync_playwright` を `ThreadPoolExecutor` 内で実行している。  
**この構造を変更しないこと。**

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

### J-PlatPat: 経過情報テーブルの抽出

経過情報ページには複数のテーブルが存在する。**最初のテーブルではなく、最も行数が多いテーブルを選択する**。  
また、デフォルト表示が「カテゴリ別表示」のため、抽出前に **「時系列表示」ラジオボタンをクリック**する。

```python
# _extract_progress_table() の方針
# 1. label:has-text('時系列表示') をクリック
# 2. page.locator("table").all() で全テーブルを取得
# 3. 行数が最多のテーブルを選択（best_row_count < 3 はフォールバック）
# 4. {"headers": [...], "rows": [[...], ...]} の JSON 文字列として返す
# 5. テーブル未発見・行ゼロ時は body_text[:8000] にフォールバック
```

`progress_info` のデータ形式:
- **新規取得（成功）**: `{"headers": [...], "rows": [[...], ...]}` の JSON 文字列
- **テーブル未発見 / 旧データ**: プレーンテキスト（最大 8000 文字）

フロントエンド（`app.js` の `renderBiblio`）は `JSON.parse` を try/catch し、  
失敗時は `<pre class="progress-text">` にフォールバックする（後方互換）。

### J-PlatPat: Angular Material ダイアログとオーバーレイ

J-PlatPat の **URL ボタン** (`a[id*='_url0']`) は Angular Material ダイアログを同一ページ上に表示する。  
クリック後にダイアログ内テキストから URL を抽出し、**必ず `Escape` キーで閉じること**。  
閉じないと `cdk-overlay-backdrop` が残存して後続の全クリックをブロックする。

```python
url_btn.first.click()
page.wait_for_timeout(1500)
# ダイアログ内テキストから URL を正規表現で抽出
page.keyboard.press("Escape")   # 必須
page.wait_for_timeout(800)
```

### J-PlatPat: OPD ファミリー情報取得

OPD ページ（`https://www.j-platpat.inpit.go.jp/h0200`）は Angular SPA のため、新タブ捕捉直後の URL が `/?uri=/h0200` になることがある。この場合 `mainte.html` にリダイレクトされる。

対策: `domcontentloaded` 後に URL を検査し、`?uri=` または `mainte` を含む場合は `/h0200` へ直接ナビゲートし直す。

**ファミリー一覧テーブルの tbody 問題:**  
Angular は `<tbody>` を行ごとに1つずつ生成するため、`querySelector('tbody')` では最初の1行しか取れない。  
必ず `querySelectorAll('tbody tr')` を使う。

**書類情報テーブルの後処理:**  
`EXCLUDE_COLS = {"PDFダウンロード", "書類出力"}` を除去し、装飾文字（`■▲▼` 等）をクリーニングする。

### J-PlatPat: デバッグログの設定

`jplatpat_scraper.py` はモジュールレベルで `StreamHandler` を追加し、`logger.propagate = False` を設定する。  
`logger.setLevel(logging.DEBUG)` だけではルートロガーが WARNING のままだと DEBUG ログが出力されない。

---

## FastAPI ルーティング注意点

### `_patent_to_dict()` に含めるフィールドの管理

`patents_router.py` の `_patent_to_dict()` が返す dict がそのまま API レスポンスになる。  
**DB に保存されていても、この関数に含めなければフロントエンドで参照できない。**  
新しいフィールドを DB モデルに追加した場合は、`_patent_to_dict()` への追記も忘れないこと。

### `key_points` の保存・取得パターン（二重エンコード問題）

AI が返す `key_points` は**文字列**になることがある。`json.dumps()` で DB に保存すると二重エンコード状態になるため、`_parse_key_points()` を経由して返す。

```python
def _parse_key_points(raw: str | None):
    if not raw:
        return []
    try:
        return json.loads(raw)   # list[str] または str を返す
    except (json.JSONDecodeError, TypeError):
        return raw               # パース失敗時は生テキストをそのまま返す
```

DB のデータ形式が2種類混在する:
- 旧形式: `["ポイント1", "ポイント2"]` → `json.loads` で `list[str]`
- 新形式: `"【技術分野】\n・..."` → `json.loads` で `str`

フロントエンドの `renderKeyPoints()` は `Array.isArray()` で両形式を判定して処理する。

### 静的パスは動的パスより前に定義する

`/{patent_id}` のような動的パスは同名の静的パスをすべて吸収してしまう。  
**必ず静的パス（`/bulk` 等）を動的パス（`/{patent_id}`）より前に定義すること。**

```python
@router.delete("/bulk")         # 静的パスを先に
def delete_patents_bulk(...): ...

@router.delete("/{patent_id}")  # 動的パスを後に
def delete_patent(...): ...
```

---

## フロントエンド設計

実装パターンの詳細（CSS クラス設計・各レンダリング関数の実装）は [`docs/frontend-design.md`](docs/frontend-design.md) を参照。

### サイドバー折りたたみ

左サイドバーは手動トグル + **compare モードのみ**自動折りたたみに対応している。

```javascript
// state オブジェクト内
sidebarAutoCollapsed: false   // compare モードで自動折りたたみしたかを追跡

// 主要関数
_applySidebarCollapsed(collapsed)  // #sidebar に .collapsed クラスを付与/除去
toggleSidebar()                    // 手動トグル（sidebarAutoCollapsed をクリア）
switchViewMode(mode)               // compare 時のみ自動折りたたみ、解除時に自動復元
```

### 詳細画面の4モード切り替え

`state.viewMode`（`"family"` | `"analysis"` | `"source"` | `"compare"`）で管理する。

| タブ名 | viewMode | 表示内容 |
|---|---|---|
| 書誌情報 | `family` | 書誌情報カード + ファミリー情報 |
| AI分析 | `analysis` | AI分析結果 + エクスポートボタン |
| 原文 | `source` | 請求の範囲・詳細な説明 |
| AI分析・原文 | `compare` | 左: AI分析、右: 原文（サイドバー自動折りたたみ） |

CSS は `data-view-mode` 属性で切り替える:
- `family`: `.compare-left/.compare-right { display: none }` → `.family-panel-wrapper` を表示
- `analysis`: `.compare-right { display: none }` → 左ペインのみ全幅
- `source`: `.compare-left { display: none }` + `.compare-right` は `applyPanelLayout()` で高さ設定
- `compare`: `display: flex` で左右並列。両パネルの高さを `applyPanelLayout()` で設定

### 原文タブパネルの主要制約

- **`.source-tabs` は `.source-pane-container`（スクロール容器）の外側に置く。** タブが常に表示される仕組みはこの DOM 構造による。`position: sticky` は使わない
- **`applyPanelLayout()` を必ず呼ぶ。** `switchViewMode`・`renderDetail`・`window.resize` の3か所から呼び出すこと。CSS の `max-height` だけでは flex 子要素の高さが確定しない
- **スクロール管理対象は `.source-pane-container`。** `switchSourceTab` のスクロール保存・復元は `.compare-right` ではなく `.source-pane-container` に対して行う

### AI 分析結果表示の主要制約

- **同じラベルを `Map` でグループ化する。** `renderKeyPoints` 内でラベルが重複しないよう `renderKpSection` が `Map` でグループ化してから表示する
- **請求項タイプバッジは `.badge` クラスを使わず `.claim-type-tag` を使う。** `.badge` の `display: inline-flex` + `white-space: nowrap` と競合し、`flex-direction: column` 内でテキスト幅計算が崩れるため

### 書誌情報カード（`renderBiblio`）

書誌情報カードには「発明の名称」行を表示しない（詳細画面ヘッダーにタイトルが既に表示されているため）。  
J-PlatPat リンクは `sourceBadge(source, url)` で詳細画面ヘッダーに表示する。

### 静的ファイルのキャッシュバスター

```html
<link rel="stylesheet" href="/static/style.css?v=16">
<script src="/static/app.js?v=28"></script>
```

**JS または CSS を変更したら、対応するバージョン番号をインクリメントすること。**

---

## Word インポート設計（`word_importer.py`）

### `【書類名】` セクション分割

Word 特許書類は `【書類名】セクション名` マーカーで章を区切る構造になっている。  
**段落単位ではなく全文に対して正規表現を適用**してセクションを分割する。  
（段落オブジェクト内に soft return `<w:br/>` で複数行が含まれることがあるため）

| `【書類名】` のセクション名 | 格納先フィールド |
|---|---|
| 要約書 | `abstract` |
| 特許請求の範囲 | `claims_text` |
| 明細書 | `description_text` |
| 特許願 | biblio 解析のソース |

マーカーが1つも見つからない場合は全文を `description_text` に格納する（`claims_text` ではない）。

### タイトル・出願人フォールバック

1. **タイトル**: `parse_biblio` が `【発明の名称】` を見つけられない場合、`description_text` 内も検索する
2. **出願人**: Word 書式では `【特許出願人】` を使う（J-PlatPat の `【出願人】` とは異なる）  
   `[^\n]+` で1行分のみキャプチャ（`re.DOTALL` と `.+` の組み合わせは残り全文を吸い込むので使わない）

---

## レポートエクスポート注意点

ダウンロード時の `Content-Disposition` ヘッダーに日本語を含む場合、HTTP ヘッダーの latin-1 制約により `UnicodeEncodeError` が発生する。`filename*=UTF-8''...` 形式（RFC 5987）でパーセントエンコードすること。

```python
def _content_disposition(patent: Patent, ext: str) -> str:
    num = (patent.patent_number or patent.id).replace("/", "-").replace(" ", "_")
    filename = f"patent_{num}.{ext}"
    encoded = urllib.parse.quote(filename.encode("utf-8"), safe="")
    return f"attachment; filename*=UTF-8''{encoded}"
```

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
