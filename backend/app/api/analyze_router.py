"""AI 分析の実行エンドポイント。"""
import json
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from backend.app.core.database import get_db, SessionLocal
from backend.app.models.patent import Patent
from backend.app.services import ai_analyzer

router = APIRouter(prefix="/analyze", tags=["analyze"])


def _build_biblio_text(patent: Patent) -> str:
    parts = []
    if patent.title:
        parts.append(f"発明の名称: {patent.title}")
    if patent.applicant:
        parts.append(f"出願人: {patent.applicant}")
    if patent.ipc_codes:
        parts.append(f"IPC: {patent.ipc_codes}")
    return "\n".join(parts)


@router.post("/{patent_id}")
async def analyze_patent(
    patent_id: str,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    """登録済み特許の AI 分析をバックグラウンドで開始する。

    即座に {"analysis_status": "analyzing"} を返す。
    フロントエンドは GET /patents/{id} をポーリングして完了を検知する。
    """
    patent = db.query(Patent).filter(Patent.id == patent_id).first()
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")

    has_text = any([patent.abstract, patent.claims_text, patent.description_text])
    if not has_text:
        raise HTTPException(status_code=400, detail="分析可能なテキストデータがありません。")

    if patent.analysis_status == "analyzing":
        return {"id": patent_id, "analysis_status": "analyzing"}

    # テキストを事前に構築（background task では DB セッションが無効なため）
    biblio_text = _build_biblio_text(patent)
    full_text = ai_analyzer.compose_patent_text(
        biblio_text=biblio_text,
        abstract_text=patent.abstract or "",
        claims_text=patent.claims_text or "",
        description_text=patent.description_text or "",
    )

    patent.analysis_status = "analyzing"
    db.commit()

    background_tasks.add_task(_run_analysis_task, patent_id, full_text)
    return {"id": patent_id, "analysis_status": "analyzing"}


async def _run_analysis_task(patent_id: str, full_text: str) -> None:
    """バックグラウンドで AI 分析を 3 ステップ順次実行し、各完了後に DB へ保存する。"""
    db = SessionLocal()
    try:
        # Step 1: 発明の概要
        result = await ai_analyzer.analyze_summary(full_text)
        patent = db.query(Patent).filter(Patent.id == patent_id).first()
        if not patent:
            return
        patent.summary = result.get("summary", "")
        db.commit()

        # Step 2: 権利化ポイント
        result = await ai_analyzer.analyze_key_points(full_text)
        patent = db.query(Patent).filter(Patent.id == patent_id).first()
        patent.key_points = json.dumps(
            result.get("key_points", []), ensure_ascii=False
        )
        db.commit()

        # Step 3: 請求項構造 + Mermaid 図
        result = await ai_analyzer.analyze_claims(full_text)
        patent = db.query(Patent).filter(Patent.id == patent_id).first()
        patent.claims_structured = result.get("claims_structured")
        patent.mermaid_diagram = result.get("mermaid_diagram", "")
        patent.analysis_status = "done"
        db.commit()

    except Exception:
        try:
            patent = db.query(Patent).filter(Patent.id == patent_id).first()
            if patent:
                patent.analysis_status = "error"
                db.commit()
        except Exception:
            pass
    finally:
        db.close()
