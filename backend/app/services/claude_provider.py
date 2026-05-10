"""Claude API を使った AI プロバイダー実装。"""
import anthropic
import base64
from .ai_provider import AIProvider, AnalysisInput, AnalysisOutput
from backend.app.core.config import settings


class ClaudeProvider(AIProvider):
    def __init__(self) -> None:
        self._client: anthropic.AsyncAnthropic | None = None

    @property
    def is_available(self) -> bool:
        return bool(settings.anthropic_api_key)

    def _get_client(self) -> anthropic.AsyncAnthropic:
        if self._client is None:
            if not self.is_available:
                raise RuntimeError(
                    "Claude API キーが設定されていません。.env ファイルに "
                    "ANTHROPIC_API_KEY を設定してください。"
                )
            self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        return self._client

    async def complete(self, prompt: str, input: AnalysisInput) -> AnalysisOutput:
        """Claude API を呼び出して分析結果を返す。

        メッセージ構造:
        - system: エキスパートペルソナ
        - user content[0..n]: 図面画像 (マルチモーダル、任意)
        - user content[-2]: 指示プロンプト (prompt テンプレート) ← キャッシュ対象
        - user content[-1]: 特許本文 (input.text) ← キャッシュ対象 (長文)
        """
        client = self._get_client()
        content: list = []

        # 図面画像（マルチモーダル、オプション）
        if input.images:
            for img_bytes in input.images[:10]:  # 最大10枚
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.standard_b64encode(img_bytes).decode(),
                    },
                })

        # 指示プロンプト（静的部分 → キャッシュ対象）
        if prompt:
            content.append({
                "type": "text",
                "text": prompt,
                "cache_control": {"type": "ephemeral"},
            })

        # 特許本文（動的部分、長文 → キャッシュ対象）
        content.append({
            "type": "text",
            "text": input.text,
            "cache_control": {"type": "ephemeral"},
        })

        system_prompt = (
            input.system_prompt
            or "あなたは特許文書をエンジニア向けに説明するアナリストです。"
               "読み手は技術者ですが特許の専門用語には不慣れです。"
               "技術的な正確さと権利範囲の把握に必要な情報は保ちつつ、"
               "明細書特有の硬い表現（「〜を特徴とする」「〜に係る」等）は"
               "平易な日本語に言い換えてください。"
        )

        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=16000,
            temperature=0,
            system=system_prompt,
            messages=[{"role": "user", "content": content}],
            extra_headers={"anthropic-beta": "prompt-caching-2024-07-31"},
        )

        return AnalysisOutput(
            content=response.content[0].text,
            model=response.model,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )


# シングルトンインスタンス
claude_provider = ClaudeProvider()
