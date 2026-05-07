from sqlalchemy import Column, String, Text, DateTime, JSON
from sqlalchemy.sql import func
from backend.app.core.database import Base


class Patent(Base):
    __tablename__ = "patents"

    # 特許識別
    id = Column(String, primary_key=True)          # 内部 UUID
    patent_number = Column(String, index=True)      # 特開2020-123456 等
    source = Column(String, nullable=False)         # "jplatpat" | "pdf" | "word"

    # 書誌情報（J-PlatPat / 明細書から取得）
    title = Column(Text)
    applicant = Column(Text)
    inventor = Column(Text)
    filing_date = Column(String)
    publication_date = Column(String)
    ipc_codes = Column(Text)                        # カンマ区切り
    abstract = Column(Text)

    # 本文データ
    claims_text = Column(Text)                      # 請求項全文
    description_text = Column(Text)                 # 明細書本文（取得済みの場合）
    figures_metadata = Column(JSON)                 # [{page, caption, path}, ...]

    # AI 分析結果
    summary = Column(Text)                          # 要約
    key_points = Column(Text)                       # 要点（JSON 文字列）
    claims_structured = Column(JSON)                # 請求項構造化データ
    mermaid_diagram = Column(Text)                  # Mermaid 図コード
    drawio_xml = Column(Text)                       # Draw.io XML

    # 管理
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    analysis_status = Column(String, default="pending")  # pending|analyzing|done|error
