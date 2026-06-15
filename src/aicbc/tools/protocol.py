"""Tool calling protocol — core implementation.

Defines the ToolCalling protocol for AI_CBC agents:
  1. Tool registration (with JSON-schema specs)
  2. Tool invocation (with structured request/response)
  3. Error handling (typed exceptions, retry policy)
  4. Timeout management (deadline propagation)

Data flow contracts:
  PersonaProfile  →  CBCRawDataset  →  AnalysisResult
  (画像生成)        →  (问卷模拟)       →  (统计分析)
"""

from __future__ import annotations

import asyncio
import functools
import inspect
import json
import time
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Callable, Coroutine

import structlog

logger = structlog.get_logger("aicbc.tools")


# ---------------------------------------------------------------------------
# Tool specification
# ---------------------------------------------------------------------------


@dataclass
class ToolParameter:
    """Schema for a single tool parameter."""

    name: str
    type: str
    description: str = ""
    required: bool = True
    default: Any = None
    enum: list[Any] | None = None

    def to_schema(self) -> dict[str, Any]:
        """Convert to JSON Schema property dict."""
        schema: dict[str, Any] = {"type": self.type, "description": self.description}
        if self.enum is not None:
            schema["enum"] = self.enum
        if self.default is not None and not self.required:
            schema["default"] = self.default
        return schema


@dataclass
class ToolSpec:
    """Specification for a tool callable by an agent.

    Extends the base ``ToolSpec`` in ``agents/base.py`` with full
    JSON-Schema parameter definitions and runtime metadata.
    """

    name: str
    description: str
    parameters: list[ToolParameter] = field(default_factory=list)
    returns: dict[str, Any] = field(default_factory=dict)
    timeout_seconds: float = 30.0
    max_retries: int = 2
    retryable_errors: tuple[type[Exception], ...] = (ConnectionError, TimeoutError)

    def to_openai_schema(self) -> dict[str, Any]:
        """Render as OpenAI function-calling schema."""
        required = [p.name for p in self.parameters if p.required]
        properties = {p.name: p.to_schema() for p in self.parameters}
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }


# ---------------------------------------------------------------------------
# Request / Response
# ---------------------------------------------------------------------------


class ToolCallStatus(StrEnum):
    """Status of a tool call execution."""

    SUCCESS = "success"
    ERROR = "error"
    TIMEOUT = "timeout"
    VALIDATION_ERROR = "validation_error"
    NOT_FOUND = "not_found"


