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
    ├── jplatpat_scraper.py   J-PlatPat スクレイピング (Playwright sync API)
    ├── pdf_importer.py       PDF テキスト抽出 (pdfplumber / PyMuPDF)
    ├── ai_analyzer.py        Claude API 統合 (claude-sonnet-4-6)
    └── document_generator.py Word/Excel 出力 (python-docx, openpyxl)
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
│           ├── ai_analyzer.py
│           └── document_generator.py
├── frontend/
│   ├── static/                  # CSS / JS
│   └── templates/               # Jinja2 HTML テンプレート
├── docs/
│   └── PatentBase効率化計画.md  # フェーズ別要件・設計方針
└── data/                        # SQLite DB（.gitignore 対象）
```

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

---

## FastAPI ルーティング注意点

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

## 開発規約

- **パッケージ管理**: `uv` を使用（`pip` は使わない）
- **依存追加**: `uv add <package>`
- **実行**: `uv run <command>`
- **AI モデル**: `claude-sonnet-4-6`（`backend/app/core/config.py` で管理）
- **DBファイル・キャッシュ**: `data/` は `.gitignore` 対象。コミットしない
- **仮想環境**: `.venv/` も `.gitignore` 対象。コミットしない
- **J-PlatPat**: 入力値を解析せずそのまま簡易検索に渡す（`特許第5305285号` 等どんな形式でも動作）
