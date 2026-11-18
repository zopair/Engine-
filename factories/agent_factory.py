from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Callable, Mapping


class AgentExecutionError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AgentSpec:
    agent_id: str
    name: str
    instructions: str
    tool_names: tuple[str, ...]


class Agent:
    """A capability-scoped agent shell; model execution is injected, never hardwired."""

    def __init__(self, spec: AgentSpec, tools: Mapping[str, Callable], executor: Callable | None):
        self.spec = spec
        self._tools = dict(tools)
        self._executor = executor

    def call_tool(self, name: str, **kwargs: Any) -> Any:
        if name not in self.spec.tool_names:
            raise PermissionError(f"Tool '{name}' is not granted to this agent")
        return self._tools[name](**kwargs)

    def run(self, task: str, context: Mapping[str, Any] | None = None) -> Any:
        if not task.strip():
            raise ValueError("task must not be empty")
        if self._executor is None:
            raise AgentExecutionError("No execution provider has been configured")
        return self._executor(
            task=task,
            instructions=self.spec.instructions,
            context=dict(context or {}),
            tools={name: self._tools[name] for name in self.spec.tool_names},
        )


class AgentFactory:
    """Build agents from validated specs and an explicit tool capability registry."""

    def __init__(self, executor: Callable | None = None) -> None:
        self._executor = executor
        self._tools: dict[str, Callable] = {}

    def register_tool(self, name: str, handler: Callable, *, replace: bool = False) -> None:
        name = name.strip()
        if not name or not callable(handler):
            raise ValueError("tool name and callable handler are required")
        if name in self._tools and not replace:
            raise ValueError(f"Tool '{name}' is already registered")
        self._tools[name] = handler

    def create(
        self,
        name: str,
        instructions: str,
        tools: tuple[str, ...] | list[str] = (),
        agent_id: str | None = None,
    ) -> Agent:
        name, instructions = name.strip(), instructions.strip()
        if not name or not instructions:
            raise ValueError("agent name and instructions must not be empty")
        granted = tuple(dict.fromkeys(tools))
        unknown = sorted(set(granted) - self._tools.keys())
        if unknown:
            raise ValueError(f"Unknown tools: {', '.join(unknown)}")
        spec = AgentSpec(agent_id or uuid.uuid4().hex, name, instructions, granted)
        return Agent(spec, {key: self._tools[key] for key in granted}, self._executor)
