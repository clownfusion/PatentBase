"""Claude Code CLI を使った AI プロバイダー実装（ANTHROPIC_API_KEY 不要）。

`claude -p --output-format json` をサブプロセスで呼び出す。
画像はサポートしない（テキスト専用）。
"""
import asyncio
import json
import shutil
from .ai_provider import AIProvider, AnalysisInput, AnalysisOutput

_DEFAULT_SYSTEM = (
    "あなたは特許の専門家（弁理士レベルの知識を持つ分析者）です。"
    "正確で実務的な日本語で回答してください。"
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
