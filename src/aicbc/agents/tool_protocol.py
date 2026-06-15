"""ToolCalling Protocol — standardized tool registration, invocation, and error handling.

This module defines the core protocol infrastructure for AI_CBC agents:
  - ToolRegistry: global and per-agent tool registration with JSON Schema validation
  - ToolCaller: synchronous and asynchronous tool invocation with timeout and retry
  - ToolResult: standardized result wrapper with success/failure semantics
  - ToolError hierarchy: structured exception types for all failure modes

Design follows the specification in:
    - docs/数据字典.md (data exchange formats)
    - consumer-simulation/07-Harness架构设计方案.md (agent harness)

Data flow:
    PersonaProfile → CBCRawDataset → AnalysisResult
    (consumer-sim)   (questionnaire)   (analysis)
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, TypeVar

import structlog

logger = structlog.get_logger("aicbc.agents.tool_protocol")


# ---------------------------------------------------------------------------
# Tool result types
# ---------------------------------------------------------------------------


class ToolStatus(str, Enum):
    """Execution status of a tool call."""

    SUCCESS = "success"
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"
    TIMEOUT = "timeout"
    EXECUTION_ERROR = "execution_error"
    RETRY_EXHAUSTED = "retry_exhausted"


@dataclass
class ToolResult:
    """Standardized wrapper for all tool call outcomes.

    Attributes:
        status: Execution status (success or specific failure type).
        data: The actual return value on success; None on failure.
        error: Error message or structured error info on failure.
        duration_ms: Wall-clock time of the call in milliseconds.
        tool_name: Name of the invoked tool.
        call_id: Unique identifier for this call.
        metadata: Additional context (retry count, chain info, etc.).
    """

    status: ToolStatus
    data: Any = None
    error: str | None = None
    duration_ms: float = 0.0
    tool_name: str = ""
    call_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def is_success(self) -> bool:
        return self.status == ToolStatus.SUCCESS

    @property
    def is_failure(self) -> bool:
        return not self.is_success

    def unwrap(self) -> Any:
        """Return data on success, raise RuntimeError on failure."""
        if self.is_failure:
            raise RuntimeError(
                f"Tool '{self.tool_name}' failed with {self.status.value}: {self.error}"
            )
        return self.data

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "data": self.data,
            "error": self.error,
            "duration_ms": self.duration_ms,
            "tool_name": self.tool_name,
            "call_id": self.call_id,
            "metadata": self.metadata,
        }


# ---------------------------------------------------------------------------
# Tool specification
# ---------------------------------------------------------------------------


@dataclass
class ToolParameter:
    """Schema for a single tool parameter."""

    name: str
    param_type: str  # "str", "int", "float", "bool", "list", "dict", "any"
    description: str = ""
    required: bool = True
    default: Any = None

    def validate(self, value: Any) -> tuple[bool, str]:
        """Validate a value against this parameter schema."""
        if value is None and self.required and self.default is None:
            return False, f"Required parameter '{self.name}' is missing"

        type_map = {
            "str": str,
            "int": int,
            "float": (int, float),
            "bool": bool,
            "list": list,
            "dict": dict,
            "any": object,
        }

        expected = type_map.get(self.param_type)
        if expected is None:
            return True, ""  # Unknown type, skip validation

        if value is not None and not isinstance(value, expected):
            return False, (
                f"Parameter '{self.name}' expected {self.param_type}, "
                f"got {type(value).__name__}"
            )

        return True, ""


@dataclass
class ToolSpec:
    """Complete specification for a callable tool.

    Replaces the simple ToolSpec in base.py with full parameter schema support.
    """

    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    return_type: str = "any"
    timeout_seconds: float = 30.0
    max_retries: int = 0
    tags: list[str] = field(default_factory=list)

    def validate_args(self, kwargs: dict[str, Any]) -> tuple[bool, str]:
        """Validate all arguments against the parameter schema."""
        # Check for unknown parameters
        known = {p.name for p in self.parameters}
        unknown = set(kwargs.keys()) - known
        if unknown:
            return False, f"Unknown parameters: {', '.join(unknown)}"

        # Validate each parameter
        for param in self.parameters:
            value = kwargs.get(param.name, param.default)
            if value is None and param.name not in kwargs and param.default is not None:
                value = param.default
            ok, msg = param.validate(value)
            if not ok:
                return False, msg

        # Check required parameters
        for param in self.parameters:
            if param.required and param.name not in kwargs and param.default is None:
                return False, f"Required parameter '{param.name}' is missing"

        return True, ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": [
                {
                    "name": p.name,
                    "type": p.param_type,
                    "description": p.description,
                    "required": p.required,
                    "default": p.default,
                }
                for p in self.parameters
            ],
            "return_type": self.return_type,
            "timeout_seconds": self.timeout_seconds,
            "max_retries": self.max_retries,
            "tags": self.tags,
        }

    @classmethod
    def from_callable(
        cls,
        fn: Callable,
        name: str | None = None,
        description: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 0,
        tags: list[str] | None = None,
    ) -> ToolSpec:
        """Infer ToolSpec from a callable's signature."""
        sig = inspect.signature(fn)
        params: list[ToolParameter] = []

        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue

            param_type = "any"
            if param.annotation != inspect.Parameter.empty:
                ann = param.annotation
                if ann in (str,):
                    param_type = "str"
                elif ann in (int,):
                    param_type = "int"
                elif ann in (float,):
                    param_type = "float"
                elif ann in (bool,):
                    param_type = "bool"
                elif ann in (list,):
                    param_type = "list"
                elif ann in (dict,):
                    param_type = "dict"

            required = param.default == inspect.Parameter.empty
            default = None if required else param.default

            params.append(
                ToolParameter(
                    name=param_name,
                    param_type=param_type,
                    description="",
                    required=required,
                    default=default,
                )
            )

        return_cls = sig.return_annotation
        return_type = "any"
        if return_cls != inspect.Signature.empty and return_cls != inspect.Parameter.empty:
            if return_cls in (str, int, float, bool, list, dict):
                return_type = return_cls.__name__

        return cls(
            name=name or fn.__name__,
            description=description or (fn.__doc__ or "").strip().split("\n")[0],
            parameters=params,
            return_type=return_type,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            tags=tags or [],
        )


