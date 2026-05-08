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
    return await loop.run_in_executor(pool, _run_playwright_in_thread, normalized)
```

### Playwright ブラウザパス

`PLAYWRIGHT_BROWSERS_PATH` を `os.environ` で明示的にセットし、  
`chromium-1217/chrome-win64/chrome.exe` が存在する場合は `executable_path` で指定する。  
headless shell（`chromium_headless_shell-1217`）ではなく通常の chromium を使用している。

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
