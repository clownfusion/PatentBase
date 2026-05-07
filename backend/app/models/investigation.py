from sqlalchemy import Column, String, Text, DateTime, ForeignKey, JSON
from sqlalchemy.sql import func
from backend.app.core.database import Base


class Investigation(Base):
    """調査案件（Phase 2 以降で使用）"""
    __tablename__ = "investigations"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)           # 案件名
    investigation_type = Column(String)             # "prior_art" | "pre_filing"
    purpose = Column(Text)                          # 調査目的
    status = Column(String, default="active")       # active | completed | archived
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class InvestigationPatent(Base):
    """調査案件と特許の紐付け（Phase 2 以降で使用）"""
    __tablename__ = "investigation_patents"

    id = Column(String, primary_key=True)
    investigation_id = Column(String, ForeignKey("investigations.id"), nullable=False)
    patent_id = Column(String, ForeignKey("patents.id"), nullable=False)

    # スクリーニング結果
    screening_1st = Column(String)                  # relevant | irrelevant | pending
    screening_1st_note = Column(Text)
    screening_2nd = Column(String)
    screening_2nd_note = Column(Text)

    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
