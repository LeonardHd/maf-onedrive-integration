"""Summary agent powered by Microsoft Agent Framework + GitHub Models.

This module provides a single high-level coroutine, ``summarize_file_content``,
that:

1. Converts raw file bytes to Markdown via *markitdown*.
2. Sends the Markdown to an LLM (hosted on GitHub Models) through the
   Microsoft Agent Framework ``OpenAIChatClient`` and returns a concise
   summary.
"""

from __future__ import annotations

import io
import logging
import os
from dataclasses import dataclass

from agent_framework import ChatAgent
from agent_framework.openai import OpenAIChatClient
from markitdown import MarkItDown

logger = logging.getLogger(__name__)

# GitHub Models exposes an OpenAI-compatible Chat Completions endpoint.
_GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"
_DEFAULT_MODEL_ID = "gpt-4o-mini"

_SYSTEM_INSTRUCTIONS = (
    "You are a document summarization assistant. "
    "You will receive the Markdown-converted content of a file. "
    "Produce a clear, concise summary that captures the key points. "
    "Use bullet points where appropriate. "
    "If the content is empty or unintelligible, say so."
)


@dataclass(frozen=True)
class SummaryResult:
    """Result of a summarization attempt."""

    success: bool
    summary: str | None = None
    error: str | None = None


def _build_agent() -> ChatAgent:
    """Create and return a configured Agent Framework agent."""
    token = os.environ.get("GITHUB_TOKEN", "")
    model_id = os.environ.get("GITHUB_MODELS_MODEL_ID", _DEFAULT_MODEL_ID)

    client = OpenAIChatClient(
        model_id=model_id,
        api_key=token,
        base_url=_GITHUB_MODELS_BASE_URL,
    )

    return ChatAgent(
        chat_client=client,
        name="SummaryAgent",
        instructions=_SYSTEM_INSTRUCTIONS,
    )


def convert_to_markdown(file_bytes: bytes, filename: str) -> str:
    """Convert raw file bytes to Markdown text using *markitdown*.

    Parameters
    ----------
    file_bytes:
        The raw content of the file.
    filename:
        Original filename (used by markitdown for format detection).

    Returns
    -------
    str
        The Markdown representation of the file.

    Raises
    ------
    ValueError
        If markitdown could not extract any text.
    """
    md = MarkItDown(enable_plugins=False)
    stream = io.BytesIO(file_bytes)
    result = md.convert_stream(stream, file_extension=_extension(filename))
    text = (result.text_content or "").strip()
    if not text:
        msg = f"markitdown produced no text for '{filename}'"
        raise ValueError(msg)
    return text


async def summarize_file_content(
    file_bytes: bytes,
    filename: str,
) -> SummaryResult:
    """End-to-end: convert a file to Markdown, then summarise it with an LLM.

    Parameters
    ----------
    file_bytes:
        Raw bytes of the downloaded file.
    filename:
        Original filename (e.g. ``"report.pdf"``).

    Returns
    -------
    SummaryResult
        Contains the summary text on success, or an error message on failure.
    """
    # Step 1 — convert to markdown
    try:
        markdown_text = convert_to_markdown(file_bytes, filename)
    except Exception:
        logger.exception("Failed to convert '%s' to Markdown", filename)
        return SummaryResult(
            success=False,
            error=f"Could not convert '{filename}' to Markdown. "
            "The file format may not be supported by markitdown.",
        )

    # Step 2 — summarise via the agent
    try:
        agent = _build_agent()
        prompt = (
            f"Please summarise the following document (filename: {filename}):\n\n"
            f"{markdown_text}"
        )
        result = await agent.run(prompt)
        return SummaryResult(success=True, summary=result.text)
    except Exception:
        logger.exception("LLM summarization failed for '%s'", filename)
        return SummaryResult(
            success=False,
            error="The model could not generate a summary. "
            "Please check that GITHUB_TOKEN is set and valid.",
        )


def _extension(filename: str) -> str | None:
    """Return the file extension including the dot, or ``None``."""
    dot = filename.rfind(".")
    if dot == -1:
        return None
    return filename[dot:]
