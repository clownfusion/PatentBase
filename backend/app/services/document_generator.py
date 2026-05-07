"""Word / Excel / Draw.io XML の出力サービス。"""
from pathlib import Path
import io


async def export_analysis_to_word(analysis: dict, output_path: Path) -> None:
    """分析結果を Word ファイルとして出力する。"""
    # TODO: Step 1-F で実装
    raise NotImplementedError("Step 1-F で実装予定です。")


async def export_analysis_to_excel(analysis: dict, output_path: Path) -> None:
    """分析結果を Excel ファイルとして出力する。"""
    # TODO: Step 1-F で実装
    raise NotImplementedError("Step 1-F で実装予定です。")


def get_drawio_xml(analysis: dict) -> str:
    """Draw.io XML を返す（分析結果に含まれている場合はそのまま返す）。"""
    return analysis.get("drawio_xml", "")
