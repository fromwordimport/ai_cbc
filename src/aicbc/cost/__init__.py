"""Cost tracking and fuse module for AI_CBC.

Provides global cost accounting, multi-level fuse thresholds, and
automatic model degradation to prevent runaway LLM API spending.
"""

from aicbc.cost.tracker import CostTracker, FuseStatus, get_cost_tracker
from aicbc.cost.fuse import CostFuse, CostFuseError, DegradationLevel

__all__ = [
    "CostTracker",
    "CostFuse",
    "CostFuseError",
    "DegradationLevel",
    "FuseStatus",
    "get_cost_tracker",
]
