from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutionNode:
    node_id: str
    name: str
    kind: str
    phase: str | None = None
    template: str | None = None
    agent: str | None = None
    message: str | None = None
    exit_code: int | None = None
    children: tuple[str, ...] = ()
    started_at: str | None = None
    finished_at: str | None = None
    artifacts: tuple[str, ...] = ()
    #: The step's last refusal line, read off its ``refusal`` output (#181); None when the
    #: step said nothing or the executor kept no outputs.
    refusal: str | None = None