@dataclass
class ToolCallRequest:
    """Structured request to invoke a tool."""

    tool_name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    request_id: str = ""
    timeout_seconds: float | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolCallResult:
    """Structured result of a tool invocation."""

    status: ToolCallStatus
    data: Any = None
    error: str = ""
    error_code: str = ""
    duration_seconds: float = 0.0
    request_id: str = ""
    retry_count: int = 0

    @property
    def is_success(self) -> bool:
        return self.status == ToolCallStatus.SUCCESS

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "data": self.data,
            "error": self.error,
            "error_code": self.error_code,
            "duration_seconds": self.duration_seconds,
            "request_id": self.request_id,
            "retry_count": self.retry_count,
        }


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ToolCallError(Exception):
    """Base exception for tool call failures."""

    def __init__(self, message: str, error_code: str = "TOOL_ERROR", detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.error_code = error_code
        self.detail = detail or {}


class ToolValidationError(ToolCallError):
    """Raised when tool arguments fail validation."""

    def __init__(self, message: str, param_name: str = "", detail: dict[str, Any] | None = None):
        super().__init__(message, error_code="VALIDATION_ERROR", detail=detail)
        self.param_name = param_name


class ToolTimeoutError(ToolCallError):
    """Raised when a tool call exceeds its deadline."""

    def __init__(self, message: str, timeout_seconds: float = 0.0):
        super().__init__(message, error_code="TIMEOUT")
        self.timeout_seconds = timeout_seconds


class ToolNotFoundError(ToolCallError):
    """Raised when the requested tool is not registered."""

    def __init__(self, tool_name: str):
        super().__init__(f"Tool '{tool_name}' not found", error_code="NOT_FOUND")
        self.tool_name = tool_name


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_arguments(spec: ToolSpec, arguments: dict[str, Any]) -> dict[str, Any]:
    """Validate and coalesce arguments against a ToolSpec.

    Returns the validated (and default-populated) argument dict.
    Raises ToolValidationError on failure.
    """
    validated: dict[str, Any] = {}
    param_map = {p.name: p for p in spec.parameters}

    # Check for unknown parameters
    for key in arguments:
        if key not in param_map:
            raise ToolValidationError(
                f"Unknown parameter '{key}' for tool '{spec.name}'",
                param_name=key,
            )

    # Check required and apply defaults
    for p in spec.parameters:
        if p.name in arguments:
            validated[p.name] = arguments[p.name]
        elif p.required:
            raise ToolValidationError(
                f"Missing required parameter '{p.name}' for tool '{spec.name}'",
                param_name=p.name,
            )
        else:
            validated[p.name] = p.default

    return validated


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass
class _RegisteredTool:
    """Internal wrapper holding a tool callable + its spec."""

    fn: Callable[..., Any]
    spec: ToolSpec
    is_async: bool = False


class ToolRegistry:
    """Central registry for agent-callable tools.

    Thread-safe (via GIL) and asyncio-compatible.  Usage::

        registry = ToolRegistry()
        registry.register(my_tool, spec=ToolSpec(...))
        result = registry.call("my_tool", {"arg": 1})
    """

    def __init__(self) -> None:
        self._tools: dict[str, _RegisteredTool] = {}
        self._log = logger.bind(registry_id=id(self))

    # -- Registration -------------------------------------------------------

    def register(
        self,
        fn: Callable[..., Any],
        spec: ToolSpec | None = None,
        name: str | None = None,
    ) -> ToolSpec:
        """Register a callable as a tool.

        If *spec* is omitted, one is auto-derived from the function
        signature (best-effort).
        """
        tool_name = name or fn.__name__
        is_async = asyncio.iscoroutinefunction(fn)

        if spec is None:
            spec = _derive_spec_from_signature(fn, tool_name)

        self._tools[tool_name] = _RegisteredTool(fn=fn, spec=spec, is_async=is_async)
        self._log.debug("tool_registered", name=tool_name, is_async=is_async)
        return spec

    def unregister(self, name: str) -> bool:
        """Remove a tool from the registry.  Returns True if it existed."""
        if name in self._tools:
            del self._tools[name]
            self._log.debug("tool_unregistered", name=name)
            return True
        return False

    def get_spec(self, name: str) -> ToolSpec:
        """Return the spec for a registered tool."""
        if name not in self._tools:
            raise ToolNotFoundError(name)
        return self._tools[name].spec

    def list_tools(self) -> list[ToolSpec]:
        """Return specs for all registered tools."""
        return [rt.spec for rt in self._tools.values()]

    def to_openai_schemas(self) -> list[dict[str, Any]]:
        """Return all tool specs as OpenAI function schemas."""
        return [rt.spec.to_openai_schema() for rt in self._tools.values()]

    # -- Invocation ---------------------------------------------------------

    def call(self, request: ToolCallRequest) -> ToolCallResult:
        """Execute a tool call synchronously.

        For async tools, this runs them in a new event loop — suitable
        for sync contexts only.  Prefer ``acall`` in async code.
        """
        if request.tool_name not in self._tools:
            return ToolCallResult(
                status=ToolCallStatus.NOT_FOUND,
                error=f"Tool '{request.tool_name}' not registered",
                error_code="NOT_FOUND",
                request_id=request.request_id,
            )

        rt = self._tools[request.tool_name]
        timeout = request.timeout_seconds or rt.spec.timeout_seconds

        # Validate arguments
        try:
            validated_args = _validate_arguments(rt.spec, request.arguments)
        except ToolValidationError as exc:
            return ToolCallResult(
                status=ToolCallStatus.VALIDATION_ERROR,
                error=str(exc),
                error_code=exc.error_code,
                request_id=request.request_id,
            )

        # Execute with timeout and retry
        start = time.perf_counter()
        retry_count = 0
        last_error: Exception | None = None

        while retry_count <= rt.spec.max_retries:
            try:
                if rt.is_async:
                    result_data = asyncio.run(
                        _run_with_timeout(rt.fn, validated_args, timeout)
                    )
                else:
                    result_data = _run_sync_with_timeout(rt.fn, validated_args, timeout)

                duration = time.perf_counter() - start
                return ToolCallResult(
                    status=ToolCallStatus.SUCCESS,
                    data=result_data,
                    duration_seconds=duration,
                    request_id=request.request_id,
                    retry_count=retry_count,
                )

            except ToolTimeoutError as exc:
                duration = time.perf_counter() - start
                return ToolCallResult(
                    status=ToolCallStatus.TIMEOUT,
                    error=str(exc),
                    error_code="TIMEOUT",
                    duration_seconds=duration,
                    request_id=request.request_id,
                    retry_count=retry_count,
                )

            except Exception as exc:
                last_error = exc
                if type(exc) in rt.spec.retryable_errors and retry_count < rt.spec.max_retries:
                    retry_count += 1
                    self._log.warning(
                        "tool_retry",
                        tool=request.tool_name,
                        attempt=retry_count,
                        error=str(exc),
                    )
                    continue
                break

        # All retries exhausted or non-retryable error
        duration = time.perf_counter() - start
        return ToolCallResult(
            status=ToolCallStatus.ERROR,
            error=str(last_error) if last_error else "Unknown error",
            error_code=getattr(last_error, "error_code", "EXECUTION_ERROR"),
            duration_seconds=duration,
            request_id=request.request_id,
            retry_count=retry_count,
        )

    async def acall(self, request: ToolCallRequest) -> ToolCallResult:
        """Execute a tool call asynchronously."""
        if request.tool_name not in self._tools:
            return ToolCallResult(
                status=ToolCallStatus.NOT_FOUND,
                error=f"Tool '{request.tool_name}' not registered",
                error_code="NOT_FOUND",
                request_id=request.request_id,
            )

        rt = self._tools[request.tool_name]
        timeout = request.timeout_seconds or rt.spec.timeout_seconds

        # Validate
        try:
            validated_args = _validate_arguments(rt.spec, request.arguments)
        except ToolValidationError as exc:
            return ToolCallResult(
                status=ToolCallStatus.VALIDATION_ERROR,
                error=str(exc),
                error_code=exc.error_code,
                request_id=request.request_id,
            )

        start = time.perf_counter()
        retry_count = 0
        last_error: Exception | None = None

        while retry_count <= rt.spec.max_retries:
            try:
                result_data = await _run_with_timeout(rt.fn, validated_args, timeout)
                duration = time.perf_counter() - start
                return ToolCallResult(
                    status=ToolCallStatus.SUCCESS,
                    data=result_data,
                    duration_seconds=duration,
                    request_id=request.request_id,
                    retry_count=retry_count,
                )

            except ToolTimeoutError as exc:
                duration = time.perf_counter() - start
                return ToolCallResult(
                    status=ToolCallStatus.TIMEOUT,
                    error=str(exc),
                    error_code="TIMEOUT",
                    duration_seconds=duration,
                    request_id=request.request_id,
                    retry_count=retry_count,
                )

            except Exception as exc:
                last_error = exc
                if type(exc) in rt.spec.retryable_errors and retry_count < rt.spec.max_retries:
                    retry_count += 1
                    self._log.warning(
                        "tool_async_retry",
                        tool=request.tool_name,
                        attempt=retry_count,
                        error=str(exc),
                    )
                    continue
                break

        duration = time.perf_counter() - start
        return ToolCallResult(
            status=ToolCallStatus.ERROR,
            error=str(last_error) if last_error else "Unknown error",
            error_code=getattr(last_error, "error_code", "EXECUTION_ERROR"),
            duration_seconds=duration,
            request_id=request.request_id,
            retry_count=retry_count,
        )


# ---------------------------------------------------------------------------
# Module-level convenience API
# ---------------------------------------------------------------------------

_default_registry: ToolRegistry | None = None


def _get_default_registry() -> ToolRegistry:
    global _default_registry
    if _default_registry is None:
        _default_registry = ToolRegistry()
    return _default_registry


def register_tool(
    fn: Callable[..., Any] | None = None,
    *,
    spec: ToolSpec | None = None,
    name: str | None = None,
) -> Callable[..., Any] | Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator / function to register a tool in the default registry.

    Usage as decorator::

        @register_tool(spec=ToolSpec(name="add", ...))
        def add(a: int, b: int) -> int:
            return a + b

    Usage as function::

        register_tool(my_function, spec=ToolSpec(...))
    """

    def _decorator(f: Callable[..., Any]) -> Callable[..., Any]:
        _get_default_registry().register(f, spec=spec, name=name or f.__name__)
        return f

    if fn is None:
        return _decorator
    return _decorator(fn)


def call_tool(name: str, **kwargs: Any) -> ToolCallResult:
    """Call a registered tool by name (sync)."""
    request = ToolCallRequest(tool_name=name, arguments=kwargs)
    return _get_default_registry().call(request)


async def acall_tool(name: str, **kwargs: Any) -> ToolCallResult:
    """Call a registered tool by name (async)."""
    request = ToolCallRequest(tool_name=name, arguments=kwargs)
    return await _get_default_registry().acall(request)


def get_tool_spec(name: str) -> ToolSpec:
    """Get the spec for a tool in the default registry."""
    return _get_default_registry().get_spec(name)


def list_registered_tools() -> list[ToolSpec]:
    """List all tools in the default registry."""
    return _get_default_registry().list_tools()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _derive_spec_from_signature(fn: Callable[..., Any], name: str) -> ToolSpec:
    """Best-effort ToolSpec derivation from a Python function signature."""
    sig = inspect.signature(fn)
    parameters: list[ToolParameter] = []

    type_map = {
        int: "integer",
        str: "string",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls"):
            continue

        param_type = "string"
        if param.annotation != inspect.Parameter.empty:
            param_type = type_map.get(param.annotation, "string")

        required = param.default == inspect.Parameter.empty
        default = None if required else param.default

        parameters.append(
            ToolParameter(
                name=param_name,
                type=param_type,
                description="",
                required=required,
                default=default,
            )
        )

    return ToolSpec(
        name=name,
        description=fn.__doc__ or "",
        parameters=parameters,
    )


async def _run_with_timeout(
    fn: Callable[..., Any],
    kwargs: dict[str, Any],
    timeout: float,
) -> Any:
    """Run a callable (sync or async) with a timeout."""
    if asyncio.iscoroutinefunction(fn):
        try:
            return await asyncio.wait_for(fn(**kwargs), timeout=timeout)
        except asyncio.TimeoutError:
            raise ToolTimeoutError(
                f"Tool call timed out after {timeout}s",
                timeout_seconds=timeout,
            )

    # Run sync function in thread pool
    loop = asyncio.get_running_loop()
    try:
        return await asyncio.wait_for(
            loop.run_in_executor(None, functools.partial(fn, **kwargs)),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        raise ToolTimeoutError(
            f"Tool call timed out after {timeout}s",
            timeout_seconds=timeout,
        )


def _run_sync_with_timeout(
    fn: Callable[..., Any],
    kwargs: dict[str, Any],
    timeout: float,
) -> Any:
    """Run a sync callable with timeout using a fresh event loop."""
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_run_with_timeout(fn, kwargs, timeout))
    except asyncio.TimeoutError:
        raise ToolTimeoutError(
            f"Tool call timed out after {timeout}s",
            timeout_seconds=timeout,
        )
    finally:
        loop.close()
