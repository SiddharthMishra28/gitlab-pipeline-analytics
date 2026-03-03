from datetime import datetime, timezone

from sqlalchemy import JSON, BigInteger, DateTime, Float, Integer, String, Text, create_engine
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class PipelineFailure(Base):
    __tablename__ = "pipeline_failures"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    flow_execution_uuid: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    pipeline_id: Mapped[int] = mapped_column(BigInteger, index=True, nullable=False)
    job_observe_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    job_ids: Mapped[list[int]] = mapped_column(ARRAY(BigInteger).with_variant(JSON, "sqlite"), nullable=False)
    failure_category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    suggested_fix: Mapped[str | None] = mapped_column(Text, nullable=True)
    diagnostic_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    log_excerpt: Mapped[str | None] = mapped_column(Text, nullable=True)
    llm_metadata: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False
    )


class Database:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

    def init(self) -> None:
        Base.metadata.create_all(self.engine)

    def save_failure(self, record: dict) -> None:
        with self.SessionLocal() as session:
            row = PipelineFailure(
                flow_execution_uuid=record["flowExecutionUuid"],
                pipeline_id=record["pipelineId"],
                job_observe_id=record["jobObserveId"],
                job_ids=record["jobIds"],
                failure_category=record.get("failureCategory"),
                suggested_fix=record.get("suggestedFix"),
                diagnostic_confidence=record.get("diagnosticConfidence"),
                log_excerpt=record.get("logExcerpt"),
                llm_metadata=record.get("llmMetadata"),
            )
            session.add(row)
            session.commit()
