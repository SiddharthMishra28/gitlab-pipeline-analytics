from datetime import datetime, timezone
from uuid import UUID
import threading

from sqlalchemy import JSON, BIGINT, Boolean, DateTime, String, create_engine, func, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class PipelineExecution(Base):
    __tablename__ = "PIPELINE_EXECUTIONS"

    id: Mapped[int] = mapped_column("ID", BIGINT, primary_key=True)
    configured_test_data: Mapped[dict | None] = mapped_column("CONFIGURED_TEST_DATA", JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column("CREATED_AT", DateTime(timezone=False), nullable=False)
    end_time: Mapped[datetime | None] = mapped_column("END_TIME", DateTime(timezone=False), nullable=True)
    flow_execution_id: Mapped[str] = mapped_column("FLOW_EXECUTION_ID", String(36), nullable=False)
    flow_id: Mapped[int] = mapped_column("FLOW_ID", BIGINT, nullable=False)
    flow_step_id: Mapped[int] = mapped_column("FLOW_STEP_ID", BIGINT, nullable=False)
    is_replay: Mapped[bool] = mapped_column("IS_REPLAY", Boolean, nullable=False)
    job_id: Mapped[int | None] = mapped_column("JOB_ID", BIGINT, nullable=True)
    job_url: Mapped[str | None] = mapped_column("JOB_URL", String(255), nullable=True)
    pipeline_id: Mapped[int | None] = mapped_column("PIPELINE_ID", BIGINT, nullable=True)
    pipeline_url: Mapped[str | None] = mapped_column("PIPELINE_URL", String(255), nullable=True)
    resume_time: Mapped[datetime | None] = mapped_column("RESUME_TIME", DateTime(timezone=False), nullable=True)
    runtime_test_data: Mapped[dict | None] = mapped_column("RUNTIME_TEST_DATA", JSON, nullable=True)
    start_time: Mapped[datetime | None] = mapped_column("START_TIME", DateTime(timezone=False), nullable=True)
    status: Mapped[str | None] = mapped_column("STATUS", String(255), nullable=True)


class Database:
    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, future=True)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        self._id_lock = threading.Lock()

    def init(self) -> None:
        Base.metadata.create_all(self.engine)

    def _next_id(self, session) -> int:
        max_id = session.execute(select(func.max(PipelineExecution.id))).scalar_one_or_none()
        return (max_id or 0) + 1

    def save_failure(self, record: dict) -> None:
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        flow_id = str(record["flowExecutionUuid"])
        try:
            UUID(flow_id)
        except Exception:
            pass

        with self._id_lock:
            with self.SessionLocal() as session:
                row = (
                    session.query(PipelineExecution)
                    .filter(PipelineExecution.flow_execution_id == flow_id)
                    .filter(PipelineExecution.job_id == record.get("jobObserveId"))
                    .order_by(PipelineExecution.id.desc())
                    .first()
                )
                if not row:
                    row = PipelineExecution(
                        id=self._next_id(session),
                        created_at=now,
                        flow_execution_id=flow_id,
                        flow_id=int(record.get("flowId", 0)),
                        flow_step_id=int(record.get("flowStepId", 0)),
                        is_replay=bool(record.get("isReplay", False)),
                        job_id=record.get("jobObserveId"),
                        pipeline_id=record.get("pipelineId"),
                        status="FAILED",
                        start_time=now,
                    )
                    session.add(row)

                row.end_time = now
                row.status = "FAILED"
                row.runtime_test_data = {
                    "diagnostics": {
                        "failureCategory": record.get("failureCategory"),
                        "suggestedFix": record.get("suggestedFix"),
                        "diagnosticConfidence": record.get("diagnosticConfidence"),
                        "logExcerpt": record.get("logExcerpt"),
                        "llmMetadata": record.get("llmMetadata"),
                        "jobIds": record.get("jobIds", []),
                        "timestamp": record.get("timestamp"),
                    }
                }
                session.commit()
