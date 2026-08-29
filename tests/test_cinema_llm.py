from pathlib import Path

from nexu.cinema_llm import (
    _extract_content,
    call_cinema_html_llm,
    call_cinema_text_llm,
    compact_llm_error,
    extract_html_document,
    has_terminal_artifacts,
    looks_like_html_document,
    normalize_html_document,
    parse_batch_alt_options,
)


def test_extract_html_document_from_fences() -> None:
    raw = "```html\n<!DOCTYPE html><html><body>ok</body></html>\n```"
    assert "ok" in extract_html_document(raw)


def test_extract_html_document_strips_rich_terminal_frame() -> None:
    raw = """╭────╮
│ <!DOCTYPE html>                                      │
│ <html><body>ok</body></html>                         │
╰────╯
"""
    html = extract_html_document(raw)
    assert html.startswith("<!DOCTYPE html>")
    assert "│" not in html
    assert "ok" in html


def test_normalize_html_document_without_doctype() -> None:
    raw = "Here is the UI:\n<html><head><title>x</title></head><body>ok</body></html>"
    html = normalize_html_document(raw)
    assert html.startswith("<!DOCTYPE html>")
    assert "ok" in html


def test_normalize_html_document_closes_partial_html() -> None:
    raw = "<html><body><div>partial</div>"
    html = normalize_html_document(raw)
    assert looks_like_html_document(html)
    assert html.lower().endswith("</html>")


def test_call_cinema_html_llm_rejects_invalid_structure(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "nexu.yaml").write_text(
        "version: nexu.v1\nllm:\n  allow_network_calls: true\n  provider: openrouter\n"
        "  model: test/model\n  api_key_env: TEST_CINEMA_KEY\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_CINEMA_KEY", "secret")

    def fake_completion(**kwargs):
        return {"choices": [{"message": {"content": "<html><body>no controls</body></html>"}}]}

    monkeypatch.setattr("nexu.cinema_llm._litellm_completion", lambda: fake_completion)
    html, err = call_cinema_html_llm("evolve this", tmp_path, ui_type="calculator")
    assert html is None
    assert err
    assert "structure validation" in err


def test_parse_batch_alt_options_skips_invalid_calculator_html() -> None:
    batch = (
        "<!-- NEXU_ALT_A -->\n"
        "<html><head></head><body><div id='screen' class='btn'>A</div></body></html>\n"
        "<!-- NEXU_ALT_B -->\n"
        "<html><body>B</body></html>\n"
        "<!-- NEXU_ALT_C -->\n"
        "<!DOCTYPE html><html><head></head><body><div id='screen' class='btn'>C</div></body></html>"
    )
    parsed = parse_batch_alt_options(batch, ui_type="calculator")
    assert parsed == {}


def test_parse_batch_alt_options_repairs_missing_head() -> None:
    batch = (
        "<!-- NEXU_ALT_A -->\n"
        "<html><body><div id='screen' class='btn'>A</div></body></html>\n"
        "<!-- NEXU_ALT_B -->\n"
        "<html><body><div id='screen' class='btn'>B</div></body></html>\n"
        "<!-- NEXU_ALT_C -->\n"
        "<html><body><div id='screen' class='btn'>C</div></body></html>"
    )
    parsed = parse_batch_alt_options(batch, ui_type="calculator")
    assert set(parsed.keys()) == {"alt_a.html", "alt_b.html", "alt_c.html"}
    for html in parsed.values():
        assert "<head>" in html.lower()


def test_parse_batch_alt_options_flexible_markers_web() -> None:
    batch = (
        "<!-- NEXU_ALT_A -->\n"
        "<html><body>A</body></html>\n"
        "<!-- NEXU_ALT_B -->\n"
        "```html\n<html><body>B</body></html>\n```\n"
        "<!-- NEXU_ALT_C -->\n"
        "<!DOCTYPE html><html><body>C</body></html>"
    )
    parsed = parse_batch_alt_options(batch, ui_type="web")
    assert set(parsed.keys()) == {"alt_a.html", "alt_b.html", "alt_c.html"}
    assert "A" in parsed["alt_a.html"]
    assert "B" in parsed["alt_b.html"]
    assert "C" in parsed["alt_c.html"]


def test_call_cinema_html_llm_accepts_html_without_doctype(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "nexu.yaml").write_text(
        "version: nexu.v1\nllm:\n  allow_network_calls: true\n  provider: openrouter\n"
        "  model: test/model\n  api_key_env: TEST_CINEMA_KEY\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_CINEMA_KEY", "secret")

    def fake_completion(**kwargs):
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            "<html><body><div id='screen' class='btn'>no doctype</div></body></html>"
                        ),
                    }
                }
            ]
        }

    monkeypatch.setattr("nexu.cinema_llm._litellm_completion", lambda: fake_completion)
    html, err = call_cinema_html_llm("evolve this", tmp_path, ui_type="calculator")
    assert err is None
    assert html and "no doctype" in html
    assert html.startswith("<!DOCTYPE html>")
    assert "<head>" in html.lower()


def test_has_terminal_artifacts_detects_box_drawing() -> None:
    assert has_terminal_artifacts("│ <!DOCTYPE html>")
    assert not has_terminal_artifacts("<!DOCTYPE html><html></html>")


def test_extract_content_supports_choice_text_fallback() -> None:
    response = {"choices": [{"text": "<!DOCTYPE html><html></html>"}]}
    assert _extract_content(response).startswith("<!DOCTYPE")


def test_extract_content_error_includes_response_shape() -> None:
    response = {"choices": [{"finish_reason": "length", "message": {"content": None}}]}
    try:
        _extract_content(response)
    except RuntimeError as exc:
        msg = str(exc)
    else:
        raise AssertionError("expected RuntimeError")
    assert "finish_reason=length" in msg
    assert "shape=" in msg


