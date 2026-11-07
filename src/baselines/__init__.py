"""Baseline methods for comparison with AgentModernize."""

from src.baselines.single_prompt import SinglePromptBaseline
from src.baselines.chain_of_thought import ChainOfThoughtBaseline
from src.baselines.llm_feedback import LLMFeedbackBaseline

__all__ = ["SinglePromptBaseline", "ChainOfThoughtBaseline", "LLMFeedbackBaseline"]
