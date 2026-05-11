# AI分析 段階表示（プログレッシブ表示）設計書

**作成日**: 2026-05-11  
**対象**: PatentBase — AI分析結果のセクション単位プログレッシブ表示

---

## 背景・課題

現在の AI 分析は、Claude への1回の API 呼び出しで全セクション（発明の概要・権利化ポイント・請求項構造・Mermaid 図）を一括生成し、完了後に全て表示する。複雑な特許では2〜3分以上待つことになる。

**目標**: 各セクションの生成が完了した時点で順次表示し、体感待ち時間を短縮する。

---

## 方針

- Claude API を **3回に分割して順番に呼び出す**（セクション単位で確定してから次へ進む）
- 各呼び出し完了後に即座に DB へ保存・commit する
- フロントエンドの既存ポーリング（2秒ごと）をそのまま活用し、フィールドが埋まった時点で逐次描画する
- SSE（Server-Sent Events）は使わない
- DB スキーマ変更なし、API 変更なし

### 分割順序

| ステップ | 対象セクション | 表示名 |
|---|---|---|
| Step 1 | `summary` | 発明の概要 |
| Step 2 | `key_points` | 権利化ポイント |
| Step 3 | `claims_structured` + `mermaid_diagram` | 請求項構造 + 図 |

### コストについて

既存の `cache_control: ephemeral` によりプロンプトキャッシュが有効。特許本文（入力トークンの大部分）は5分以内の連続呼び出しでキャッシュヒットするため、コスト増は **+20〜30% 程度**に抑えられる。

---

## バックエンド変更

### 1. プロンプトファイルの分割

既存の `backend/app/prompts/analyze_patent.txt` を廃止し、3ファイルに分割する。

| ファイル | 生成フィールド | 出力形式 |
|---|---|---|
| `analyze_summary.txt` | `summary` のみ | `{"summary": "..."}` |
| `analyze_key_points.txt` | `key_points` のみ | `{"key_points": "..."}` |
| `analyze_claims.txt` | `claims_structured` + `mermaid_diagram` | `{"claims_structured": [...], "mermaid_diagram": "..."}` |

各プロンプトには特許文書（書誌・要約・請求項・詳細説明）を渡す（共通）。

### 2. `ai_analyzer.py` の変更

3つの関数を追加する。既存の `analyze_patent()` は削除する。

```python
async def analyze_summary(text: str) -> dict:
    # {"summary": str}

async def analyze_key_points(text: str) -> dict:
    # {"key_points": str}

async def analyze_claims(text: str) -> dict:
    # {"claims_structured": list, "mermaid_diagram": str}
```

`_parse_analysis_response()` はそのまま流用する。

### 3. `analyze_router.py` の変更

`_run_analysis_task()` を3ステップの順次実行に変更する。

```python
async def _run_analysis_task(patent_id: str, full_text: str) -> None:
    db = SessionLocal()
    try:
        # Step 1: summary
        result = await ai_analyzer.analyze_summary(full_text)
        patent = db.query(Patent).filter(Patent.id == patent_id).first()
        patent.summary = result.get("summary", "")
        db.commit()

        # Step 2: key_points
        result = await ai_analyzer.analyze_key_points(full_text)
        patent = db.query(Patent).filter(Patent.id == patent_id).first()
        patent.key_points = json.dumps(result.get("key_points", []), ensure_ascii=False)
        db.commit()

        # Step 3: claims_structured + mermaid_diagram
        result = await ai_analyzer.analyze_claims(full_text)
        patent = db.query(Patent).filter(Patent.id == patent_id).first()
        patent.claims_structured = result.get("claims_structured")
        patent.mermaid_diagram = result.get("mermaid_diagram", "")
        patent.analysis_status = "done"
        db.commit()

    except Exception:
        # 失敗したステップ以前に保存済みのフィールドはそのまま残す
        patent = db.query(Patent).filter(Patent.id == patent_id).first()
        if patent:
            patent.analysis_status = "error"
            db.commit()
    finally:
        db.close()
```

**エラーハンドリング**: ステップ途中で例外が発生した場合、それまでに保存済みのフィールドはそのまま DB に残る。フロントエンドは取得済みセクションを表示しつつ、残りに「エラー」を表示する。

---

## フロントエンド変更（`app.js`）

### ポーリング時の描画ロジック変更

現在は `analysis_status === "done"` になってから全セクションを一括描画している。これを、`"analyzing"` 中も各フィールドの存在を確認して逐次描画するよう変更する。

**描画ルール:**

| フィールドの状態 | 描画内容 |
|---|---|
| 値が存在する | 通常描画（既存の renderXxx 関数を使用） |
| `null` かつ `status === "analyzing"` | ローディングスケルトン（グレーのプレースホルダー）を表示 |
| `null` かつ `status === "error"` | 「分析中にエラーが発生しました」を表示 |

**スケルトン表示の対象セクション:**

- 発明の概要（`summary`）
- 権利化ポイント（`key_points`）
- 請求項構造（`claims_structured`）

スケルトンは既存の CSS クラスを活用するか、シンプルなグレーブロックで実装する。

### 進捗インジケーターの更新

現在の「テキスト送信 → Claude 解析中 → 構造化・保存」の3ステップ表示を、4ステップに更新する。

```
✓ テキスト送信 → ◎ 発明の概要 → 権利化ポイント → 請求項構造・保存
```

各ステップが DB に保存された時点でチェックマーク表示に切り替わる。

---

## 変更ファイル一覧

| ファイル | 変更種別 | 内容 |
|---|---|---|
| `backend/app/prompts/analyze_summary.txt` | 新規 | summary 専用プロンプト |
| `backend/app/prompts/analyze_key_points.txt` | 新規 | key_points 専用プロンプト |
| `backend/app/prompts/analyze_claims.txt` | 新規 | claims_structured + mermaid 専用プロンプト |
| `backend/app/prompts/analyze_patent.txt` | 削除 | 上記3ファイルに分割 |
| `backend/app/services/ai_analyzer.py` | 変更 | 3関数に分割、analyze_patent() 削除 |
| `backend/app/api/analyze_router.py` | 変更 | 順次呼び出し＋都度 commit |
| `frontend/static/app.js` | 変更 | 部分描画 + スケルトン + 進捗インジケーター更新 |
| `frontend/static/style.css` | 変更 | スケルトンアニメーション CSS（必要な場合） |

---

## 変更しないもの

- DB スキーマ（`Patent` モデル）
- API エンドポイント（`POST /analyze/{id}`、`GET /patents/{id}`）
- ポーリング間隔（2秒）
- `claude_provider.py` / `claude_code_provider.py`
