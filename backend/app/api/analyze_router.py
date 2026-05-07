"""AI 分析の実行エンドポイント。"""
import json
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.models.patent import Patent
from backend.app.services import ai_analyzer

router = APIRouter(prefix="/analyze", tags=["analyze"])


@router.post("/{patent_id}")
async def analyze_patent(patent_id: str, db: Session = Depends(get_db)):
    """登録済み特許の AI 分析を実行する。

    書誌情報・要約・請求項・詳細説明を結合して Claude API に送信し、
    以下を生成して DB に保存する:
    - summary: 発明の概要 3〜5文
    - key_points: 権利化ポイントリスト
    - claims_structured: 構造化請求項
    - mermaid_diagram: Mermaid フロー図
    - drawio_xml: Draw.io XML
    """
    patent = db.query(Patent).filter(Patent.id == patent_id).first()
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")

    # 分析可能なテキストがあるか確認
    has_text = any([patent.abstract, patent.claims_text, patent.description_text])
    if not has_text:
        raise HTTPException(status_code=400, detail="分析可能なテキストデータがありません。")

    patent.analysis_status = "analyzing"
    db.commit()

    try:
        # 書誌・要約・請求項・詳細説明を結合
        biblio_parts = []
        if patent.title:
            biblio_parts.append(f"発明の名称: {patent.title}")
        if patent.applicant:
            biblio_parts.append(f"出願人: {patent.applicant}")
        if patent.ipc_codes:
            biblio_parts.append(f"IPC: {patent.ipc_codes}")
        biblio_text = "\n".join(biblio_parts)

        full_text = ai_analyzer.compose_patent_text(
            biblio_text=biblio_text,
            abstract_text=patent.abstract or "",
            claims_text=patent.claims_text or "",
            description_text=patent.description_text or "",
        )

        result = await ai_analyzer.analyze_patent(text=full_text)

        patent.summary = result.get("summary", "")
        patent.key_points = json.dumps(result.get("key_points", []), ensure_ascii=False)
        patent.claims_structured = result.get("claims_structured")
        patent.mermaid_diagram = result.get("mermaid_diagram", "")
        patent.drawio_xml = result.get("drawio_xml", "")
        patent.analysis_status = "done"

    except RuntimeError as e:
        # Claude API が利用不可
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
        "patent_number": patent.patent_number,
        "title": patent.title,
        "summary": patent.summary,
        "key_points": json.loads(patent.key_points or "[]"),
        "claims_structured": patent.claims_structured,
        "mermaid_diagram": patent.mermaid_diagram,
        "drawio_xml": patent.drawio_xml,
        "analysis_status": patent.analysis_status,
    }