# ---------------------------------------------------------------------------
# Tool registry
# ---------------------------------------------------------------------------


class ToolRegistry:
    """Central registry for tool specifications and implementations.

    Supports both global (singleton) and per-agent (isolated) registries.
    Thread-safe for read operations; write operations should be done at init.
    """

    _global_instance: ToolRegistry | None = None

    def __init__(self, name: str = "default") -> None:
        self.name = name
        self._tools: dict[str, Callable] = {}
        self._specs: dict[str, ToolSpec] = {}
        self._log = logger.bind(registry=name)

    @classmethod
    def global_registry(cls) -> ToolRegistry:
        """Get the singleton global registry."""
        if cls._global_instance is None:
            cls._global_instance = cls(name="global")
        return cls._global_instance

    @classmethod
    def reset_global(cls) -> None:
        """Reset the global registry (mainly for testing)."""
        cls._global_instance = None

    def register(
        self,
        spec: ToolSpec,
        fn: Callable,
        override: bool = False,
    ) -> None:
        """Register a tool with its specification.

        Args:
            spec: Tool specification (schema, timeout, etc.).
            fn: The callable implementation.
            override: If True, allow replacing an existing tool.

        Raises:
            ValueError: If tool already registered and override=False.
        """
        if spec.name in self._tools and not override:
            raise ValueError(f"Tool '{spec.name}' already registered. Use override=True to replace.")

        self._tools[spec.name] = fn
        self._specs[spec.name] = spec
        self._log.debug("tool_registered", name=spec.name, tags=spec.tags)

    def register_from_callable(
        self,
        fn: Callable,
        name: str | None = None,
        description: str | None = None,
        timeout_seconds: float = 30.0,
        max_retries: int = 0,
        tags: list[str] | None = None,
        override: bool = False,
    ) -> ToolSpec:
        """Register a tool by inferring its spec from the callable signature."""
        spec = ToolSpec.from_callable(
            fn,
            name=name,
            description=description,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            tags=tags,
        )
        self.register(spec, fn, override=override)
        return spec

    def unregister(self, name: str) -> bool:
        """Remove a tool from the registry. Returns True if found and removed."""
        if name in self._tools:
            del self._tools[name]
            del self._specs[name]
            self._log.debug("tool_unregistered", name=name)
            return True
        return False

    def get(self, name: str) -> Callable | None:
        """Get the implementation for a tool."""
        return self._tools.get(name)

    def get_spec(self, name: str) -> ToolSpec | None:
        """Get the specification for a tool."""
        return self._specs.get(name)

    def has_tool(self, name: str) -> bool:
        """Check if a tool is registered."""
        return name in self._tools

    def list_tools(self, tag: str | None = None) -> list[str]:
        """List all registered tool names, optionally filtered by tag."""
        if tag is None:
            return list(self._tools.keys())
        return [
            name for name, spec in self._specs.items()
            if tag in spec.tags
        ]

    def list_specs(self) -> list[ToolSpec]:
        """Return all tool specifications."""
        return list(self._specs.values())

    def discover(self, prefix: str = "") -> list[str]:
        """Discover tools by name prefix."""
        return [name for name in self._tools if name.startswith(prefix)]

    def to_openai_schema(self) -> list[dict[str, Any]]:
        """Export all tools as OpenAI function-calling schema."""
        schemas = []
        for spec in self._specs.values():
            schema = {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": {
                        "type": "object",
                        "properties": {
                            p.name: {
                                "type": p.param_type,
                                "description": p.description,
                            }
                            for p in spec.parameters
                        },
                        "required": [p.name for p in spec.parameters if p.required],
                    },
                },
            }
            schemas.append(schema)
        return schemas


