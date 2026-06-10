"""Behavior simulation engine for interactive consumer research."""

from aicbc.core.simulation.behavior_simulator import (
    BehaviorSimulator,
    ConversationTurn,
    DecisionTrace,
)
from aicbc.core.simulation.cbc_choice_simulator import CBCChoiceSimulator
from aicbc.core.simulation.llm_choice_simulator import LLMChoiceSimulator

__all__ = [
    "BehaviorSimulator",
    "ConversationTurn",
    "DecisionTrace",
    "CBCChoiceSimulator",
    "LLMChoiceSimulator",
]
