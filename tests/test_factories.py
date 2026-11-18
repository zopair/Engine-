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
