"""PDF ファイルから特許テキストと図面画像を抽出するサービス。"""
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class PatentDocument:
    text: str
    images: list[bytes] = field(default_factory=list)   # PNG バイト列のリスト
    metadata: dict = field(default_factory=dict)


async def import_pdf(path: Path | str) -> PatentDocument:
    """PDF ファイルを読み込み、テキストと図面画像を返す。"""
    import pdfplumber
    import fitz  # PyMuPDF

    path = Path(path)
    text_parts: list[str] = []
    images: list[bytes] = []

    # テキスト抽出（pdfplumber）
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            if page_text:
                text_parts.append(page_text)

    # 図面抽出（PyMuPDF）
    doc = fitz.open(str(path))
    for page in doc:
        for img_info in page.get_images(full=True):
            xref = img_info[0]
            img_data = doc.extract_image(xref)
            images.append(img_data["image"])
    doc.close()

    return PatentDocument(
        text="\n\n".join(text_parts),
        images=images,
    )