# ---------------------------------------------------------------------------
# Tool caller with timeout and retry
# ---------------------------------------------------------------------------


@dataclass
class ToolCallRecord:
    """Record of a single tool invocation for tracing and auditing."""

    call_id: str
    tool_name: str
    arguments: dict[str, Any]
    result: ToolResult | None = None
    timestamp: float = field(default_factory=time.time)
    parent_call_id: str | None = None


class ToolCaller:
    """Execute tool calls with validation, timeout, retry, and tracing.

    Usage:
        caller = ToolCaller(registry)
        result = caller.call("fit_hb_model", data=df, feature_cols=["price", "brand_0"])

        # Async
        result = await caller.acall("fit_hb_model", data=df, feature_cols=[...])
    """

    def __init__(
        self,
        registry: ToolRegistry | None = None,
        default_timeout: float = 30.0,
        default_retries: int = 0,
        enable_tracing: bool = True,
    ) -> None:
        self.registry = registry or ToolRegistry.global_registry()
        self.default_timeout = default_timeout
        self.default_retries = default_retries
        self.enable_tracing = enable_tracing
        self._call_history: list[ToolCallRecord] = []
        self._log = logger.bind(caller="ToolCaller")

    # ------------------------------------------------------------------
    # Synchronous call
    # ------------------------------------------------------------------

    def call(self, tool_name: str, **kwargs: Any) -> ToolResult:
        """Invoke a tool synchronously with full error handling."""
        call_id = f"tc-{uuid.uuid4().hex[:8]}"
        record = ToolCallRecord(
            call_id=call_id,
            tool_name=tool_name,
            arguments=kwargs,
        )

        # 1. Check tool exists
        spec = self.registry.get_spec(tool_name)
        fn = self.registry.get(tool_name)
        if spec is None or fn is None:
            result = ToolResult(
                status=ToolStatus.NOT_FOUND,
                error=f"Tool '{tool_name}' not found in registry",
                tool_name=tool_name,
                call_id=call_id,
            )
            record.result = result
            self._record_call(record)
            return result

        # 2. Validate arguments
        ok, msg = spec.validate_args(kwargs)
        if not ok:
            result = ToolResult(
                status=ToolStatus.VALIDATION_ERROR,
                error=msg,
                tool_name=tool_name,
                call_id=call_id,
            )
            record.result = result
            self._record_call(record)
            return result

        # 3. Execute with timeout and retry
        timeout = spec.timeout_seconds or self.default_timeout
        max_retries = spec.max_retries or self.default_retries

        result = self._execute_with_retry(
            fn, kwargs, spec, call_id, timeout, max_retries
        )
        record.result = result
        self._record_call(record)
        return result

    def _execute_with_retry(
        self,
        fn: Callable,
        kwargs: dict[str, Any],
        spec: ToolSpec,
        call_id: str,
        timeout: float,
        max_retries: int,
    ) -> ToolResult:
        """Execute with timeout and retry logic."""
        last_error: Exception | None = None
        retry_count = 0

        for attempt in range(max_retries + 1):
            start = time.perf_counter()
            try:
                # Run with timeout using ThreadPoolExecutor
                if asyncio.iscoroutinefunction(fn):
                    # Async function in sync context — run via asyncio.run
                    data = asyncio.run(self._run_async_with_timeout(fn, kwargs, timeout))
                else:
                    data = self._run_sync_with_timeout(fn, kwargs, timeout)

                duration_ms = (time.perf_counter() - start) * 1000
                return ToolResult(
                    status=ToolStatus.SUCCESS,
                    data=data,
                    duration_ms=duration_ms,
                    tool_name=spec.name,
                    call_id=call_id,
                    metadata={"retry_count": retry_count},
                )

            except FutureTimeoutError:
                duration_ms = (time.perf_counter() - start) * 1000
                retry_count += 1
                last_error = FutureTimeoutError(f"Timeout after {timeout}s")
                self._log.warning(
                    "tool_timeout",
                    tool=spec.name,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    timeout=timeout,
                )
                if attempt < max_retries:
                    # Exponential backoff: 2^attempt seconds
                    time.sleep(min(2 ** attempt, 10))

            except Exception as exc:
                duration_ms = (time.perf_counter() - start) * 1000
                retry_count += 1
                last_error = exc
                self._log.warning(
                    "tool_execution_error",
                    tool=spec.name,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(exc),
                )
                if attempt < max_retries:
                    time.sleep(min(2 ** attempt, 10))

        # All retries exhausted
        status = (
            ToolStatus.TIMEOUT
            if isinstance(last_error, FutureTimeoutError)
            else ToolStatus.RETRY_EXHAUSTED
        )
        return ToolResult(
            status=status,
            error=f"{last_error} (after {max_retries + 1} attempts)",
            duration_ms=(time.perf_counter() - start) * 1000,
            tool_name=spec.name,
            call_id=call_id,
            metadata={"retry_count": retry_count},
        )

    def _run_sync_with_timeout(
        self,
        fn: Callable,
        kwargs: dict[str, Any],
        timeout: float,
    ) -> Any:
        """Run a synchronous function with timeout."""
        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(fn, **kwargs)
            return future.result(timeout=timeout)

    async def _run_async_with_timeout(
        self,
        fn: Callable,
        kwargs: dict[str, Any],
        timeout: float,
    ) -> Any:
        """Run an async function with timeout."""
        return await asyncio.wait_for(fn(**kwargs), timeout=timeout)

    # ------------------------------------------------------------------
    # Asynchronous call
    # ------------------------------------------------------------------

    async def acall(self, tool_name: str, **kwargs: Any) -> ToolResult:
        """Invoke a tool asynchronously with full error handling."""
        call_id = f"tc-{uuid.uuid4().hex[:8]}"
        record = ToolCallRecord(
            call_id=call_id,
            tool_name=tool_name,
            arguments=kwargs,
        )

        # 1. Check tool exists
        spec = self.registry.get_spec(tool_name)
        fn = self.registry.get(tool_name)
        if spec is None or fn is None:
            result = ToolResult(
                status=ToolStatus.NOT_FOUND,
                error=f"Tool '{tool_name}' not found in registry",
                tool_name=tool_name,
                call_id=call_id,
            )
            record.result = result
            self._record_call(record)
            return result

        # 2. Validate arguments
        ok, msg = spec.validate_args(kwargs)
        if not ok:
            result = ToolResult(
                status=ToolStatus.VALIDATION_ERROR,
                error=msg,
                tool_name=tool_name,
                call_id=call_id,
            )
            record.result = result
            self._record_call(record)
            return result

        # 3. Execute with timeout and retry
        timeout = spec.timeout_seconds or self.default_timeout
        max_retries = spec.max_retries or self.default_retries

        result = await self._aexecute_with_retry(
            fn, kwargs, spec, call_id, timeout, max_retries
        )
        record.result = result
        self._record_call(record)
        return result

    async def _aexecute_with_retry(
        self,
        fn: Callable,
        kwargs: dict[str, Any],
        spec: ToolSpec,
        call_id: str,
        timeout: float,
        max_retries: int,
    ) -> ToolResult:
        """Async execution with timeout and retry."""
        last_error: Exception | None = None
        retry_count = 0

        for attempt in range(max_retries + 1):
            start = time.perf_counter()
            try:
                if asyncio.iscoroutinefunction(fn):
                    data = await asyncio.wait_for(fn(**kwargs), timeout=timeout)
                else:
                    # Run sync function in thread pool
                    loop = asyncio.get_event_loop()
                    with ThreadPoolExecutor(max_workers=1) as executor:
                        future = loop.run_in_executor(executor, functools.partial(fn, **kwargs))
                        data = await asyncio.wait_for(future, timeout=timeout)

                duration_ms = (time.perf_counter() - start) * 1000
                return ToolResult(
                    status=ToolStatus.SUCCESS,
                    data=data,
                    duration_ms=duration_ms,
                    tool_name=spec.name,
                    call_id=call_id,
                    metadata={"retry_count": retry_count},
                )

            except asyncio.TimeoutError:
                duration_ms = (time.perf_counter() - start) * 1000
                retry_count += 1
                last_error = asyncio.TimeoutError(f"Timeout after {timeout}s")
                self._log.warning(
                    "tool_timeout_async",
                    tool=spec.name,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                )
                if attempt < max_retries:
                    await asyncio.sleep(min(2 ** attempt, 10))

            except Exception as exc:
                duration_ms = (time.perf_counter() - start) * 1000
                retry_count += 1
                last_error = exc
                self._log.warning(
                    "tool_execution_error_async",
                    tool=spec.name,
                    attempt=attempt + 1,
                    max_retries=max_retries,
                    error=str(exc),
                )
                if attempt < max_retries:
                    await asyncio.sleep(min(2 ** attempt, 10))

        status = (
            ToolStatus.TIMEOUT
            if isinstance(last_error, asyncio.TimeoutError)
            else ToolStatus.RETRY_EXHAUSTED
        )
        return ToolResult(
            status=status,
            error=f"{last_error} (after {max_retries + 1} attempts)",
            duration_ms=(time.perf_counter() - start) * 1000,
            tool_name=spec.name,
            call_id=call_id,
            metadata={"retry_count": retry_count},
        )

    # ------------------------------------------------------------------
    # Tracing
    # ------------------------------------------------------------------

    def _record_call(self, record: ToolCallRecord) -> None:
        if self.enable_tracing:
            self._call_history.append(record)
            self._log.debug(
                "tool_call_recorded",
                call_id=record.call_id,
                tool=record.tool_name,
                status=record.result.status.value if record.result else "pending",
            )

    def get_call_history(self) -> list[ToolCallRecord]:
        """Return all recorded tool calls."""
        return list(self._call_history)

    def get_call_history_for_tool(self, tool_name: str) -> list[ToolCallRecord]:
        """Return calls for a specific tool."""
        return [r for r in self._call_history if r.tool_name == tool_name]

    def clear_history(self) -> None:
        """Clear the call history."""
        self._call_history.clear()

    def get_stats(self) -> dict[str, Any]:
        """Return call statistics."""
        if not self._call_history:
            return {"total_calls": 0}

        total = len(self._call_history)
        successes = sum(1 for r in self._call_history if r.result and r.result.is_success)
        failures = total - successes
        avg_duration = (
            sum(r.result.duration_ms for r in self._call_history if r.result) / total
        )

        by_tool: dict[str, dict[str, int]] = {}
        for r in self._call_history:
            if r.tool_name not in by_tool:
                by_tool[r.tool_name] = {"calls": 0, "successes": 0, "failures": 0}
            by_tool[r.tool_name]["calls"] += 1
            if r.result and r.result.is_success:
                by_tool[r.tool_name]["successes"] += 1
            else:
                by_tool[r.tool_name]["failures"] += 1

        return {
            "total_calls": total,
            "successes": successes,
            "failures": failures,
            "success_rate": successes / total if total > 0 else 0.0,
            "avg_duration_ms": avg_duration,
            "by_tool": by_tool,
        }


