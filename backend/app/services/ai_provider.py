"""AI プロバイダー抽象化レイヤー。
将来 OpenAI 等への切り替えは AIProvider を実装した別クラスを用意して
ai_analyzer.py の依存先を差し替えるだけで対応できる。
"""
from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AnalysisInput:
    text: str
    images: list[bytes] | None = None   # 図面画像バイト列（マルチモーダル用）
    system_prompt: str | None = None


@dataclass
class AnalysisOutput:
    content: str
    model: str
    input_tokens: int
    output_tokens: int


class AIProvider(ABC):
    @abstractmethod
    async def complete(self, prompt: str, input: AnalysisInput) -> AnalysisOutput:
        """プロンプトと入力を受け取り、LLM の応答を返す。"""
        ...

    @property
    @abstractmethod
    def is_available(self) -> bool:
        """API キーが設定されており利用可能かを返す。"""
        ...
