"""Word (.docx) ファイルから特許テキストと図面を抽出するサービス。"""
from dataclasses import dataclass, field
from pathlib import Path
from .pdf_importer import PatentDocument


async def import_word(path: Path | str) -> PatentDocument:
    """Word ファイルを読み込み、テキストと画像を返す。"""
    from docx import Document
    from docx.oxml.ns import qn
    import io

    path = Path(path)
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

    return PatentDocument(
        text=text,
        images=images,
        metadata={"source_file": path.name},
    )
