"""レポート出力エンドポイント。

GET /reports/{patent_id}/drawio  → Draw.io XML ファイルダウンロード
GET /reports/{patent_id}/word    → Word (.docx) ファイルダウンロード
GET /reports/{patent_id}/excel   → Excel (.xlsx) ファイルダウンロード
"""
import urllib.parse
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.models.patent import Patent
from backend.app.services import document_generator

router = APIRouter(prefix="/reports", tags=["reports"])


def _get_patent_or_404(patent_id: str, db: Session) -> Patent:
    patent = db.query(Patent).filter(Patent.id == patent_id).first()
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")
    return patent


def _content_disposition(patent: Patent, ext: str) -> str:
    """RFC 5987 形式の Content-Disposition ヘッダー値を返す。

    日本語を含む特許番号でも latin-1 エンコードエラーが起きないよう
    filename*=UTF-8''... 形式でパーセントエンコードする。
    """
    num = (patent.patent_number or patent.id).replace("/", "-").replace(" ", "_")
    filename = f"patent_{num}.{ext}"
    encoded = urllib.parse.quote(filename.encode("utf-8"), safe="")
    return f"attachment; filename*=UTF-8''{encoded}"


@router.get("/{patent_id}/drawio")
def download_drawio(patent_id: str, db: Session = Depends(get_db)):
    """Draw.io XML をダウンロードする。"""
    patent = _get_patent_or_404(patent_id, db)
    if not patent.drawio_xml:
        raise HTTPException(
            status_code=404,
            detail="Draw.io データが未生成です。先に AI 分析を実行してください。",
        )
    return Response(
        content=patent.drawio_xml,
        media_type="application/xml",
        headers={"Content-Disposition": _content_disposition(patent, "drawio")},
    )


@router.get("/{patent_id}/word")
def download_word(patent_id: str, db: Session = Depends(get_db)):
    """Word レポートをダウンロードする。"""
    patent = _get_patent_or_404(patent_id, db)
    try:
        content = document_generator.generate_word_report(patent)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Word 生成中にエラーが発生しました: {e}")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        headers={"Content-Disposition": _content_disposition(patent, "docx")},
    )


@router.get("/{patent_id}/excel")
def download_excel(patent_id: str, db: Session = Depends(get_db)):
    """Excel サマリーをダウンロードする。"""
    patent = _get_patent_or_404(patent_id, db)
    try:
        content = document_generator.generate_excel_summary(patent)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Excel 生成中にエラーが発生しました: {e}")
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": _content_disposition(patent, "xlsx")},
    )
