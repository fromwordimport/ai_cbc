"""AI agents for automated CBC analysis pipeline.

Provides:
  - BaseAgent: three-layer prompt architecture (system → rules → examples)
  - ConsumerGeneratorAgent: persona generation with self-correction
  - AnalysisAgent: orchestrates full analysis workflow
  - EvaluationChain: assesses virtual consumer response quality
"""

from aicbc.agents.analysis_agent import AnalysisAgent, AnalysisAgentConfig
from aicbc.agents.base import (
    AgentState,
    BaseAgent,
    DynamicExample,
    RuleInjection,
    SystemInstruction,
    ToolSpec,
)
from aicbc.agents.consumer_generator import ConsumerGeneratorAgent
from aicbc.agents.evaluation_chain import (
    ChoicePattern,
    ContradictionFinding,
    CorrectionRecord,
    EvaluationChain,
    EvaluationReport,
)

__all__ = [
    "AgentState",
    "AnalysisAgent",
    "AnalysisAgentConfig",
    "BaseAgent",
    "ConsumerGeneratorAgent",
    "DynamicExample",
    "EvaluationChain",
    "EvaluationReport",
    "ChoicePattern",
    "ContradictionFinding",
    "CorrectionRecord",
    "RuleInjection",
    "SystemInstruction",
    "ToolSpec",
]
