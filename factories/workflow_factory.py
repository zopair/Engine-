from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping

from memory.database import Database


class WorkflowExecutionError(RuntimeError):
    def __init__(self, run_id: str, step_name: str, cause: Exception):
        super().__init__(f"Workflow {run_id} failed at step '{step_name}': {cause}")
        self.run_id = run_id
        self.step_name = step_name


class WorkflowBusyError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WorkflowStep:
    name: str
    handler: Callable[[Mapping[str, Any], Mapping[str, Any]], Any]


@dataclass(frozen=True, slots=True)
class WorkflowResult:
    run_id: str
    status: str
    outputs: dict[str, Any]


class Workflow:
    def __init__(
        self,
        database: Database,
        name: str,
        steps: tuple[WorkflowStep, ...],
        lease_seconds: int = 900,
    ) -> None:
        self.database = database
        self.name = name
        self.steps = steps
        self.lease_seconds = max(30, int(lease_seconds))
        self.owner = uuid.uuid4().hex

    def run(self, input_data: Mapping[str, Any], run_id: str | None = None) -> WorkflowResult:
        run_id = run_id or uuid.uuid4().hex
        encoded_input = self._encode(dict(input_data))
        now = time.time()
        with self.database.connect() as connection:
            connection.execute(
                """INSERT INTO workflow_runs
                   (run_id, workflow_name, status, input_json, outputs_json, created_at, updated_at)
                   VALUES (?, ?, 'pending', ?, '{}', ?, ?)""",
                (run_id, self.name, encoded_input, now, now),
            )
            connection.executemany(
                """INSERT INTO workflow_steps(run_id, step_name, position, status)
                   VALUES (?, ?, ?, 'pending')""",
                [(run_id, step.name, position) for position, step in enumerate(self.steps)],
            )
        return self._execute(run_id)

    def resume(self, run_id: str) -> WorkflowResult:
        with self.database.connect() as connection:
            run = connection.execute(
                "SELECT workflow_name, status FROM workflow_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            rows = connection.execute(
                "SELECT step_name FROM workflow_steps WHERE run_id=? ORDER BY position", (run_id,)
            ).fetchall()
        if run is None:
            raise KeyError(f"Unknown workflow run: {run_id}")
        if run["workflow_name"] != self.name:
            raise ValueError("workflow name does not match persisted run")
        if [row["step_name"] for row in rows] != [step.name for step in self.steps]:
            raise ValueError("workflow step definition differs from persisted run")
        if run["status"] == "completed":
            return self._result(run_id)
        return self._execute(run_id)

    @staticmethod
    def _encode(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"workflow state must be JSON serializable: {exc}") from exc

    def _claim(self, run_id: str) -> dict[str, Any]:
        now = time.time()
        with self.database.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM workflow_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise KeyError(f"Unknown workflow run: {run_id}")
            if row["status"] == "completed":
                return dict(row)
            if (
                row["status"] == "running"
                and row["lease_owner"] != self.owner
                and (row["lease_until"] or 0) > now
            ):
                raise WorkflowBusyError(f"Workflow run {run_id} is owned by another worker")
            connection.execute(
                """UPDATE workflow_runs SET status='running', lease_owner=?, lease_until=?, updated_at=?
                   WHERE run_id=?""",
                (self.owner, now + self.lease_seconds, now, run_id),
            )
            return dict(row)

    def _execute(self, run_id: str) -> WorkflowResult:
        run = self._claim(run_id)
        if run["status"] == "completed":
            return self._result(run_id)
        input_data = json.loads(run["input_json"])
        outputs = json.loads(run["outputs_json"] or "{}")
        try:
            for step in self.steps:
                with self.database.connect() as connection:
                    persisted = connection.execute(
                        "SELECT status, output_json FROM workflow_steps WHERE run_id=? AND step_name=?",
                        (run_id, step.name),
                    ).fetchone()
                if persisted["status"] == "completed":
                    outputs[step.name] = json.loads(persisted["output_json"] or "null")
                    continue

                now = time.time()
                with self.database.connect() as connection:
                    connection.execute(
                        """UPDATE workflow_steps SET status='running', error=NULL, started_at=?
                           WHERE run_id=? AND step_name=?""",
                        (now, run_id, step.name),
                    )
                    connection.execute(
                        "UPDATE workflow_runs SET lease_until=?, updated_at=? WHERE run_id=? AND lease_owner=?",
                        (now + self.lease_seconds, now, run_id, self.owner),
                    )
                try:
                    output = step.handler(input_data, dict(outputs))
                    encoded_output = self._encode(output)
                except Exception as exc:
                    with self.database.connect() as connection:
                        connection.execute(
                            """UPDATE workflow_steps SET status='failed', error=?
                               WHERE run_id=? AND step_name=?""",
                            (str(exc)[:2000], run_id, step.name),
                        )
                        connection.execute(
                            """UPDATE workflow_runs SET status='failed', lease_owner=NULL,
                               lease_until=NULL, updated_at=? WHERE run_id=?""",
                            (time.time(), run_id),
                        )
                    raise WorkflowExecutionError(run_id, step.name, exc) from exc

                outputs[step.name] = output
                with self.database.connect() as connection:
                    connection.execute(
                        """UPDATE workflow_steps SET status='completed', output_json=?,
                           error=NULL, completed_at=? WHERE run_id=? AND step_name=?""",
                        (encoded_output, time.time(), run_id, step.name),
                    )
                    connection.execute(
                        """UPDATE workflow_runs SET outputs_json=?, lease_until=?, updated_at=?
                           WHERE run_id=? AND lease_owner=?""",
                        (self._encode(outputs), time.time() + self.lease_seconds, time.time(), run_id, self.owner),
                    )
            with self.database.connect() as connection:
                connection.execute(
                    """UPDATE workflow_runs SET status='completed', lease_owner=NULL,
                       lease_until=NULL, updated_at=? WHERE run_id=? AND lease_owner=?""",
                    (time.time(), run_id, self.owner),
                )
            return WorkflowResult(run_id, "completed", outputs)
        except WorkflowExecutionError:
            raise

    def _result(self, run_id: str) -> WorkflowResult:
        with self.database.connect() as connection:
            row = connection.execute(
                "SELECT status, outputs_json FROM workflow_runs WHERE run_id=?", (run_id,)
            ).fetchone()
        return WorkflowResult(run_id, row["status"], json.loads(row["outputs_json"] or "{}"))


class WorkflowFactory:
    """Construct bounded workflows whose completed steps are checkpointed in SQLite."""

    def __init__(self, database: Database | None = None, lease_seconds: int = 900) -> None:
        self.database = database or Database()
        self.database.initialize()
        self.lease_seconds = lease_seconds

    def create(self, name: str, steps: list[WorkflowStep] | tuple[WorkflowStep, ...]) -> Workflow:
        name = name.strip()
        normalized = tuple(steps)
        names = [step.name.strip() for step in normalized]
        if not name or not normalized:
            raise ValueError("workflow name and at least one step are required")
        if len(normalized) > 100:
            raise ValueError("workflow cannot contain more than 100 steps")
        if any(not step_name or not callable(step.handler) for step, step_name in zip(normalized, names)):
            raise ValueError("every workflow step needs a name and callable handler")
        if len(set(names)) != len(names):
            raise ValueError("workflow step names must be unique")
        return Workflow(self.database, name, normalized, self.lease_seconds)
