"""PDF ファイルから特許テキストと図面画像を抽出するサービス。"""
import logging
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass
class PatentDocument:
    text: str
    images: list[bytes] = field(default_factory=list)   # PNG バイト列のリスト
    metadata: dict = field(default_factory=dict)
    biblio: dict = field(default_factory=dict)           # 書誌情報（parse_biblio の結果）


async def import_pdf(path: Path | str) -> PatentDocument:
    """PDF ファイルを読み込み、テキスト・書誌情報・図面画像を返す。"""
    import pdfplumber
    import fitz  # PyMuPDF
    from .jplatpat_scraper import parse_biblio

    path = Path(path)
    logger.info(f"PDF インポート開始: {path.name}")
    text_parts: list[str] = []
    images: list[bytes] = []

    # テキスト抽出（pdfplumber）
    try:
        with pdfplumber.open(path) as pdf:
            page_count = len(pdf.pages)
            logger.info(f"PDF ページ数: {page_count}")
            for page in pdf.pages:
                page_text = page.extract_text() or ""
                if page_text:
                    text_parts.append(page_text)
            logger.info(f"テキスト抽出完了: {len(text_parts)} ページにテキストあり")
    except Exception as e:
        logger.error(f"pdfplumber テキスト抽出エラー: {e}")
        raise RuntimeError(f"PDF のテキスト抽出に失敗しました: {e}") from e

    # 図面抽出（PyMuPDF）
    try:
        doc = fitz.open(str(path))
        for page in doc:
            for img_info in page.get_images(full=True):
                xref = img_info[0]
                img_data = doc.extract_image(xref)
                images.append(img_data["image"])
        doc.close()
        logger.info(f"図面抽出完了: {len(images)} 枚")
    except Exception as e:
        logger.warning(f"PyMuPDF 図面抽出エラー（テキストは利用可能）: {e}")

    full_text = "\n\n".join(text_parts)
    if not full_text:
        logger.warning("テキストが抽出できませんでした（スキャン PDF の可能性）")

    biblio = parse_biblio(full_text)
    logger.info(f"書誌解析結果: title={biblio.get('title', '')!r}")

    return PatentDocument(
        text=full_text,
        images=images,
        biblio=biblio,
    )
