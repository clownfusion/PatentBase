"""特許の登録・取得・削除エンドポイント。"""
import uuid
from pathlib import Path
from typing import List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Body
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
        raise HTTPException(
            status_code=501,
            detail=str(e) or "J-PlatPat スクレイパーが未実装または初期化に失敗しました",
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    b = doc.biblio
    figures_meta = [{"figure_number": f.figure_number, "url": f.url} for f in doc.figures]
    # 特許公報は registration_number を、公開公報は patent_number (公開番号) を主番号とする
    primary_number = b.registration_number or b.patent_number or patent_number
    # 特許権者がいれば出願人として格納（特許公報）、なければ出願人（公開公報）
    applicant_name = b.patentee or b.applicant
    patent = _create_patent_record(
        db=db,
        patent_number=primary_number,
        source="jplatpat",
        title=b.title,
        applicant=applicant_name,
        filing_date=b.filing_date,
        publication_date=b.publication_date,
        abstract=doc.abstract,
        claims_text=doc.claims_text,
        description_text=doc.description_text,
        metadata={
            "figures": figures_meta,
            "isn": b.isn,
            "ipc": b.ipc_codes,
            "publication_type": b.publication_type,
            "app_number": b.app_number,
            "publication_number": b.patent_number,
            "registration_number": b.registration_number,
            "filing_date": b.filing_date,
            "publication_date": b.publication_date,
            "registration_date": b.registration_date,
            "patentee": b.patentee,
            "applicant": b.applicant,
            "inventor": b.inventor,
            "status": b.status,
            "progress_info": b.progress_info,
            "jplatpat_url": b.jplatpat_url,
        },
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
    except RuntimeError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF の処理中にエラーが発生しました: {e}")
    finally:
        os.unlink(tmp_path)

    b = doc.biblio
    patent = _create_patent_record(
        db=db,
        source="pdf",
        patent_number=b.get("patent_number") or "【公開番号/登録番号】が含まれておらず不明",
        title=b.get("title") or "【発明の名称】が含まれておらずタイトル不明",
        applicant=b.get("applicant") or "【出願人】が含まれておらず不明",
        claims_text=doc.text,
        metadata={
            "filename": file.filename,
            "images_count": len(doc.images),
            "ipc": b.get("ipc_codes", ""),
            "app_number": b.get("app_number", ""),
            "filing_date": b.get("filing_date", ""),
            "publication_date": b.get("publication_date", ""),
        },
    )
    return {"id": patent.id, "patent_number": patent.patent_number, "title": patent.title}


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
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Word の処理中にエラーが発生しました: {e}")
    finally:
        os.unlink(tmp_path)

    b = doc.biblio
    # 登録番号があれば優先、なければ公開番号
    patent_num = b.get("registration_number") or b.get("patent_number") or "【公開番号/登録番号】が含まれておらず不明"
    patent = _create_patent_record(
        db=db,
        source="word",
        patent_number=patent_num,
        title=b.get("title") or "【発明の名称】が含まれておらずタイトル不明",
        applicant=b.get("applicant") or "【出願人】が含まれておらず不明",
        abstract=doc.abstract,
        claims_text=doc.claims_text,
        description_text=doc.description_text,
        filing_date=b.get("filing_date", ""),
        publication_date=b.get("publication_date", ""),
        metadata={
            "filename": file.filename,
            "ipc": b.get("ipc_codes", ""),
            "app_number": b.get("app_number", ""),
            "filing_date": b.get("filing_date", ""),
            "publication_date": b.get("publication_date", ""),
        },
    )
    return {"id": patent.id, "patent_number": patent.patent_number, "title": patent.title}


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


@router.delete("/bulk")
def delete_patents_bulk(ids: List[str] = Body(...), db: Session = Depends(get_db)):
    """指定した複数の特許をまとめて削除する。"""
    db.query(Patent).filter(Patent.id.in_(ids)).delete(synchronize_session=False)
    db.commit()
    return {"ok": True, "deleted": len(ids)}


@router.delete("/{patent_id}")
def delete_patent(patent_id: str, db: Session = Depends(get_db)):
    """特許を1件削除する。"""
    patent = db.query(Patent).filter(Patent.id == patent_id).first()
    if not patent:
        raise HTTPException(status_code=404, detail="Patent not found")
    db.delete(patent)
    db.commit()
    return {"ok": True}


def _create_patent_record(db: Session, source: str, claims_text: str = "",
                           patent_number: str = "", title: str = "",
                           applicant: str = "", abstract: str = "",
                           description_text: str = "",
                           filing_date: str = "", publication_date: str = "",
                           metadata: dict | None = None) -> Patent:
    patent = Patent(
        id=str(uuid.uuid4()),
        patent_number=patent_number,
        source=source,
        title=title,
        applicant=applicant,
        filing_date=filing_date or None,
        publication_date=publication_date or None,
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
        "applicant": p.applicant,
        "ipc_codes": p.ipc_codes,
        "filing_date": p.filing_date,
        "publication_date": p.publication_date,
        "abstract": p.abstract,
        "claims_text": p.claims_text,
        "description_text": p.description_text,
        "summary": p.summary,
        "key_points": p.key_points,
        "claims_structured": p.claims_structured,
        "mermaid_diagram": p.mermaid_diagram,
        "drawio_xml": p.drawio_xml,
        "analysis_status": p.analysis_status,
        "metadata": p.figures_metadata,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }
