"""In-process LiteLLM calls for Cinema HTML generation (avoids llx CLI overhead)."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from .cinema_html import ensure_html_document_closure
from .cinema_html_validate import prepare_cinema_html_document
from .config import load_config, load_env_files

_CONFIG_CACHE: tuple[float, object] | None = None
_COMPLETION = None


def _cached_config(root: Path):
    global _CONFIG_CACHE
    yaml_path = root / "nexu.yaml"
    mtime = yaml_path.stat().st_mtime if yaml_path.is_file() else 0.0
    if _CONFIG_CACHE is not None and _CONFIG_CACHE[0] == mtime:
        return _CONFIG_CACHE[1]
    load_env_files(root)
    config = load_config(root)
    _CONFIG_CACHE = (mtime, config)
    return config


def _litellm_completion():
    global _COMPLETION
    if _COMPLETION is None:
        from litellm import completion as _COMPLETION  # type: ignore
    return _COMPLETION


def _subllm_complete():
    from subllm import complete as subllm_complete

    return subllm_complete


def _strip_markdown_fences(text: str) -> str:
    raw = str(text or "").strip()
    fence_match = re.search(r"```(?:html|HTML)?\s*\n([\s\S]*?)```", raw)
    if fence_match:
        return fence_match.group(1).strip()
    if raw.startswith("```"):
        lines = raw.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        return "\n".join(lines).strip()
    return raw


_RICH_BORDER_CHARS = ("│", "║", "╭", "╮", "╰", "╯", "─", "═")


def _strip_rich_console_artifacts(text: str) -> str:
    """Remove Rich/terminal box borders that some CLIs add around LLM output."""
    lines = str(text or "").splitlines()
    cleaned: list[str] = []
    for line in lines:
        s = line.rstrip()
        stripped = s.strip()
        if stripped and set(stripped) <= set("╭╮╰╯─═ "):
            continue
        if stripped.startswith(("│", "║")):
            stripped = stripped[1:].strip()
            if stripped.endswith(("│", "║")):
                stripped = stripped[:-1].rstrip()
            cleaned.append(stripped)
        else:
            cleaned.append(s)
    return "\n".join(cleaned).strip()


def has_terminal_artifacts(text: str) -> bool:
    """Detect box-drawing output that should never be persisted as app HTML."""
    sample = "\n".join(str(text or "").splitlines()[:24])
    return any(ch in sample for ch in _RICH_BORDER_CHARS)


def looks_like_html_document(text: str) -> bool:
    sample = str(text or "").lstrip()[:4000].lower()
    return "<html" in sample or "<!doctype" in sample


def normalize_html_document(text: str) -> str:
    """Extract and normalize one HTML document from LLM output."""
    cleaned = _strip_rich_console_artifacts(_strip_markdown_fences(text))
    match = re.search(r"<!DOCTYPE\s+html[\s\S]*?</html>", cleaned, flags=re.I)
    if match:
        return match.group(0).strip()
    match = re.search(r"<html[\s\S]*?</html>", cleaned, flags=re.I)
    if match:
        return "<!DOCTYPE html>\n" + match.group(0).strip()
    match = re.search(r"(?:<!DOCTYPE\s+html\s*>)?\s*<html[\s\S]*", cleaned, flags=re.I)
    if match:
        partial = ensure_html_document_closure(match.group(0).strip())
        if partial.lstrip().upper().startswith("<!DOCTYPE"):
            return partial
        return "<!DOCTYPE html>\n" + partial
    return cleaned


def extract_html_document(text: str) -> str:
    return normalize_html_document(text)


_BATCH_ALT_FILES = {"A": "alt_a.html", "B": "alt_b.html", "C": "alt_c.html"}


def parse_batch_alt_options(text: str, *, ui_type: str = "web") -> dict[str, str]:
    """Parse NEXU_ALT_A/B/C marked batch LLM output into option filenames."""
    cleaned = _strip_rich_console_artifacts(text or "")
    out: dict[str, str] = {}
    for key, filename in _BATCH_ALT_FILES.items():
        segment_pattern = (
            rf"<!--\s*NEXU_ALT_{key}\s*-->\s*"
            rf"(?P<body>[\s\S]*?)(?=<!--\s*NEXU_ALT_[ABC]\s*-->|$)"
        )
        segment_match = re.search(segment_pattern, cleaned, flags=re.I)
        if not segment_match:
            strict = re.search(
                rf"<!--\s*NEXU_ALT_{key}\s*-->\s*"
                rf"(?P<html><!DOCTYPE\s+html[\s\S]*?</html>)",
                cleaned,
                flags=re.I,
            )
            if strict:
                html = strict.group("html").strip()
            else:
                continue
        else:
            html = normalize_html_document(segment_match.group("body"))
        if not looks_like_html_document(html):
            continue
        prepared, ok, _errors = prepare_cinema_html_document(html, ui_type=ui_type)
        if ok and prepared:
            out[filename] = prepared
    if set(out.keys()) != set(_BATCH_ALT_FILES.values()):
        return {}
    return out


def _as_plain_data(value: Any) -> Any:
    if isinstance(value, dict):
        return value
    for attr in ("model_dump", "dict"):
        fn = getattr(value, attr, None)
        if callable(fn):
            try:
                return fn()
            except Exception:
                pass
    return value


def _lookup(obj: Any, key: str, default: Any = None) -> Any:
    obj = _as_plain_data(obj)
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _response_shape(response: Any) -> str:
    data = _as_plain_data(response)
    try:
        text = json.dumps(data, ensure_ascii=False, default=str)
    except Exception:
        text = repr(response)
    return text[:1200]


def _extract_parts(content: list) -> str | None:
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict):
            text = item.get("text")
            if isinstance(text, str):
                parts.append(text)
        elif isinstance(item, str):
            parts.append(item)
    joined = "".join(parts)
    if joined.strip():
        return joined
    return None


def _extract_content(response: Any) -> str:
    data = _as_plain_data(response)
    choices = _lookup(data, "choices")
    if not choices:
        output_text = _lookup(data, "output_text")
        if isinstance(output_text, str) and output_text.strip():
            return output_text
        raise RuntimeError(
            "LLM response did not contain choices; shape=" + _response_shape(response)
        )

    first = _as_plain_data(choices[0])
    message = _lookup(first, "message", {})
    content = _lookup(message, "content")
    if isinstance(content, list):
        joined = _extract_parts(content)
        if joined is not None:
            return joined
    if isinstance(content, str) and content.strip():
        return content

    for key in ("text", "reasoning_content", "reasoning", "output_text"):
        candidate = _lookup(first, key) if key == "text" else _lookup(message, key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate

    finish = _lookup(first, "finish_reason", "unknown")
    raise RuntimeError(
        "LLM response did not contain message content"
        f" (finish_reason={finish}); shape={_response_shape(response)}"
    )


def compact_llm_error(err_text: str) -> str:
    if "OpenrouterException - " in err_text:
        payload = err_text.split("OpenrouterException - ", 1)[1].strip()
        try:
            import json

            data = json.loads(payload)
            msg = data.get("error", {}).get("message")
            if isinstance(msg, str) and msg.strip():
                return msg.strip()
        except Exception:
            pass
    compact = " ".join(str(err_text).split())
    return compact[:260]


def _compact_response_preview(text: str, *, limit: int = 800) -> str:
    compact = " ".join(str(text or "").split())
    return compact[:limit]


def _as_image_url(ref: str, root: Path) -> str:
    value = str(ref or "").strip()
    if value.startswith(("data:image/", "https://")):
        return value
    path = Path(value)
    if not path.is_absolute():
        path = root / path
    if not path.is_file():
        raise ValueError(f"vision image not found: {ref}")
    suffix = path.suffix.lower().lstrip(".") or "png"
    mime = {"jpg": "jpeg", "jpeg": "jpeg", "png": "png", "webp": "webp"}.get(suffix, "png")
    import base64

    encoded = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return f"data:image/{mime};base64,{encoded}"


def call_cinema_text_llm(
    prompt: str,
    root: Path,
    *,
    model: str | None = None,
    max_tokens: int = 20480,
    system_prompt: str | None = None,
    images: list[str] | None = None,
) -> tuple[str | None, str | None]:
    """Return raw LLM text content via LiteLLM/OpenRouter or SubLLM vision."""
    try:
        config = _cached_config(root)
        llm = config.llm
    except Exception as exc:
        return None, compact_llm_error(str(exc))

    if not llm.allow_network_calls:
        return None, "llm.allow_network_calls disabled in nexu.yaml"

    api_key = os.environ.get(llm.api_key_env, "")
    if not api_key:
        return None, f"{llm.api_key_env} not set"

    resolved_model = model or llm.model
    system = system_prompt or (
        "You are a UI evolution engine. Return exactly one complete HTML5 document "
        "with <!DOCTYPE html>, <html>, <head> (all CSS in <style> tags inside head), "
        "and <body>. Preserve existing DOM ids and calculator/dashboard structure. "
        "No markdown fences, no explanation."
    )
    image_refs = [item for item in (images or []) if str(item).strip()]
    if image_refs:
        try:
            subllm_complete = _subllm_complete()
        except Exception:
            return None, "Install subactor-subllm for Cinema vision"
        try:
            user_content: list[dict[str, Any]] = [
                {"type": "image_url", "image_url": {"url": _as_image_url(item, root)}}
                for item in image_refs
            ]
            user_content.append({"type": "text", "text": prompt})
            response = subllm_complete(
                "autogrammar-nexu",
                "vision",
                [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user_content},
                ],
                timeout_seconds=float(llm.timeout),
                credentials={"openrouter": api_key},
            )
            return response.content, None
        except Exception as exc:
            return None, compact_llm_error(str(exc))

    try:
        completion = _litellm_completion()
    except Exception:
        return None, "Install litellm (uv sync) for Cinema live iteration"

    kwargs: dict[str, Any] = {
        "model": resolved_model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": prompt},
        ],
        "temperature": llm.temperature,
        "max_tokens": max_tokens,
        "timeout": llm.timeout,
        "api_key": api_key,
    }
    if llm.provider == "openrouter":
        kwargs["api_base"] = llm.base_url

    try:
        response = completion(**kwargs)
        return _extract_content(response), None
    except Exception as exc:
        return None, compact_llm_error(str(exc))


def call_cinema_html_llm(
    prompt: str,
    root: Path,
    *,
    model: str | None = None,
    max_tokens: int = 20480,
    ui_type: str = "web",
    images: list[str] | None = None,
) -> tuple[str | None, str | None]:
    """
    Generate one complete HTML document via LiteLLM/OpenRouter.

    Returns (html, error). Uses nexu.yaml llm settings; no llx subprocess.
    Image refs use the central SubLLM vision route.
    """
    content, err = call_cinema_text_llm(
        prompt,
        root,
        model=model,
        max_tokens=max_tokens,
        images=images,
    )
    if err:
        return None, err
    raw = normalize_html_document(content or "")
    if raw and looks_like_html_document(raw):
        if has_terminal_artifacts(raw):
            return None, "LLM output contained terminal box-drawing artifacts, not clean HTML"
        prepared, ok, validation_errors = prepare_cinema_html_document(raw, ui_type=ui_type)
        if ok and prepared:
            return prepared, None
        detail = "; ".join(validation_errors[:4])
        preview = _compact_response_preview(content or "")
        suffix = f"; response_preview={preview}" if preview else ""
        return None, "LLM HTML failed structure validation: " + detail + suffix
    preview = _compact_response_preview(content or "")
    detail = f"; response_preview={preview}" if preview else ""
    return None, "LLM did not return a complete HTML document" + detail