# ---------------------------------------------------------------------------
# Decorator for easy tool registration
# ---------------------------------------------------------------------------


def tool(
    name: str | None = None,
    description: str | None = None,
    timeout_seconds: float = 30.0,
    max_retries: int = 0,
    tags: list[str] | None = None,
    registry: ToolRegistry | None = None,
) -> Callable:
    """Decorator to register a function as a tool.

    Usage:
        @tool(tags=["analysis"])
        def fit_model(data: pd.DataFrame, feature_cols: list[str]) -> dict:
            ...
    """
    def decorator(fn: Callable) -> Callable:
        reg = registry or ToolRegistry.global_registry()
        spec = ToolSpec.from_callable(
            fn,
            name=name or fn.__name__,
            description=description,
            timeout_seconds=timeout_seconds,
            max_retries=max_retries,
            tags=tags or [],
        )
        reg.register(spec, fn)
        fn._tool_spec = spec  # type: ignore
        return fn
    return decorator


# ---------------------------------------------------------------------------
# Convenience: tool chain / pipeline
# ---------------------------------------------------------------------------


@dataclass
class ToolChain:
    """Chain multiple tool calls with data passing between steps.

    Usage:
        chain = ToolChain(caller)
        chain.add("preprocess", dataset=dataset, attributes=attrs)
        chain.add("fit_model", data="$preprocess.data", model_type="hb")
        result = chain.execute()
    """

    caller: ToolCaller
    steps: list[tuple[str, dict[str, Any]]] = field(default_factory=list)
    step_names: list[str] = field(default_factory=list)
    results: dict[str, ToolResult] = field(default_factory=dict)

    def add(self, tool_name: str, step_name: str | None = None, **kwargs: Any) -> ToolChain:
        """Add a step to the chain. Use '$step_name.field' for data references."""
        name = step_name or f"step_{len(self.steps)}"
        self.steps.append((tool_name, kwargs))
        self.step_names.append(name)
        return self

    def execute(self, stop_on_error: bool = True) -> dict[str, ToolResult]:
        """Execute all steps in order, resolving data references."""
        for i, (tool_name, kwargs) in enumerate(self.steps):
            step_name = self.step_names[i]

            # Resolve references like "$step_name.data"
            resolved = self._resolve_refs(kwargs)

            result = self.caller.call(tool_name, **resolved)
            self.results[step_name] = result

            if result.is_failure and stop_on_error:
                self.caller._log.error(
                    "chain_stopped",
                    step=step_name,
                    tool=tool_name,
                    error=result.error,
                )
                break

        return self.results

    def _resolve_refs(self, kwargs: dict[str, Any]) -> dict[str, Any]:
        """Resolve data references of form '$step_name.data' or '$step_name.data.key'."""
        resolved: dict[str, Any] = {}
        for key, value in kwargs.items():
            if isinstance(value, str) and value.startswith("$"):
                ref_path = value[1:].split(".")
                step_name = ref_path[0]
                if step_name not in self.results:
                    raise ValueError(f"Reference to unknown step '{step_name}'")
                result = self.results[step_name]
                if result.is_failure:
                    raise ValueError(f"Cannot reference failed step '{step_name}'")

                # Navigate the data
                data = result.data
                for attr in ref_path[1:]:
                    if isinstance(data, dict):
                        data = data[attr]
                    elif hasattr(data, attr):
                        data = getattr(data, attr)
                    else:
                        raise ValueError(f"Cannot resolve '{value}': {attr} not found")
                resolved[key] = data
            else:
                resolved[key] = value
        return resolved
