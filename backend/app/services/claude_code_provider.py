"""Claude Code CLI を使った AI プロバイダー実装（ANTHROPIC_API_KEY 不要）。

`claude -p --output-format json` をサブプロセスで呼び出す。
画像はサポートしない（テキスト専用）。
"""
import asyncio
import json
import shutil
from .ai_provider import AIProvider, AnalysisInput, AnalysisOutput

_DEFAULT_SYSTEM = (
    "あなたは特許文書をエンジニア向けに説明するアナリストです。"
    "読み手は技術者ですが特許の専門用語には不慣れです。"
    "技術的な正確さと権利範囲の把握に必要な情報は保ちつつ、"
    "明細書特有の硬い表現（「〜を特徴とする」「〜に係る」等）は"
    "平易な日本語に言い換えてください。"
)

_TIMEOUT_SECONDS = 300  # 5分


class ClaudeCodeProvider(AIProvider):
    @property
    def is_available(self) -> bool:
        return shutil.which("claude") is not None

    async def complete(self, prompt: str, input: AnalysisInput) -> AnalysisOutput:
        """claude CLI に stdin でプロンプトを渡して応答を返す。

        images は無視される（テキスト専用）。
        """
        system = input.system_prompt or _DEFAULT_SYSTEM
        full_prompt = f"{system}\n\n{prompt}\n\n{input.text}"

        proc = await asyncio.create_subprocess_exec(
            "claude", "-p", "--output-format", "json",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                proc.communicate(input=full_prompt.encode("utf-8")),
                timeout=_TIMEOUT_SECONDS,
            )
        except asyncio.TimeoutError:
            proc.kill()
            raise RuntimeError(
                f"Claude Code CLI がタイムアウトしました（{_TIMEOUT_SECONDS}秒）。"
            )

        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace")[:500]
            raise RuntimeError(
                f"Claude Code CLI がエラーを返しました (exit {proc.returncode}): {err}"
            )

        raw = stdout.decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
            content = data.get("result", raw)
        except json.JSONDecodeError:
            content = raw

        return AnalysisOutput(
            content=content,
            model="claude-code-cli",
            input_tokens=0,
            output_tokens=0,
        )


claude_code_provider = ClaudeCodeProvider()
