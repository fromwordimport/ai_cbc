"""Base agent framework with three-layer prompt architecture.

Three-layer prompt stack:
  1. System instruction (角色定义)
  2. Rule injection (约束规则)
  3. Dynamic examples (动态示例)
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Generic, TypeVar

import structlog

logger = structlog.get_logger("aicbc.agents")


# ---------------------------------------------------------------------------
# Security constants
# ---------------------------------------------------------------------------

_MAX_TASK_CONTEXT_LENGTH = 4000
_MAX_HISTORY_LENGTH = 50

_ROLE_SWITCH_MARKERS = (
    "\n\nsystem:",
    "\n\nassistant:",
    "\n\nuser:",
    "<|im_start|>",
    "<|im_end|>",
    "[INST]",
    "[/INST]",
    "### Instruction",
    "### System",
)

_INSTRUCTION_OVERRIDE_PATTERNS = (
    "忽略以上",
    "ignore previous",
    "forget above",
    "忽略前面",
    "ignore above",
    "forget previous",
    "reset your",
    "new instructions",
    "you are now",
    "system instruction",
    "你现在的角色是",
    "your new role is",
)


# ---------------------------------------------------------------------------
# Prompt layer types
# ---------------------------------------------------------------------------


@dataclass
class SystemInstruction:
    """Layer 1: System-level role definition."""

    role: str
    expertise: list[str]
    constraints: list[str] = field(default_factory=list)

    def render(self) -> str:
        parts = [f"你是{self.role}。"]
        if self.expertise:
            parts.append(f"专业领域：{', '.join(self.expertise)}。")
        if self.constraints:
            parts.append("约束条件：")
            for c in self.constraints:
                parts.append(f"  - {c}")
        return "\n".join(parts)


@dataclass
class RuleInjection:
    """Layer 2: Hard rules and constraints injected into prompts."""

    rules: list[str] = field(default_factory=list)
    forbidden_patterns: list[str] = field(default_factory=list)
    required_fields: list[str] = field(default_factory=list)

    def render(self) -> str:
        parts = []
        if self.rules:
            parts.append("【必须遵守的规则】")
            for i, rule in enumerate(self.rules, 1):
                parts.append(f"RULE-{i:03d}: {rule}")
        if self.forbidden_patterns:
            parts.append("【禁止出现的内容】")
            for p in self.forbidden_patterns:
                parts.append(f"  - {p}")
        if self.required_fields:
            parts.append("【必须包含的字段】")
            for f in self.required_fields:
                parts.append(f"  - {f}")
        return "\n".join(parts)


@dataclass
class DynamicExample:
    """Layer 3: A single dynamic example with input/output pair."""

    input_context: str
    expected_output: str
    rationale: str = ""

    def render(self) -> str:
        parts = [
            "【示例】",
            f"输入：{self.input_context}",
            f"输出：{self.expected_output}",
        ]
        if self.rationale:
            parts.append(f"说明：{self.rationale}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Agent state
# ---------------------------------------------------------------------------


T = TypeVar("T")


@dataclass
class AgentState:
    """Mutable state carried across agent turns."""

    turn_count: int = 0
    correction_count: int = 0
    history: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def record_turn(self, action: str, result: dict[str, Any]) -> None:
        """Record a turn in the agent history."""
        self.turn_count += 1
        self.history.append(
            {
                "turn": self.turn_count,
                "action": action,
                "result": result,
            }
        )
        # SEC-010: Enforce max history length to prevent unbounded growth
        if len(self.history) > _MAX_HISTORY_LENGTH:
            # Keep most recent entries, drop oldest
            self.history = self.history[-_MAX_HISTORY_LENGTH:]

    def record_correction(self, reason: str) -> None:
        """Record a self-correction event."""
        self.correction_count += 1
        self.history.append(
            {
                "turn": self.turn_count,
                "action": "self_correction",
                "reason": reason,
            }
        )
        # SEC-010: Enforce max history length
        if len(self.history) > _MAX_HISTORY_LENGTH:
            self.history = self.history[-_MAX_HISTORY_LENGTH:]


# ---------------------------------------------------------------------------
# Tool definition
# ---------------------------------------------------------------------------


@dataclass
class ToolSpec:
    """Specification for a tool callable by an agent."""

    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)
    required_params: list[str] = field(default_factory=list)
    permission_tags: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Base agent
# ---------------------------------------------------------------------------


class BaseAgent(ABC, Generic[T]):
    """Abstract base for all AI_CBC agents.

    Provides the three-layer prompt architecture and tool-calling
    infrastructure. Subclasses implement ``execute()`` for specific tasks.
    """

    def __init__(
        self,
        system_instruction: SystemInstruction,
        rules: RuleInjection | None = None,
        examples: list[DynamicExample] | None = None,
        max_corrections: int = 3,
        allowed_tool_tags: list[str] | None = None,
    ) -> None:
        self.system = system_instruction
        self.rules = rules or RuleInjection()
        self.examples = examples or []
        self.max_corrections = max_corrections
        self.state = AgentState()
        self._tools: dict[str, callable] = {}
        self._tool_specs: dict[str, ToolSpec] = {}
        self._allowed_tool_tags: set[str] = set(allowed_tool_tags or [])
        self._log = logger.bind(agent=self.__class__.__name__)

    # ------------------------------------------------------------------
    # Input sanitization (SEC-008)
    # ------------------------------------------------------------------

    def _sanitize_task_context(self, task_context: str) -> str:
        """Sanitize user-provided task context to prevent prompt injection.

        Detects role-switching markers and instruction override patterns.
        Raises ValueError if dangerous content is found.
        """
        if not isinstance(task_context, str):
            raise ValueError("task_context must be a string")

        # 1. Length truncation
        if len(task_context) > _MAX_TASK_CONTEXT_LENGTH:
            self._log.warning(
                "task_context_truncated",
                original_length=len(task_context),
                max_length=_MAX_TASK_CONTEXT_LENGTH,
            )
            task_context = task_context[:_MAX_TASK_CONTEXT_LENGTH]

        task_lower = task_context.lower()

        # 2. Detect role-switching markers
        for marker in _ROLE_SWITCH_MARKERS:
            if marker.lower() in task_lower:
                self._log.warning("prompt_injection_detected", marker=marker)
                raise ValueError(
                    f"Task context contains disallowed role marker: '{marker.strip()}'"
                )

        # 3. Detect instruction override patterns
        for pattern in _INSTRUCTION_OVERRIDE_PATTERNS:
            if pattern.lower() in task_lower:
                self._log.warning("prompt_injection_detected", pattern=pattern)
                raise ValueError(
                    f"Task context contains disallowed instruction override: '{pattern}'"
                )

        return task_context

    # ------------------------------------------------------------------
    # Tool registration (SEC-009: permission control)
    # ------------------------------------------------------------------

    def register_tool(self, name: str, fn: callable, spec: ToolSpec | None = None) -> None:
        """Register a callable tool for this agent.

        If allowed_tool_tags is configured, the tool must have at least one
        matching permission tag.
        """
        tool_spec = spec or ToolSpec(name=name, description="")

        # Permission check: if whitelist exists, tool must have a matching tag
        if self._allowed_tool_tags:
            tool_tags = set(tool_spec.permission_tags)
            if not tool_tags.intersection(self._allowed_tool_tags):
                allowed = ", ".join(sorted(self._allowed_tool_tags))
                tool_tags_str = ", ".join(sorted(tool_tags)) if tool_tags else "(none)"
                raise PermissionError(
                    f"Tool '{name}' has tags [{tool_tags_str}] but agent only allows [{allowed}]"
                )

        self._tools[name] = fn
        self._tool_specs[name] = tool_spec
        self._log.debug("tool_registered", name=name, tags=tool_spec.permission_tags)

    def call_tool(self, name: str, **kwargs: Any) -> Any:
        """Invoke a registered tool by name."""
        if name not in self._tools:
            raise KeyError(f"Tool '{name}' not registered")
        self._log.debug("tool_call", name=name, params=list(kwargs.keys()))
        return self._tools[name](**kwargs)

    # ------------------------------------------------------------------
    # Prompt assembly
    # ------------------------------------------------------------------

    def build_prompt(
        self, task_context: str, extra_rules: list[str] | None = None
    ) -> list[dict[str, str]]:
        """Build the full three-layer prompt as OpenAI-style messages.

        Returns a list of message dicts ready for LLMClient.generate().
        """
        # SEC-008: Sanitize task context before building prompt
        safe_task_context = self._sanitize_task_context(task_context)

        # Layer 1: System instruction
        system_content = self.system.render()

        # Layer 2: Rule injection (static + dynamic)
        rules = self.rules
        if extra_rules:
            rules = RuleInjection(
                rules=rules.rules + extra_rules,
                forbidden_patterns=rules.forbidden_patterns,
                required_fields=rules.required_fields,
            )
        rules_content = rules.render()

        # Layer 3: Dynamic examples
        examples_content = "\n\n".join(ex.render() for ex in self.examples)

        # Assemble system message
        parts = [system_content]
        if rules_content:
            parts.append(rules_content)
        if examples_content:
            parts.append(examples_content)

        messages = [
            {"role": "system", "content": "\n\n".join(parts)},
            {"role": "user", "content": safe_task_context},
        ]

        return messages

    # ------------------------------------------------------------------
    # Execution lifecycle
    # ------------------------------------------------------------------

    @abstractmethod
    def execute(self, **kwargs: Any) -> T:
        """Execute the agent's primary task.

        Subclasses implement the core logic here, including any
        self-correction loops.
        """
        ...

    def _should_correct(self, evaluation: dict[str, Any]) -> tuple[bool, str]:
        """Determine if self-correction is needed based on evaluation.

        Returns (needs_correction, reason).
        """
        return False, ""

    def run_with_correction(
        self,
        execute_fn: callable,
        evaluate_fn: callable,
        **kwargs: Any,
    ) -> tuple[T, AgentState]:
        """Run execute + evaluate in a loop until passing or max corrections.

        Args:
            execute_fn: Callable that produces a candidate result.
            evaluate_fn: Callable that evaluates the result and returns a dict.
            **kwargs: Passed to execute_fn.

        Returns:
            Tuple of (final_result, agent_state).
        """
        result = execute_fn(**kwargs)
        evaluation = evaluate_fn(result)
        self.state.record_turn("execute", evaluation)

        while True:
            needs_correction, reason = self._should_correct(evaluation)
            if not needs_correction:
                break
            if self.state.correction_count >= self.max_corrections:
                self._log.warning(
                    "max_corrections_reached",
                    corrections=self.state.correction_count,
                )
                break

            self.state.record_correction(reason)
            self._log.info("self_correction_triggered", reason=reason)

            # Re-execute with feedback injected
            feedback = self._build_correction_feedback(reason, evaluation)
            result = execute_fn(**kwargs, feedback=feedback)
            evaluation = evaluate_fn(result)
            self.state.record_turn("re_execute", evaluation)

        return result, self.state

    def _build_correction_feedback(self, reason: str, evaluation: dict[str, Any]) -> str:
        """Build feedback text to inject on correction."""
        parts = [f"上次生成存在问题：{reason}"]
        if "details" in evaluation:
            parts.append(f"详细反馈：{evaluation['details']}")
        return "\n".join(parts)
