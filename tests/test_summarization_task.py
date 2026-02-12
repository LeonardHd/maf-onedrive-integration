"""Tests for the summarization task."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from maf_onedrive_integration.summarization_task.task import (
    SummaryResult,
    _build_chat_client,
    _extension,
    convert_to_markdown,
    summarize_file_content,
)


class TestExtension:
    """_extension helper."""

    def test_returns_extension_with_dot(self) -> None:
        assert _extension("report.pdf") == ".pdf"

    def test_returns_last_extension(self) -> None:
        assert _extension("archive.tar.gz") == ".gz"

    def test_returns_none_when_no_dot(self) -> None:
        assert _extension("README") is None


class TestConvertToMarkdown:
    """convert_to_markdown wraps markitdown."""

    @patch("maf_onedrive_integration.summarization_task.task.MarkItDown")
    def test_returns_markdown_text(self, mock_md_cls: MagicMock) -> None:
        # Arrange
        mock_result = MagicMock()
        mock_result.text_content = "# Title\nSome content"
        mock_md = MagicMock()
        mock_md.convert_stream.return_value = mock_result
        mock_md_cls.return_value = mock_md

        # Act
        text = convert_to_markdown(b"raw bytes", "document.docx")

        # Assert
        assert text == "# Title\nSome content"
        mock_md.convert_stream.assert_called_once()

    @patch("maf_onedrive_integration.summarization_task.task.MarkItDown")
    def test_raises_when_no_text_produced(self, mock_md_cls: MagicMock) -> None:
        # Arrange
        mock_result = MagicMock()
        mock_result.text_content = ""
        mock_md = MagicMock()
        mock_md.convert_stream.return_value = mock_result
        mock_md_cls.return_value = mock_md

        # Act & Assert
        with pytest.raises(ValueError, match="markitdown produced no text"):
            convert_to_markdown(b"raw bytes", "empty.bin")

    @patch("maf_onedrive_integration.summarization_task.task.MarkItDown")
    def test_raises_when_text_content_is_none(self, mock_md_cls: MagicMock) -> None:
        # Arrange
        mock_result = MagicMock()
        mock_result.text_content = None
        mock_md = MagicMock()
        mock_md.convert_stream.return_value = mock_result
        mock_md_cls.return_value = mock_md

        # Act & Assert
        with pytest.raises(ValueError, match="markitdown produced no text"):
            convert_to_markdown(b"raw bytes", "nothing.xyz")


class TestBuildChatClient:
    """_build_chat_client constructs a ChatAgent with OpenAIChatClient."""

    @patch.dict(
        "os.environ",
        {"GITHUB_TOKEN": "ghp_test123", "GITHUB_MODELS_MODEL_ID": "gpt-4o"},
    )
    @patch("maf_onedrive_integration.summarization_task.task.ChatAgent")
    @patch("maf_onedrive_integration.summarization_task.task.OpenAIChatClient")
    def test_builds_with_env_vars(
        self, mock_client_cls: MagicMock, mock_chat_cls: MagicMock
    ) -> None:
        # Act
        _build_chat_client()

        # Assert
        mock_client_cls.assert_called_once_with(
            model_id="gpt-4o",
            api_key="ghp_test123",
            base_url="https://models.inference.ai.azure.com",
        )
        mock_chat_cls.assert_called_once()
        call_kwargs = mock_chat_cls.call_args
        assert call_kwargs.kwargs["name"] == "Summarizer"

    @patch.dict("os.environ", {}, clear=False)
    @patch("maf_onedrive_integration.summarization_task.task.ChatAgent")
    @patch("maf_onedrive_integration.summarization_task.task.OpenAIChatClient")
    def test_defaults_when_env_vars_missing(
        self, mock_client_cls: MagicMock, mock_chat_cls: MagicMock
    ) -> None:
        # Arrange — remove env vars if present
        import os

        os.environ.pop("GITHUB_TOKEN", None)
        os.environ.pop("GITHUB_MODELS_MODEL_ID", None)

        # Act
        _build_chat_client()

        # Assert
        mock_client_cls.assert_called_once_with(
            model_id="gpt-4o-mini",
            api_key="",
            base_url="https://models.inference.ai.azure.com",
        )


class TestSummarizeFileContent:
    """End-to-end summarize_file_content tests."""

    @patch("maf_onedrive_integration.summarization_task.task._build_chat_client")
    @patch("maf_onedrive_integration.summarization_task.task.convert_to_markdown")
    async def test_success(
        self,
        mock_convert: MagicMock,
        mock_build: MagicMock,
    ) -> None:
        # Arrange
        mock_convert.return_value = "# Report\nSome content here."

        mock_response = MagicMock()
        mock_response.text = "This is a summary of the report."
        mock_agent = AsyncMock()
        mock_agent.run.return_value = mock_response
        mock_build.return_value = mock_agent

        # Act
        result = await summarize_file_content(b"file-bytes", "report.pdf")

        # Assert
        assert result.success is True
        assert result.summary == "This is a summary of the report."
        mock_convert.assert_called_once_with(b"file-bytes", "report.pdf")
        mock_agent.run.assert_called_once()

    @patch("maf_onedrive_integration.summarization_task.task.convert_to_markdown")
    async def test_conversion_failure_returns_error(
        self,
        mock_convert: MagicMock,
    ) -> None:
        # Arrange
        mock_convert.side_effect = ValueError("markitdown produced no text")

        # Act
        result = await summarize_file_content(b"bad-bytes", "corrupt.bin")

        # Assert
        assert result.success is False
        assert result.error is not None
        assert "Could not convert" in result.error

    @patch("maf_onedrive_integration.summarization_task.task._build_chat_client")
    @patch("maf_onedrive_integration.summarization_task.task.convert_to_markdown")
    async def test_llm_failure_returns_error(
        self,
        mock_convert: MagicMock,
        mock_build: MagicMock,
    ) -> None:
        # Arrange
        mock_convert.return_value = "# Some markdown"

        mock_agent = AsyncMock()
        mock_agent.run.side_effect = RuntimeError("API error")
        mock_build.return_value = mock_agent

        # Act
        result = await summarize_file_content(b"file-bytes", "doc.docx")

        # Assert
        assert result.success is False
        assert result.error is not None
        assert "model could not generate" in result.error


class TestSummaryResult:
    """SummaryResult dataclass."""

    def test_success_result(self) -> None:
        result = SummaryResult(success=True, summary="A summary.")
        assert result.success is True
        assert result.summary == "A summary."
        assert result.error is None

    def test_error_result(self) -> None:
        result = SummaryResult(success=False, error="Something went wrong.")
        assert result.success is False
        assert result.summary is None
        assert result.error == "Something went wrong."

    def test_frozen(self) -> None:
        result = SummaryResult(success=True, summary="text")
        with pytest.raises(AttributeError):
            result.success = False  # type: ignore[misc]
