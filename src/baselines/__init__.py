"""Baseline methods for comparison with AgentModernize."""

from src.baselines.single_prompt import SinglePromptBaseline
from src.baselines.chain_of_thought import ChainOfThoughtBaseline

__all__ = ["SinglePromptBaseline", "ChainOfThoughtBaseline"]
