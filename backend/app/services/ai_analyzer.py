"""特許分析サービス。AI プロバイダー経由で要約・請求項構造化・図解生成を行う。"""
import json
from pathlib import Path
from .ai_provider import AIProvider, AnalysisInput
from .claude_provider import claude_provider

PROMPT_DIR = Path(__file__).parents[1] / "prompts"


def _load_prompt(name: str) -> str:
    path = PROMPT_DIR / f"{name}.txt"
    return path.read_text(encoding="utf-8")


def _get_provider() -> AIProvider:
    if not claude_provider.is_available:
        raise RuntimeError(
            "AI 分析機能を利用するには Claude API キーが必要です。"
            ".env ファイルに ANTHROPIC_API_KEY を設定してください。"
        )
    return claude_provider


async def analyze_patent(
    text: str,
    images: list[bytes] | None = None,
) -> dict:
    """特許テキスト（＋図面）から要約・請求項構造・図解を生成して返す。

    Returns:
        {
          "summary": str,
          "key_points": list[str],
          "claims_structured": list[dict],
          "mermaid_diagram": str,
          "drawio_xml": str,
        }
    """
    provider = _get_provider()
    prompt = _load_prompt("analyze_patent")

    output = await provider.complete(
        prompt=prompt,
        input=AnalysisInput(text=text, images=images),
    )

    return _parse_analysis_response(output.content)


async def summarize_patent(text: str) -> str:
    """特許テキストから短い要約を生成する（1次スクリーニング用）。"""
    provider = _get_provider()
    prompt = _load_prompt("summarize_patent")
    output = await provider.complete(
        prompt=prompt,
        input=AnalysisInput(text=text),
    )
    return output.content.strip()


def _parse_analysis_response(raw: str) -> dict:
    """LLM の応答から JSON ブロックを抽出してパースする。"""
    import re
    match = re.search(r"```json\s*(.*?)\s*```", raw, re.DOTALL)
    if match:
        return json.loads(match.group(1))
    # JSON ブロックがない場合は全体をそのまま返す（フォールバック）
    return {"raw": raw}
