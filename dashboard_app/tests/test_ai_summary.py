"""ai_summary.py のテスト（実APIは呼ばない）。"""
import types

import pytest

import ai_summary as A

TEXTS = {"business_description": "<p>自動車を作る。</p>", "business_risks": "為替リスク。", "management_policy": None}


def test_build_prompt_wraps_sections():
    prompt, truncated = A.build_user_prompt(A.SummaryInput("テスト株式会社", "2026-03-31", TEXTS))
    assert '<document title="事業の内容">' in prompt and '<document title="事業等のリスク">' in prompt
    assert "経営方針" not in prompt  # 空のセクションは入れない
    assert "<p>" not in prompt and truncated == []


def test_build_prompt_reports_truncation(monkeypatch):
    monkeypatch.setattr(A, "MAX_SECTION_CHARS", 10)
    _, truncated = A.build_user_prompt(A.SummaryInput("x", None, {"business_risks": "あ" * 50}))
    assert truncated == ["事業等のリスク"]


def test_build_prompt_without_texts_raises():
    with pytest.raises(A.AISummaryError):
        A.build_user_prompt(A.SummaryInput("x", None, {}))


def fake_anthropic(captured, stop_reason="end_turn"):
    class Messages:
        def create(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(
                stop_reason=stop_reason,
                content=[types.SimpleNamespace(type="thinking", thinking=""),
                         types.SimpleNamespace(type="text", text="### 何をしている会社か\n要約")],
            )

    return lambda api_key: types.SimpleNamespace(beta=types.SimpleNamespace(messages=Messages()))


def test_claude_request_shape(monkeypatch):
    import anthropic

    captured = {}
    monkeypatch.setattr(anthropic, "Anthropic", fake_anthropic(captured))
    out = A.summarize("claude", "prompt", "key", "claude-opus-5-5")
    assert out.startswith("### 何をしている会社か")
    assert captured["system"] == A.SYSTEM_PROMPT
    assert captured["fallbacks"] == "default" and captured["betas"] == ["server-side-fallback-2026-07-01"]


def test_claude_refusal(monkeypatch):
    import anthropic

    monkeypatch.setattr(anthropic, "Anthropic", fake_anthropic({}, stop_reason="refusal"))
    with pytest.raises(A.AISummaryError):
        A.summarize("claude", "prompt", "key", "claude-opus-5-5")


def test_openai_request_shape(monkeypatch):
    import openai

    captured = {}

    class Responses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return types.SimpleNamespace(output_text="要約", status="completed")

    monkeypatch.setattr(openai, "OpenAI", lambda api_key: types.SimpleNamespace(responses=Responses()))
    assert A.summarize("openai", "prompt", "key", "gpt-5") == "要約"
    assert captured["instructions"] == A.SYSTEM_PROMPT and captured["input"] == "prompt"


def test_missing_key_and_unknown_provider():
    with pytest.raises(A.AISummaryError):
        A.summarize("openai", "p", "", "gpt-5")
    with pytest.raises(A.AISummaryError):
        A.summarize("unknown", "p", "k", "m")
