"""特許分析サービス。AI プロバイダー経由で要約・請求項構造化・図解生成を行う。"""
import json
import re
from pathlib import Path
from .ai_provider import AIProvider, AnalysisInput
from .claude_provider import claude_provider
from .claude_code_provider import claude_code_provider

PROMPT_DIR = Path(__file__).parents[1] / "prompts"


def _load_prompt(name: str) -> str:
    path = PROMPT_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


def _get_provider() -> AIProvider:
    from backend.app.core.config import settings
    ptype = settings.ai_provider_type

    if ptype == "claude_code":
        if not claude_code_provider.is_available:
            raise RuntimeError(
                "claude CLI が見つかりません。Claude Code をインストールして PATH を通してください。"
            )
        return claude_code_provider

    if ptype == "api":
        if not claude_provider.is_available:
            raise RuntimeError(
                "ANTHROPIC_API_KEY が設定されていません。.env ファイルに設定してください。"
            )
        return claude_provider

    # auto: API キーがあれば API 優先、なければ Claude Code CLI
    if claude_provider.is_available:
        return claude_provider
    if claude_code_provider.is_available:
        return claude_code_provider
    raise RuntimeError(
        "AI 分析機能を利用するには ANTHROPIC_API_KEY または claude CLI が必要です。"
        ".env に ANTHROPIC_API_KEY を設定するか、Claude Code をインストールしてください。"
    )


def compose_patent_text(
    biblio_text: str = "",
    abstract_text: str = "",
    claims_text: str = "",
    description_text: str = "",
    max_desc_chars: int = 15000,
) -> str:
    """書誌・要約・請求項・詳細説明を結合して分析用テキストを生成する。

    詳細説明は長くなる可能性があるため max_desc_chars でトリミングする。
    """
    parts = []
    if biblio_text:
        parts.append(f"=== 書誌情報 ===\n{biblio_text.strip()}")
    if abstract_text:
        parts.append(f"=== 要約 ===\n{abstract_text.strip()}")
    if claims_text:
        parts.append(f"=== 請求の範囲 ===\n{claims_text.strip()}")
    if description_text:
        trimmed = description_text[:max_desc_chars]
        if len(description_text) > max_desc_chars:
            trimmed += "\n\n[...以下省略...]"
        parts.append(f"=== 詳細な説明 ===\n{trimmed.strip()}")
    return "\n\n".join(parts)


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


async def summarize_patent(text: str) -> str:
    """特許テキストから短い要約を生成する（1次スクリーニング用）。

    analyze_patent() より軽量で高速。主に Phase 2 の一括処理に使用。
    """
    provider = _get_provider()
    prompt = _load_prompt("summarize_patent")
    output = await provider.complete(
        prompt=prompt,
        input=AnalysisInput(text=text),
    )
    return output.content.strip()


def _parse_analysis_response(raw: str) -> dict:
    """LLM の応答から JSON ブロックを抽出してパースする。

    エラー時は raw テキストを含むフォールバック dict を返す。
    """
    # コードブロック内の JSON を抽出
    match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if match:
        json_str = match.group(1)
    else:
        # コードブロックなしで直接 JSON の場合
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            json_str = match.group(0)
        else:
            return {
                "summary": "（解析失敗）",
                "key_points": [],
                "claims_structured": [],
                "mermaid_diagram": "",
                "drawio_xml": "",
                "raw": raw,
            }

    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        # JSON 修復を試みる（末尾の切れ等）
        try:
            # よくある問題: 末尾が切れている場合に閉じ括弧を追加
            for closing in ["}", "}\n```", '"}']:
                try:
                    data = json.loads(json_str + closing)
                    break
                except Exception:
                    continue
            else:
                return {
                    "summary": "（JSON パースエラー）",
                    "key_points": [],
                    "claims_structured": [],
                    "mermaid_diagram": "",
                    "drawio_xml": "",
                    "raw": raw[:500],
                }
        except Exception:
            return {
                "summary": "（JSON パースエラー）",
                "key_points": [],
                "claims_structured": [],
                "mermaid_diagram": "",
                "drawio_xml": "",
                "raw": raw[:500],
            }

    # フィールドの存在確認とデフォルト値設定
    return {
        "summary": data.get("summary", ""),
        "key_points": data.get("key_points", []),
        "claims_structured": data.get("claims_structured", []),
        "mermaid_diagram": data.get("mermaid_diagram", ""),
        "drawio_xml": data.get("drawio_xml", ""),
    }
