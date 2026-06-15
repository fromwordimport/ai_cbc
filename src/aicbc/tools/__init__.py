"""Tool calling protocol for AI_CBC agent subsystem.

Provides standardized tool registration, invocation, error handling,
and timeout management across all agents.
"""

from aicbc.tools.protocol import (
    ToolCallError,
    ToolCallRequest,
    ToolCallResult,
    ToolRegistry,
    ToolSpec,
    ToolTimeoutError,
    ToolValidationError,
    call_tool,
    register_tool,
)

__all__ = [
    "ToolCallRequest",
    "ToolCallResult",
    "ToolSpec",
    "ToolRegistry",
    "ToolCallError",
    "ToolValidationError",
    "ToolTimeoutError",
    "register_tool",
    "call_tool",
]
