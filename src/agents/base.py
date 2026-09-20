"""Base class for all AgentModernize agents."""

from __future__ import annotations

import json
import logging
import os
import time
from abc import ABC, abstractmethod
from typing import Any

from langchain_openai import ChatOpenAI

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_TEMPERATURE_EXTRACTION = 0.2
DEFAULT_TEMPERATURE_GENERATION = 0.0



class BaseAgent(ABC):
    """Abstract base class for pipeline agents."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        temperature: float = DEFAULT_TEMPERATURE_EXTRACTION,
    ) -> None:
        self.model_name = model_name
        self.temperature = temperature
        self._llm: ChatOpenAI | None = None

    @property
    def llm(self) -> ChatOpenAI:
        if self._llm is None:
            base_url = os.environ.get("OPENAI_BASE_URL")
            api_key = os.environ.get("OPENAI_API_KEY", "")
            kwargs: dict[str, Any] = {
                "model": self.model_name,
                "temperature": self.temperature,
                "api_key": api_key,
            }
            if base_url:
                kwargs["base_url"] = base_url
            self._llm = ChatOpenAI(**kwargs)
        return self._llm

    @property
    @abstractmethod
    def agent_name(self) -> str:
        """Human-readable agent name for logging."""

    @abstractmethod
    def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute the agent on the shared pipeline state.

        Args:
            state: Current pipeline state dictionary.

        Returns:
            Updated pipeline state dictionary.
        """

    def _invoke_llm(self, prompt: str, *, max_retries: int = 3) -> str:
        """Send a prompt to the LLM and return the response text.

        Retries on transient connection errors with exponential backoff.
        """
        logger.info("[%s] Invoking LLM (%s)", self.agent_name, self.model_name)
        for attempt in range(max_retries):
            try:
                response = self.llm.invoke(prompt)
                content = response.content
                if isinstance(content, list):
                    content = "\n".join(
                        block.get("text", "") if isinstance(block, dict) else str(block)
                        for block in content
                    )
                return content
            except Exception as exc:
                if attempt < max_retries - 1 and "onnection" in str(exc):
                    wait = 2 ** (attempt + 1)
                    logger.warning(
                        "[%s] Connection error (attempt %d/%d), retrying in %ds: %s",
                        self.agent_name, attempt + 1, max_retries, wait, exc,
                    )
                    time.sleep(wait)
                else:
                    raise

    def _parse_json_response(self, response: str) -> dict:
        """Extract and parse JSON from LLM response, handling markdown fences."""
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            lines = lines[1:]  # remove opening fence
            if lines and lines[-1].strip() == "```":
                lines = lines[:-1]  # remove closing fence
            text = "\n".join(lines)
        return json.loads(text)
