"""AI 分析の実行エンドポイント。"""
import json
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.models.patent import Patent
from backend.app.services import ai_analyzer, pdf_importer, word_importer

router = APIRouter(prefix="/analyze", tags=["analyze"])


@router.post("/{patent_id}")
async def analyze_patent(patent_id: str, db: Session = Depends(get_db)):
    """登録済み特許の AI 分析を実行する。"""
    patent = db.query(Patent).filter(Patent.id == patent_id).first()
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")
    if not patent.claims_text:
        raise HTTPException(status_code=400, detail="テキストデータが未取得です。")

    patent.analysis_status = "analyzing"
    db.commit()

    try:
        result = await ai_analyzer.analyze_patent(text=patent.claims_text)
        patent.summary = result.get("summary", "")
        patent.key_points = json.dumps(result.get("key_points", []), ensure_ascii=False)
        patent.claims_structured = result.get("claims_structured")
        patent.mermaid_diagram = result.get("mermaid_diagram", "")
        patent.drawio_xml = result.get("drawio_xml", "")
        patent.analysis_status = "done"
    except RuntimeError as e:
        patent.analysis_status = "error"
        db.commit()
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        patent.analysis_status = "error"
        db.commit()
        raise HTTPException(status_code=500, detail=f"分析中にエラーが発生しました: {e}")

    db.commit()
    db.refresh(patent)
    return {
        "id": patent.id,
        "summary": patent.summary,
        "key_points": json.loads(patent.key_points or "[]"),
        "claims_structured": patent.claims_structured,
        "mermaid_diagram": patent.mermaid_diagram,
        "drawio_xml": patent.drawio_xml,
        "analysis_status": patent.analysis_status,
    }