def test_compact_llm_error_openrouter_payload() -> None:
    err = 'OpenrouterException - {"error":{"message":"Rate limited"}}'
    assert compact_llm_error(err) == "Rate limited"


def test_call_cinema_html_llm_blocks_when_network_disabled(tmp_path: Path) -> None:
    (tmp_path / "nexu.yaml").write_text(
        "version: nexu.v1\nllm:\n  allow_network_calls: false\n",
        encoding="utf-8",
    )
    html, err = call_cinema_html_llm("prompt", tmp_path)
    assert html is None
    assert err and "allow_network_calls" in err


def test_call_cinema_html_llm_requires_api_key(tmp_path: Path, monkeypatch) -> None:
    (tmp_path / "nexu.yaml").write_text(
        "version: nexu.v1\nllm:\n  allow_network_calls: true\n  api_key_env: TEST_CINEMA_KEY\n",
        encoding="utf-8",
    )
    monkeypatch.delenv("TEST_CINEMA_KEY", raising=False)
    html, err = call_cinema_html_llm("prompt", tmp_path)
    assert html is None
    assert err == "TEST_CINEMA_KEY not set"


def test_call_cinema_html_llm_uses_litellm(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "nexu.yaml").write_text(
        "version: nexu.v1\nllm:\n  allow_network_calls: true\n  provider: openrouter\n"
        "  model: test/model\n  api_key_env: TEST_CINEMA_KEY\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_CINEMA_KEY", "secret")

    captured: dict = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return {
            "choices": [
                {
                    "message": {
                        "content": "<!DOCTYPE html><html><body>done</body></html>",
                    }
                }
            ]
        }

    monkeypatch.setattr("nexu.cinema_llm._litellm_completion", lambda: fake_completion)
    html, err = call_cinema_html_llm("evolve this", tmp_path)
    assert err is None
    assert html and "done" in html
    assert captured["model"] == "test/model"
    assert captured["api_key"] == "secret"
    assert captured["api_base"] == "https://openrouter.ai/api/v1"


def test_call_cinema_html_llm_uses_nexu_yaml_default_model(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "nexu.yaml").write_text(
        "version: nexu.v1\nllm:\n  allow_network_calls: true\n  provider: openrouter\n"
        "  model: openrouter/deepseek/deepseek-v4-pro\n  api_key_env: TEST_CINEMA_KEY\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_CINEMA_KEY", "secret")

    captured: dict = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        return {
            "choices": [
                {
                    "message": {
                        "content": "<!DOCTYPE html><html><body>done</body></html>",
                    }
                }
            ]
        }

    monkeypatch.setattr("nexu.cinema_llm._litellm_completion", lambda: fake_completion)
    html, err = call_cinema_html_llm("evolve this", tmp_path)
    assert err is None
    assert html and "done" in html
    assert captured["model"] == "openrouter/deepseek/deepseek-v4-pro"


def test_call_cinema_text_llm_uses_subllm_vision(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "nexu.yaml").write_text(
        "version: nexu.v1\nllm:\n  allow_network_calls: true\n  provider: openrouter\n"
        "  model: openrouter/deepseek/deepseek-v4-pro\n  api_key_env: TEST_CINEMA_KEY\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_CINEMA_KEY", "secret")
    screenshot = tmp_path / "shot.png"
    screenshot.write_bytes(b"\x89PNG\r\n\x1a\n")
    captured: dict = {}

    def fake_complete(application, function, messages, **kwargs):
        captured.update(
            application=application,
            function=function,
            messages=messages,
            kwargs=kwargs,
        )
        return type("Response", (), {"content": "vision-ok"})()

    monkeypatch.setattr("nexu.cinema_llm._subllm_complete", lambda: fake_complete)
    text, err = call_cinema_text_llm("describe", tmp_path, images=[str(screenshot)])
    assert err is None
    assert text == "vision-ok"
    assert captured["application"] == "autogrammar-nexu"
    assert captured["function"] == "vision"
    content = captured["messages"][1]["content"]
    assert content[0]["type"] == "image_url"
    assert content[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert content[1] == {"type": "text", "text": "describe"}
    assert captured["kwargs"]["credentials"] == {"openrouter": "secret"}


def test_call_cinema_text_llm_returns_raw_content(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "nexu.yaml").write_text(
        "version: nexu.v1\nllm:\n  allow_network_calls: true\n  provider: openrouter\n"
        "  model: test/model\n  api_key_env: TEST_CINEMA_KEY\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_CINEMA_KEY", "secret")

    def fake_completion(**kwargs):
        return {"choices": [{"message": {"content": "raw response"}}]}

    monkeypatch.setattr("nexu.cinema_llm._litellm_completion", lambda: fake_completion)
    text, err = call_cinema_text_llm("prompt", tmp_path)
    assert err is None
    assert text == "raw response"


def test_call_cinema_html_llm_error_includes_non_html_preview(monkeypatch, tmp_path: Path) -> None:
    (tmp_path / "nexu.yaml").write_text(
        "version: nexu.v1\nllm:\n  allow_network_calls: true\n  provider: openrouter\n"
        "  model: test/model\n  api_key_env: TEST_CINEMA_KEY\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("TEST_CINEMA_KEY", "secret")

    def fake_completion(**kwargs):
        return {"choices": [{"message": {"content": "I cannot produce HTML today."}}]}

    monkeypatch.setattr("nexu.cinema_llm._litellm_completion", lambda: fake_completion)
    html, err = call_cinema_html_llm("evolve this", tmp_path)
    assert html is None
    assert err
    assert "response_preview=I cannot produce HTML today." in err
