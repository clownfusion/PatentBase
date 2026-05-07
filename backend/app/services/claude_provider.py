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
        client = self._get_client()

        content: list = []

        # 図面画像（マルチモーダル）
        if input.images:
            for img_bytes in input.images:
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": "image/png",
                        "data": base64.standard_b64encode(img_bytes).decode(),
                    },
                })

        # テキスト（プロンプトキャッシュ対象）
        content.append({
            "type": "text",
            "text": input.text,
            "cache_control": {"type": "ephemeral"},  # プロンプトキャッシュ
        })

        messages = [{"role": "user", "content": content}]

        response = await client.messages.create(
            model=settings.anthropic_model,
            max_tokens=8096,
            system=input.system_prompt or "あなたは特許の専門家です。",
            messages=messages,
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
