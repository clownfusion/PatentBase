"""レポート出力エンドポイント（Step 1-F で実装）。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.models.patent import Patent

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get("/{patent_id}/drawio")
def download_drawio(patent_id: str, db: Session = Depends(get_db)):
    """Draw.io XML をダウンロードする。"""
    patent = db.query(Patent).filter(Patent.id == patent_id).first()
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")
    if not patent.drawio_xml:
        raise HTTPException(status_code=404, detail="Draw.io データが未生成です。先に分析を実行してください。")

    from fastapi.responses import Response
    filename = f"patent_{patent.patent_number or patent.id}.drawio"
    return Response(
        content=patent.drawio_xml,
        media_type="application/xml",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/{patent_id}/word")
async def download_word(patent_id: str, db: Session = Depends(get_db)):
    """Word レポートをダウンロードする（Step 1-F で実装）。"""
    raise HTTPException(status_code=501, detail="Word 出力は Step 1-F で実装予定です。")


@router.get("/{patent_id}/excel")
async def download_excel(patent_id: str, db: Session = Depends(get_db)):
    """Excel レポートをダウンロードする（Step 1-F で実装）。"""
    raise HTTPException(status_code=501, detail="Excel 出力は Step 1-F で実装予定です。")
