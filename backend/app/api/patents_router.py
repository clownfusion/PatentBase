"""特許の登録・取得エンドポイント。"""
import uuid
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from backend.app.core.database import get_db
from backend.app.models.patent import Patent
from backend.app.services import pdf_importer, word_importer, jplatpat_scraper, ai_analyzer

router = APIRouter(prefix="/patents", tags=["patents"])


@router.post("/from-number")
async def register_from_number(
    patent_number: str = Form(...),
    db: Session = Depends(get_db),
):
    """特許番号から J-PlatPat で情報を取得して登録する。"""
    try:
        doc = await jplatpat_scraper.fetch_patent(patent_number)
    except NotImplementedError as e:
        raise HTTPException(status_code=501, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    import json
    figures_meta = [{"figure_number": f.figure_number, "url": f.url} for f in doc.figures]
    patent = _create_patent_record(
        db=db,
        patent_number=doc.biblio.patent_number,
        source="jplatpat",
        title=doc.biblio.title,
        applicant=doc.biblio.applicant,
        abstract=doc.abstract,
        claims_text=doc.claims_text,
        description_text=doc.description_text,
        metadata={"figures": figures_meta, "isn": doc.biblio.isn, "ipc": doc.biblio.ipc_codes},
    )
    return {"id": patent.id, "patent_number": patent.patent_number, "title": patent.title}


@router.post("/from-pdf")
async def register_from_pdf(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """PDF ファイルをアップロードして特許を登録する。"""
    import tempfile, os
    suffix = Path(file.filename or "upload.pdf").suffix
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        doc = await pdf_importer.import_pdf(tmp_path)
    finally:
        os.unlink(tmp_path)

    patent = _create_patent_record(
        db=db,
        source="pdf",
        claims_text=doc.text,
        metadata={"filename": file.filename, "images_count": len(doc.images)},
    )
    return {"id": patent.id}


@router.post("/from-word")
async def register_from_word(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Word ファイルをアップロードして特許を登録する。"""
    import tempfile, os
    with tempfile.NamedTemporaryFile(delete=False, suffix=".docx") as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name
    try:
        doc = await word_importer.import_word(tmp_path)
    finally:
        os.unlink(tmp_path)

    patent = _create_patent_record(
        db=db,
        source="word",
        claims_text=doc.text,
        metadata={"filename": file.filename},
    )
    return {"id": patent.id}


@router.get("/{patent_id}")
def get_patent(patent_id: str, db: Session = Depends(get_db)):
    """特許の詳細を取得する。"""
    patent = db.query(Patent).filter(Patent.id == patent_id).first()
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")
    return _patent_to_dict(patent)


@router.get("/")
def list_patents(db: Session = Depends(get_db)):
    """登録済み特許の一覧を返す。"""
    patents = db.query(Patent).order_by(Patent.created_at.desc()).all()
    return [_patent_to_dict(p) for p in patents]


def _create_patent_record(db: Session, source: str, claims_text: str = "",
                           patent_number: str = "", title: str = "",
                           applicant: str = "", abstract: str = "",
                           description_text: str = "",
                           metadata: dict | None = None) -> Patent:
    patent = Patent(
        id=str(uuid.uuid4()),
        patent_number=patent_number,
        source=source,
        title=title,
        applicant=applicant,
        abstract=abstract,
        claims_text=claims_text,
        description_text=description_text,
        figures_metadata=metadata or {},
        analysis_status="pending",
    )
    db.add(patent)
    db.commit()
    db.refresh(patent)
    return patent


def _patent_to_dict(p: Patent) -> dict:
    return {
        "id": p.id,
        "patent_number": p.patent_number,
        "source": p.source,
        "title": p.title,
        "abstract": p.abstract,
        "summary": p.summary,
        "key_points": p.key_points,
        "claims_structured": p.claims_structured,
        "mermaid_diagram": p.mermaid_diagram,
        "drawio_xml": p.drawio_xml,
        "analysis_status": p.analysis_status,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
