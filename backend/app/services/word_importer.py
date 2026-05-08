"""Word (.docx) ファイルから特許テキストと図面を抽出するサービス。"""
import logging
from pathlib import Path
from .pdf_importer import PatentDocument
from .jplatpat_scraper import parse_biblio

logger = logging.getLogger(__name__)


async def import_word(path: Path | str) -> PatentDocument:
    """Word ファイルを読み込み、テキスト・書誌情報・画像を返す。"""
    from docx import Document

    path = Path(path)
    logger.info(f"Word インポート開始: {path.name}")
    doc = Document(str(path))

    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    text = "\n\n".join(paragraphs)

    images: list[bytes] = []
    for rel in doc.part.rels.values():
        if "image" in rel.target_ref:
            try:
                images.append(rel.target_part.blob)
            except Exception:
                pass

    biblio = parse_biblio(text)
    logger.info(f"書誌解析結果: title={biblio.get('title', '')!r}")

    return PatentDocument(
        text=text,
        images=images,
        metadata={"source_file": path.name},
        biblio=biblio,
    )
