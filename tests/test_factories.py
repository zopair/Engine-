from pathlib import Path

import pytest

from factories.agent_factory import AgentFactory
from factories.workflow_factory import WorkflowExecutionError, WorkflowFactory, WorkflowStep
from memory.database import Database


def test_agent_factory_binds_only_declared_tools_and_executes():
    factory = AgentFactory(
        executor=lambda task, instructions, context, tools: {
            "task": task,
            "instructions": instructions,
            "tool_names": sorted(tools),
            "context": context,
        }
    )
    factory.register_tool("add", lambda left, right: left + right)
    agent = factory.create(
        name="calculator",
        instructions="Use tools for arithmetic.",
        tools=("add",),
    )

    assert agent.call_tool("add", left=2, right=3) == 5
    result = agent.run("2 + 3", context={"request_id": "r-1"})
    assert result["task"] == "2 + 3"
    assert result["tool_names"] == ["add"]
    assert result["context"]["request_id"] == "r-1"


def test_agent_factory_rejects_unregistered_tools():
    factory = AgentFactory()
    with pytest.raises(ValueError, match="Unknown tools"):
        factory.create(name="bad-agent", instructions="test", tools=("missing",))


def test_workflow_resume_skips_completed_steps_and_restores_checkpoint(tmp_path: Path):
    database_path = tmp_path / "workflow.db"
    database = Database(str(database_path))
    attempts = {"second": 0}

    def first(payload, state):
        return {"value": payload["value"] + 1}

    def second(payload, state):
        attempts["second"] += 1
        if attempts["second"] == 1:
            raise RuntimeError("temporary failure")
        return {"value": state["first"]["value"] * 2}

    def third(payload, state):
        return {"final": state["second"]["value"] + 1}

    steps = [
        WorkflowStep("first", first),
        WorkflowStep("second", second),
        WorkflowStep("third", third),
    ]
    workflow = WorkflowFactory(database).create("resumable-pipeline", steps)

    with pytest.raises(WorkflowExecutionError) as failure:
        workflow.run({"value": 4}, run_id="run-001")
    assert failure.value.run_id == "run-001"

    resumed = WorkflowFactory(Database(str(database_path))).create(
        "resumable-pipeline", steps
    ).resume("run-001")

    assert resumed.status == "completed"
    assert resumed.outputs["first"] == {"value": 5}
    assert resumed.outputs["second"] == {"value": 10}
    assert resumed.outputs["third"] == {"final": 11}
    assert attempts["second"] == 2


def test_workflow_rejects_duplicate_step_names(tmp_path: Path):
    workflow_factory = WorkflowFactory(Database(str(tmp_path / "workflow.db")))
    with pytest.raises(ValueError, match="unique"):
        workflow_factory.create(
            "invalid",
            [WorkflowStep("same", lambda payload, state: None),
             WorkflowStep("same", lambda payload, state: None)],
        )


def test_agent_rejects_ungranted_tool_and_missing_executor():
    factory = AgentFactory()
    factory.register_tool("private", lambda: "secret")
    agent = factory.create("restricted", "No tools.", tools=())
    with pytest.raises(PermissionError, match="not granted"):
        agent.call_tool("private")
    with pytest.raises(Exception, match="all inference providers failed"):
        agent.run("do work")


def test_agent_factory_rejects_duplicate_registration():
    factory = AgentFactory()
    factory.register_tool("lookup", lambda: 1)
    with pytest.raises(ValueError, match="already registered"):
        factory.register_tool("lookup", lambda: 2)


def test_workflow_completed_run_is_idempotent(tmp_path: Path):
    calls = {"count": 0}

    def step(payload, state):
        calls["count"] += 1
        return {"done": payload["value"]}

    workflow = WorkflowFactory(Database(str(tmp_path / "idempotent.db"))).create(
        "idempotent", [WorkflowStep("finish", step)]
    )
    first = workflow.run({"value": "ok"}, run_id="same-run")
    second = workflow.resume("same-run")

    assert first == second
    assert calls["count"] == 1


def test_workflow_rejects_non_json_state_before_creating_run(tmp_path: Path):
    workflow = WorkflowFactory(Database(str(tmp_path / "json.db"))).create(
        "json-only", [WorkflowStep("finish", lambda payload, state: None)]
    )
    with pytest.raises(ValueError, match="JSON serializable"):
        workflow.run({"not_json": object()}, run_id="invalid-json")
    with workflow.database.connect() as connection:
        assert connection.execute(
            "SELECT 1 FROM workflow_runs WHERE run_id='invalid-json'"
        ).fetchone() is None


def test_workflow_factory_rejects_empty_and_oversized_definitions(tmp_path: Path):
    factory = WorkflowFactory(Database(str(tmp_path / "limits.db")))
    with pytest.raises(ValueError, match="at least one step"):
        factory.create("empty", [])
    steps = [WorkflowStep(f"step-{index}", lambda payload, state: None) for index in range(101)]
    with pytest.raises(ValueError, match="100 steps"):
        factory.create("too-large", steps)


def test_agent_factory_executes_only_explicitly_granted_model_tool_calls():
    class SequenceOrchestrator:
        def __init__(self):
            self.responses = [
                '{"tool_calls":[{"name":"lookup","arguments":{"key":"alpha"}}]}',
                "Resolved value is 42.",
            ]
        def complete(self, prompt):
            return self.responses.pop(0)

    factory = AgentFactory(orchestrator=SequenceOrchestrator())
    factory.register_tool("lookup", lambda key: {"key": key, "value": 42})
    agent = factory.create("researcher", "Use lookup when needed.", tools=("lookup",))
    assert agent.run("Find alpha") == "Resolved value is 42."
