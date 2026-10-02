from dataclasses import dataclass
from enum import StrEnum


class TaskKind(StrEnum):
    PAPER_PARSE = "paper_parse"
    KNOWLEDGE_EXTRACT = "knowledge_extract"
    SCHEME_GENERATE = "scheme_generate"


class TaskStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    PARTIAL = "partial"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_STATUSES = frozenset(
    {TaskStatus.SUCCEEDED, TaskStatus.PARTIAL, TaskStatus.FAILED, TaskStatus.CANCELLED}
)


@dataclass(frozen=True, slots=True)
class TaskSpec:
    timeout: int
    resource_type: str


TASK_SPECS = {
    TaskKind.PAPER_PARSE: TaskSpec(timeout=1800, resource_type="paper"),
    TaskKind.KNOWLEDGE_EXTRACT: TaskSpec(timeout=7200, resource_type="paper"),
    TaskKind.SCHEME_GENERATE: TaskSpec(timeout=3600, resource_type="project"),
}


def task_event_name(status: str) -> str:
    if status in {TaskStatus.SUCCEEDED, TaskStatus.PARTIAL}:
        return "completed"
    return status if status in {TaskStatus.FAILED, TaskStatus.CANCELLED} else "progress"
