import base64
import json
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest

from nexu.cinema_project_imports import (
    _build_http_preview_stage0,
    _safe_extract_zip,
    _validate_git_url,
    _validate_http_url,
    activate_imported_project,
    delete_imported_project,
    delete_project,
    extract_markpact_embedded_files,
    http_cinema_files_match_import,
    http_stage_matches_import,
    import_git_project,
    import_http_project,
    import_markpact_project,
    import_zip_project,
    is_deletable_imported_id,
    list_imported_projects,
    merged_projects_catalog,
    promote_cinema_option,
    read_imported_markpact,
    reject_import_stage_replacement,
    restore_http_import_stages_if_needed,
)


def test_import_zip_project_creates_markpact_migration_and_options(tmp_path: Path):
    archive = tmp_path / "demo.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("demo/package.json", '{"scripts":{"dev":"vite"}}')
        zf.writestr("demo/src/App.jsx", "export default function App(){return <h1>Demo</h1>}")

    cinema = tmp_path / "cinema"
    cinema.mkdir()
    payload = base64.b64encode(archive.read_bytes()).decode("ascii")

    result = import_zip_project(cinema, "demo.zip", payload)

    assert result["status"] == "project_imported"
    assert result["project"]["kind"] == "imported"
    assert result["project"]["imported"] is True
    assert result["project"]["markpact"] is True
    assert result["project"]["path_hint"].startswith("imported_projects/")
    assert result["project"]["file_count"] >= 1
    assert result["project"]["total_bytes"] > 0
    assert "markpact_path" in result["project"]
    markpact = Path(result["project"]["markpact_path"])
    assert markpact.exists()
    text = markpact.read_text(encoding="utf-8")
    assert "markpact:file path=nexu-import-meta.json" in text
    assert "markpact:run" in text
    assert "src/App.jsx" in text
    assert "Markpact migration" in (cinema / "stage0.html").read_text(encoding="utf-8")
    assert "Markpact migration" in (cinema / "alt_a.html").read_text(encoding="utf-8")

    catalog = list_imported_projects(cinema)
    assert catalog[0]["id"] == result["project"]["id"]
    assert catalog[0]["kind"] == "imported"
    assert catalog[0]["markpact"] is True
    assert catalog[0]["file_count"] >= 1
    assert catalog[0]["total_bytes"] > 0
    assert catalog[0]["source_url"] == "demo.zip"
    assert catalog[0]["path_hint"].startswith("imported_projects/")


def test_merged_projects_catalog_includes_imported(tmp_path: Path):
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    archive = tmp_path / "mini.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "hello")
    import_zip_project(cinema, "mini.zip", base64.b64encode(archive.read_bytes()).decode("ascii"))

    catalog = merged_projects_catalog(cinema)
    assert len(catalog["projects"]) == 10
    assert any(p.get("imported") for p in catalog["projects"])
    assert "import" in catalog["filters"]["domains"]


def test_delete_project_hides_demo_from_workspace_catalog(tmp_path: Path):
    cinema = tmp_path / "cinema"
    cinema.mkdir()

    result = delete_project(cinema, "web_app_dashboard", workspace_root=tmp_path)
    catalog = merged_projects_catalog(cinema)

    assert result["status"] == "deleted"
    assert result["delete_mode"] == "workspace_tombstone"
    assert "web_app_dashboard" not in {p["id"] for p in catalog["projects"]}


def test_import_zip_with_index_html_organizes_source(tmp_path: Path):
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    html = """<!DOCTYPE html><html><head>
<style>
.hero { color: #112233; padding: 2rem; margin: 1rem; border-radius: 8px; }
.card { background: #fff; box-shadow: 0 2px 4px rgba(0,0,0,.1); }
</style>
</head><body><h1>Landing</h1></body></html>"""
    archive = tmp_path / "site.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("index.html", html)

    result = import_zip_project(
        cinema,
        "site.zip",
        base64.b64encode(archive.read_bytes()).decode("ascii"),
    )

    assert result["status"] == "project_imported"
    project_id = result["project"]["id"]
    project_dir = cinema / "imported_projects" / project_id
    source_dir = project_dir / "source"
    meta = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    organize = meta.get("organize") or {}
    assert organize.get("styles_extracted") is True
    assert organize.get("extracted_files") == ["nexu-extracted.css"]
    assert (source_dir / "nexu-extracted.css").is_file()
    assert "<style" not in (source_dir / "index.html").read_text(encoding="utf-8").lower()
    assert "Markpact migration" in (cinema / "stage0.html").read_text(encoding="utf-8")


def test_import_zip_without_index_html_skips_organize(tmp_path: Path):
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    archive = tmp_path / "code.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("src/main.py", "print('hi')")

    result = import_zip_project(
        cinema,
        "code.zip",
        base64.b64encode(archive.read_bytes()).decode("ascii"),
    )

    project_id = result["project"]["id"]
    meta = json.loads(
        (cinema / "imported_projects" / project_id / "project.json").read_text(encoding="utf-8")
    )
    assert "organize" not in meta


def test_activate_imported_project_reloads_stages(tmp_path: Path):
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    archive = tmp_path / "mini.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("index.html", "<html><body>hi</body></html>")
    imported = import_zip_project(
        cinema,
        "mini.zip",
        base64.b64encode(archive.read_bytes()).decode("ascii"),
    )
    project_id = imported["project"]["id"]
    (cinema / "stage0.html").write_text("<html>stale</html>", encoding="utf-8")

    result = activate_imported_project(cinema, project_id)
    assert result["status"] == "project_imported"
    assert "Markpact migration" in (cinema / "stage0.html").read_text(encoding="utf-8")


def test_validate_urls_reject_file_scheme():
    assert _validate_http_url("file:///etc/passwd") == "URL must be http or https"
    assert _validate_git_url("file:///tmp/repo") == "file:// URLs are not allowed"


def test_safe_extract_zip_rejects_unsafe_paths(tmp_path: Path):
    zpath = tmp_path / "bad.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("../escape.txt", "nope")
    target = tmp_path / "out"
    target.mkdir()
    with pytest.raises(ValueError, match="unsafe zip path"):
        _safe_extract_zip(zpath, target)


def test_import_http_project_fetches_and_migrates(tmp_path: Path):
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    body = (
        b"<!DOCTYPE html><html><head>"
        b'<link rel="stylesheet" href="/styles/main.css">'
        b'</head><body><h1>Site</h1><img src="/img/hero.png" '
        b'srcset="/img/hero.png 1x, /img/hero@2x.png 2x" alt="Hero">'
        b'<img data-src="/img/lazy.jpg" alt="Lazy"></body></html>'
    )
    css_body = b"body { color: navy; }"
    image_body = b"\x89PNG\r\n"
    lazy_body = b"\xff\xd8\xff"

    class FakeResp:
        def __init__(self, payload: bytes, *, url: str, content_type: str):
            self.headers = {"Content-Type": content_type}
            self.url = url
            self._payload = payload
            self._done = False

        def read(self, n=-1):
            if self._done:
                return b""
            self._done = True
            return self._payload if n == -1 else self._payload[: max(n, 0)]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=0):
        target = req.full_url
        if target.endswith("/styles/main.css"):
            return FakeResp(
                css_body,
                url="https://example.com/styles/main.css",
                content_type="text/css; charset=utf-8",
            )
        if target.endswith("/img/hero.png"):
            return FakeResp(
                image_body,
                url="https://example.com/img/hero.png",
                content_type="image/png",
            )
        if target.endswith("/img/hero@2x.png"):
            return FakeResp(
                image_body,
                url="https://example.com/img/hero@2x.png",
                content_type="image/png",
            )
        if target.endswith("/img/lazy.jpg"):
            return FakeResp(
                lazy_body,
                url="https://example.com/img/lazy.jpg",
                content_type="image/jpeg",
            )
        return FakeResp(
            body,
            url="https://example.com/demo",
            content_type="text/html; charset=utf-8",
        )

    with (
        patch("repatch.web_fetch._render_with_playwright", return_value=None),
        patch("repatch.web_fetch._SAFE_OPENER.open", side_effect=fake_urlopen),
    ):
        result = import_http_project(cinema, "https://example.com/demo", allow_network=True)

    assert result["status"] == "project_imported"
    assert result["project"]["id"].startswith("http-")
    project_id = result["project"]["id"]
    project_dir = cinema / "imported_projects" / project_id
    meta = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    assert meta["source"] == "https://example.com/demo"
    assert meta["import_kind"] == "http"
    assert meta["fetch_meta"]["final_url"] == "https://example.com/demo"
    assert meta["fetch_meta"]["fetch_method"] == "urllib"
    assert {item["kind"] for item in meta["fetch_meta"]["assets"]} == {"stylesheet", "image"}
    assert len(meta["fetch_meta"]["images"]) == 3
    stage0 = (cinema / "stage0.html").read_text(encoding="utf-8")
    assert ">Site</h1>" in stage0
    assert "<base" not in stage0.lower()
    assert f'imported_projects/{project_id}/source/assets/stylesheet-0.css' in stage0
    assert f'imported_projects/{project_id}/source/assets/image-0.png' in stage0
    assert f'imported_projects/{project_id}/source/assets/image-1.png 2x' in stage0
    assert f'imported_projects/{project_id}/source/assets/image-2.jpg' in stage0
    assert "nexu preview: block cross-origin fetch" in stage0
    assert "Markpact migration" not in stage0
    assert (project_dir / "source" / "assets" / "stylesheet-0.css").exists()
    assert (project_dir / "source" / "assets" / "image-0.png").exists()
    assert (project_dir / "source" / "assets" / "image-1.png").exists()
    assert (project_dir / "source" / "assets" / "image-2.jpg").exists()
    alt_a = (cinema / "alt_a.html").read_text(encoding="utf-8")
    assert ">Site</h1>" in alt_a
    assert "calc-body" not in alt_a
    policy = json.loads((cinema / "intract_policy.json").read_text(encoding="utf-8"))
    assert policy["capsule"]["is_calculator"] is False
    assert policy["capsule"]["is_imported"] is True
    assert meta["llm_context_mode"] == "patch"
    assert (project_dir / "source" / "nexu-visual.css").is_file()
    assert (project_dir / "source" / "nexu-outline.html").is_file()
    assert meta["visual_css_bytes"] > 0
    assert meta["outline_node_count"] >= 1
    assert meta.get("organize", {}).get("targets_added", 0) >= 1
    assert meta.get("organize", {}).get("tagged_targets_count", 0) >= 1
    assert "extracted_files" in meta.get("organize", {})
    outline = (project_dir / "source" / "nexu-outline.html").read_text(encoding="utf-8")
    index_html = (project_dir / "source" / "index.html").read_text(encoding="utf-8")
    assert len(outline) < len(index_html)
    assert any(a.get("kind") == "visual_css" for a in meta.get("artifacts") or [])


def test_build_http_preview_stage0_serves_extracted_css_from_cinema(tmp_path: Path) -> None:
    """Organize-extracted assets must not resolve against the import origin base URL."""
    project_id = "http-example.com"
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True)
    (source_dir / "nexu-extracted.css").write_text("body { color: navy; }", encoding="utf-8")
    (source_dir / "index.html").write_text(
        """<!DOCTYPE html><html><head>
<base href="https://example.com/">
<link rel="stylesheet" href="nexu-extracted.css">
</head><body><h1>Demo</h1></body></html>""",
        encoding="utf-8",
    )
    (source_dir / "nexu-fetch-meta.json").write_text(
        json.dumps({"final_url": "https://example.com/"}),
        encoding="utf-8",
    )
    meta = {
        "id": project_id,
        "source_dir": str(source_dir),
        "organize": {"extracted_files": ["nexu-extracted.css"]},
    }

    stage0 = _build_http_preview_stage0(meta)

    assert stage0 is not None
    assert f'imported_projects/{project_id}/source/nexu-extracted.css' in stage0
    assert 'href="nexu-extracted.css"' not in stage0
    assert "<base" not in stage0.lower()


def test_build_http_preview_stage0_absolutizes_remote_asset_refs(tmp_path: Path) -> None:
    project_id = "http-example.com"
    source_dir = tmp_path / "source"
    source_dir.mkdir(parents=True)
    (source_dir / "index.html").write_text(
        """<!DOCTYPE html><html><head>
<base href="https://example.com/app/">
<link rel="stylesheet" href="/cdn/theme.css">
</head><body><img src="/img/logo.png" alt="Logo"></body></html>""",
        encoding="utf-8",
    )
    (source_dir / "nexu-fetch-meta.json").write_text(
        json.dumps({"final_url": "https://example.com/app/"}),
        encoding="utf-8",
    )
    meta = {"id": project_id, "source_dir": str(source_dir)}

    stage0 = _build_http_preview_stage0(meta)

    assert stage0 is not None
    assert 'href="https://example.com/cdn/theme.css"' in stage0
    assert 'src="https://example.com/img/logo.png"' in stage0
    assert "<base" not in stage0.lower()


def test_import_http_project_uses_rendered_dom_snapshot(tmp_path: Path):
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    rendered = (
        '<!DOCTYPE html><html><head><link rel="stylesheet" href="/app.css"></head>'
        '<body><div id="root"><h1>Rendered dashboard</h1><img src="/hero.webp"></div></body></html>'
    )

    class FakeResp:
        def __init__(self, payload: bytes, *, url: str, content_type: str):
            self.headers = {"Content-Type": content_type}
            self.url = url
            self._payload = payload
            self._done = False

        def read(self, n=-1):
            if self._done:
                return b""
            self._done = True
            return self._payload if n == -1 else self._payload[: max(n, 0)]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    def fake_urlopen(req, timeout=0):
        target = req.full_url
        if target.endswith("/app.css"):
            return FakeResp(b"#root{display:grid}", url=target, content_type="text/css")
        if target.endswith("/hero.webp"):
            return FakeResp(b"RIFFWEBP", url=target, content_type="image/webp")
        raise AssertionError(f"base HTML should come from rendered DOM, got: {target}")

    with (
        patch(
            "repatch.web_fetch._render_with_playwright",
            return_value=(rendered, "https://example.com/app"),
        ),
        patch("repatch.web_fetch._SAFE_OPENER.open", side_effect=fake_urlopen),
    ):
        result = import_http_project(cinema, "https://example.com/app", allow_network=True)

    project_id = result["project"]["id"]
    project_dir = cinema / "imported_projects" / project_id
    meta = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    assert meta["fetch_meta"]["fetch_method"] == "playwright"
    assert meta["fetch_meta"]["final_url"] == "https://example.com/app"
    assert len(meta["fetch_meta"]["assets"]) == 2
    index_html = (project_dir / "source" / "index.html").read_text(encoding="utf-8")
    assert "Rendered dashboard</h1>" in index_html
    stage0 = (cinema / "stage0.html").read_text(encoding="utf-8")
    assert "Rendered dashboard</h1>" in stage0
    assert f'imported_projects/{project_id}/source/assets/stylesheet-0.css' in stage0
    assert f'imported_projects/{project_id}/source/assets/image-0.webp' in stage0


def test_activate_http_import_regenerates_preview_stage0(tmp_path: Path):
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    body = b"<!DOCTYPE html><html><body><h1>Live preview</h1></body></html>"

    class FakeResp:
        headers = {"Content-Type": "text/html; charset=utf-8"}
        url = "https://example.org/"

        def __init__(self):
            self._done = False

        def read(self, n=-1):
            if self._done:
                return b""
            self._done = True
            return body if n == -1 else body[: max(n, 0)]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with (
        patch("repatch.web_fetch._render_with_playwright", return_value=None),
        patch("repatch.web_fetch._SAFE_OPENER.open", return_value=FakeResp()),
    ):
        imported = import_http_project(cinema, "https://example.org/", allow_network=True)

    project_id = imported["project"]["id"]
    (cinema / "stage0.html").write_text("<html>stale migration</html>", encoding="utf-8")

    result = activate_imported_project(cinema, project_id)
    assert result["status"] == "project_imported"
    assert result.get("goal_required") is True
    assert result.get("is_calculator") is False
    assert result.get("ui_type") == "web"
    boot = result.get("goal_bootstrap") or {}
    assert boot.get("status") == "requires_user_goal"
    assert "user_goal" not in boot
    assert result["project"].get("subtitle") == ""
    assert "Markpact migration workspace" not in json.dumps(result)
    assert "Chemical" not in json.dumps(result)
    stage0 = (cinema / "stage0.html").read_text(encoding="utf-8")
    assert ">Live preview</h1>" in stage0
    assert "Markpact migration" not in stage0
    assert "const NEXU_PARAMS = new URLSearchParams" in stage0
    assert "nexu preview: block cross-origin fetch" in stage0
    assert 'data-nexu-import-preview="http"' in stage0
    assert json.loads((cinema / "intract_policy_ledger.json").read_text(encoding="utf-8")) == []


def test_activate_http_import_regenerates_preprocess_when_missing(tmp_path: Path):
    """Re-activate migrates pre-preprocess HTTP imports without re-fetching."""
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    body = b"""<!DOCTYPE html><html><head><style>body{color:#112233}</style></head>
<body><main class="hero"><h1>Legacy site</h1></main></body></html>"""

    class FakeResp:
        headers = {"Content-Type": "text/html; charset=utf-8"}
        url = "https://legacy.example/"

        def __init__(self):
            self._done = False

        def read(self, n=-1):
            if self._done:
                return b""
            self._done = True
            return body if n == -1 else body[: max(n, 0)]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with (
        patch("repatch.web_fetch._render_with_playwright", return_value=None),
        patch("repatch.web_fetch._SAFE_OPENER.open", return_value=FakeResp()),
    ):
        imported = import_http_project(cinema, "https://legacy.example/", allow_network=True)

    project_id = imported["project"]["id"]
    project_dir = cinema / "imported_projects" / project_id
    source_dir = project_dir / "source"
    (source_dir / "nexu-visual.css").unlink()
    (source_dir / "nexu-outline.html").unlink()
    meta_path = project_dir / "project.json"
    legacy_meta = json.loads(meta_path.read_text(encoding="utf-8"))
    for key in (
        "llm_context_mode",
        "visual_css_path",
        "html_outline_path",
        "visual_css_bytes",
        "outline_node_count",
        "visual_css_truncated",
    ):
        legacy_meta.pop(key, None)
    legacy_meta["artifacts"] = [
        {"kind": "markpact", "path": "README.markpact.md"},
        {"kind": "source", "path": "source/"},
    ]
    meta_path.write_text(json.dumps(legacy_meta, indent=2) + "\n", encoding="utf-8")
    (cinema / "stage0.html").write_text("<html>stale without shield</html>", encoding="utf-8")

    result = activate_imported_project(cinema, project_id)
    assert result["status"] == "project_imported"

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["llm_context_mode"] == "patch"
    assert (source_dir / "nexu-visual.css").is_file()
    assert (source_dir / "nexu-outline.html").is_file()
    assert meta["visual_css_bytes"] > 0
    assert meta["outline_node_count"] >= 1
    assert any(a.get("kind") == "visual_css" for a in meta.get("artifacts") or [])

    from nexu.cinema_scope import load_cinema_ui_profile

    active = json.loads((cinema / "active_project.json").read_text(encoding="utf-8"))
    profile = load_cinema_ui_profile(active, cinema)
    assert profile.get("llm_context_mode") == "patch"
    assert profile.get("visual_css")

    stage0 = (cinema / "stage0.html").read_text(encoding="utf-8")
    assert ">Legacy site</h1>" in stage0
    assert "const NEXU_PARAMS = new URLSearchParams" in stage0
    assert "nexu preview: block cross-origin fetch" in stage0


def test_activate_http_import_empty_subtitle_not_goal(tmp_path: Path):
    """HTTP activate must not seed Markpact placeholder text as project goal."""
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    body = b"<!DOCTYPE html><html><body><h1>Site</h1></body></html>"

    class FakeResp:
        headers = {"Content-Type": "text/html; charset=utf-8"}
        url = "https://example.net/"

        def __init__(self):
            self._done = False

        def read(self, n=-1):
            if self._done:
                return b""
            self._done = True
            return body if n == -1 else body[: max(n, 0)]

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    with (
        patch("repatch.web_fetch._render_with_playwright", return_value=None),
        patch("repatch.web_fetch._SAFE_OPENER.open", return_value=FakeResp()),
    ):
        imported = import_http_project(cinema, "https://example.net/", allow_network=True)

    project_id = imported["project"]["id"]
    active_path = cinema / "active_project.json"
    active = json.loads(active_path.read_text(encoding="utf-8"))
    assert active.get("subtitle") == ""
    assert "Markpact migration workspace" not in json.dumps(active)

    result = activate_imported_project(cinema, project_id)
    assert result.get("goal_required") is True
    assert result["project"].get("subtitle") == ""
    assert "user_goal" not in (result.get("goal_bootstrap") or {})
    assert "Markpact migration workspace" not in json.dumps(result)


def test_activate_zip_import_does_not_require_user_goal(tmp_path: Path):
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    archive = tmp_path / "mini.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("index.html", "<html><body>hi</body></html>")
    imported = import_zip_project(
        cinema,
        "mini.zip",
        base64.b64encode(archive.read_bytes()).decode("ascii"),
    )
    project_id = imported["project"]["id"]
    result = activate_imported_project(cinema, project_id)
    assert result.get("goal_required") is False
    assert (result.get("goal_bootstrap") or {}).get("status") != "requires_user_goal"


def test_activate_imported_project_resets_calculator_ledger(tmp_path: Path):
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    archive = tmp_path / "mini.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("index.html", "<html><body>hi</body></html>")
    imported = import_zip_project(
        cinema,
        "mini.zip",
        base64.b64encode(archive.read_bytes()).decode("ascii"),
    )
    project_id = imported["project"]["id"]
    (cinema / "intract_policy_ledger.json").write_text(
        '[{"stage":0,"keep":["sin"],"delete":["log"]}]',
        encoding="utf-8",
    )

    activate_imported_project(cinema, project_id)

    assert json.loads((cinema / "intract_policy_ledger.json").read_text(encoding="utf-8")) == []
    policy = json.loads((cinema / "intract_policy.json").read_text(encoding="utf-8"))
    assert policy["capsule"]["is_calculator"] is False


def test_import_http_project_requires_network_flag(tmp_path: Path):
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    result = import_http_project(cinema, "https://example.com", allow_network=False)
    assert "error" in result


def test_import_git_project_requires_network_flag(tmp_path: Path):
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    result = import_git_project(cinema, "https://github.com/org/repo.git", allow_network=False)
    assert result.get("error")


def test_is_deletable_imported_id():
    assert is_deletable_imported_id("zip-demo")
    assert is_deletable_imported_id("http-example.com")
    assert is_deletable_imported_id("http-malortgdynia.pl")
    assert not is_deletable_imported_id("web_app_calculator")
    assert not is_deletable_imported_id("../escape")
    assert not is_deletable_imported_id("http-http-malortgdynia.pl")


def test_delete_imported_http_domain_id_with_dot(tmp_path: Path):
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    project_id = "http-malortgdynia.pl"
    project_dir = cinema / "imported_projects" / project_id
    project_dir.mkdir(parents=True)
    (project_dir / "project.json").write_text(
        json.dumps(
            {
                "id": project_id,
                "title": "Malortgdynia.Pl",
                "import_kind": "http",
                "source": "https://malortgdynia.pl/",
            }
        ),
        encoding="utf-8",
    )
    (project_dir / "source").mkdir()
    (project_dir / "README.markpact.md").write_text("# Markpact migration\n", encoding="utf-8")

    catalog = list_imported_projects(cinema)
    assert catalog[0]["id"] == project_id
    assert catalog[0]["deletable"] is True
    assert catalog[0]["imported"] is True

    result = delete_imported_project(cinema, project_id)
    assert result["status"] == "deleted"
    assert result["id"] == project_id
    assert not project_dir.exists()
    assert not list_imported_projects(cinema)


def test_delete_imported_project_removes_directory(tmp_path: Path):
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    archive = tmp_path / "drop.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "hello")
    imported = import_zip_project(
        cinema,
        "drop.zip",
        base64.b64encode(archive.read_bytes()).decode("ascii"),
    )
    project_id = imported["project"]["id"]
    project_dir = cinema / "imported_projects" / project_id
    assert project_dir.is_dir()

    result = delete_imported_project(cinema, project_id)
    assert result["status"] == "deleted"
    assert result["was_active"] is True
    assert not project_dir.exists()
    assert not list_imported_projects(cinema)


def test_extract_markpact_embedded_files_parses_fenced_blocks() -> None:
    md = (
        "# Demo\n\n"
        "```html markpact:file path=index.html\n"
        "<html><body>Hi</body></html>\n"
        "```\n\n"
        "````json markpact:file path=nexu-import-meta.json\n"
        '{"title": "Demo"}\n'
        "````\n"
    )
    files = extract_markpact_embedded_files(md)
    paths = {path for path, _ in files}
    assert "index.html" in paths
    assert "nexu-import-meta.json" in paths


def test_import_markpact_project_extracts_files_and_activates(tmp_path: Path) -> None:
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    md = (
        "# Demo App — Markpact\n\n"
        "```html markpact:file path=index.html\n"
        "<html><body><h1>Hi</h1></body></html>\n"
        "```\n\n"
        "```json markpact:file path=nexu-import-meta.json\n"
        '{"title": "Demo App"}\n'
        "```\n"
    )
    result = import_markpact_project(cinema, "demo-app.md", content_bytes=md.encode("utf-8"))
    assert result["status"] == "project_imported"
    project_id = result["project"]["id"]
    assert project_id.startswith("markpact-")
    assert result["project"]["import_kind"] == "markpact"
    assert result["project"]["title"] == "Demo App"
    project_dir = cinema / "imported_projects" / project_id
    assert (project_dir / "README.markpact.md").read_text(encoding="utf-8") == md
    index_html = (project_dir / "source" / "index.html").read_text(encoding="utf-8")
    assert "<h1" in index_html and "Hi</h1>" in index_html
    assert is_deletable_imported_id(project_id)


def test_import_markpact_project_rejects_non_markdown(tmp_path: Path) -> None:
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    result = import_markpact_project(cinema, "bundle.zip", content_bytes=b"not md")
    assert result["error"]


def test_read_imported_markpact_returns_markdown(tmp_path: Path):
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    archive = tmp_path / "mini.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("readme.txt", "hello")
    imported = import_zip_project(
        cinema,
        "mini.zip",
        base64.b64encode(archive.read_bytes()).decode("ascii"),
    )
    payload = read_imported_markpact(cinema, imported["project"]["id"])
    assert "markdown" in payload
    assert "Markpact migration" in payload["markdown"]


def test_http_stage_matches_import_rejects_calculator_pollution(tmp_path: Path) -> None:
    meta = {
        "id": "http-malortgdynia.pl",
        "import_kind": "http",
        "source": "https://malortgdynia.pl/",
        "source_url": "https://malortgdynia.pl/",
    }
    calc_html = '<html><body class="calc-body"><section id="functions">7</section></body></html>'
    site_html = (
        '<html><body data-nexu-import-preview="http">'
        "<h1>Malort Gdynia</h1>https://malortgdynia.pl/</body></html>"
    )
    assert not http_stage_matches_import(calc_html, meta)
    assert http_stage_matches_import(site_html, meta)
    assert reject_import_stage_replacement(calc_html, meta)


def test_http_stage_matches_import_ignores_nexu_shield_selectors(tmp_path: Path) -> None:
    meta = {
        "id": "http-malortgdynia.pl",
        "import_kind": "http",
        "source": "https://malortgdynia.pl/",
        "source_url": "https://malortgdynia.pl/",
    }
    shield_html = (
        '<html><body data-nexu-import-preview="http">'
        "<h1>Malort Gdynia</h1>https://malortgdynia.pl/"
        "<script>const SELECTOR_BASE = ['.btn', '.btn-sci', '.btn-sci-excess'];</script>"
        "</body></html>"
    )
    assert http_stage_matches_import(shield_html, meta)


def test_http_cinema_files_match_import_detects_polluted_alt(tmp_path: Path) -> None:
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    meta = {
        "id": "http-example.org",
        "import_kind": "http",
        "source": "https://example.org/",
        "source_url": "https://example.org/",
    }
    site = (
        '<html><body data-nexu-import-preview="http"><h1>Live site</h1>'
        "https://example.org/</body></html>"
    )
    (cinema / "stage0.html").write_text(site, encoding="utf-8")
    (cinema / "alt_b.html").write_text(
        '<html><body class="calc-body"><section id="functions">7</section></body></html>',
        encoding="utf-8",
    )
    assert not http_cinema_files_match_import(cinema, meta)


def test_restore_http_import_stages_if_needed_rebuilds_from_seed(tmp_path: Path) -> None:
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    project_id = "http-example.org"
    project_dir = cinema / "imported_projects" / project_id
    source_dir = project_dir / "source"
    source_dir.mkdir(parents=True)
    (source_dir / "index.html").write_text(
        '<html><body data-nexu-import-preview="http"><h1>Live site</h1>'
        "https://example.org/</body></html>",
        encoding="utf-8",
    )
    (source_dir / "nexu-fetch-meta.json").write_text(
        json.dumps({"final_url": "https://example.org/"}),
        encoding="utf-8",
    )
    meta = {
        "id": project_id,
        "import_kind": "http",
        "source": "https://example.org/",
        "source_dir": str(source_dir),
    }
    (project_dir / "project.json").write_text(json.dumps(meta), encoding="utf-8")
    (cinema / "stage0.html").write_text(
        '<html><body class="calc-body"><section id="functions">7</section></body></html>',
        encoding="utf-8",
    )
    (cinema / "alt_a.html").write_text("<html>calculator alt</html>", encoding="utf-8")

    result = restore_http_import_stages_if_needed(cinema, meta)

    assert result["status"] == "restored"
    stage0 = (cinema / "stage0.html").read_text(encoding="utf-8")
    assert "<h1>Live site</h1>" in stage0
    assert "calc-body" not in stage0
    alt_a = (cinema / "alt_a.html").read_text(encoding="utf-8")
    assert "<h1>Live site</h1>" in alt_a
    assert "calculator alt" not in alt_a


def test_promote_http_import_restores_polluted_alt_before_copy(tmp_path: Path) -> None:
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    project_id = "http-malortgdynia.pl"
    project_dir = cinema / "imported_projects" / project_id
    source_dir = project_dir / "source"
    source_dir.mkdir(parents=True)
    site_html = (
        '<html><body data-nexu-import-preview="http"><h1>Malort Gdynia</h1>'
        "https://malortgdynia.pl/</body></html>"
    )
    (source_dir / "index.html").write_text(site_html, encoding="utf-8")
    (source_dir / "nexu-fetch-meta.json").write_text(
        json.dumps({"final_url": "https://malortgdynia.pl/"}),
        encoding="utf-8",
    )
    meta = {
        "id": project_id,
        "title": "Malort",
        "import_kind": "http",
        "source": "https://malortgdynia.pl/",
        "source_dir": str(source_dir),
    }
    (project_dir / "project.json").write_text(json.dumps(meta), encoding="utf-8")
    calc_html = (
        '<html><head><title>Scientific Calculator (S1)</title></head>'
        '<body class="calc-body" data-project="web_app_calculator">'
        '<section id="functions">7</section></body></html>'
    )
    (cinema / "stage0.html").write_text(calc_html, encoding="utf-8")
    (cinema / "alt_b.html").write_text(calc_html, encoding="utf-8")
    (cinema / "active_project.json").write_text(
        json.dumps({"id": project_id, "kind": "imported", "import_kind": "http"}),
        encoding="utf-8",
    )

    activate_imported_project(cinema, project_id)
    (cinema / "alt_b.html").write_text(calc_html, encoding="utf-8")

    result = promote_cinema_option(cinema, alt_name="alt_b.html", stage=0)

    assert result.get("status") == "promoted"
    stage0 = (cinema / "stage0.html").read_text(encoding="utf-8")
    assert "Malort Gdynia" in stage0
    assert "Scientific Calculator" not in stage0
    assert "calc-body" not in stage0
    alt_b = (cinema / "alt_b.html").read_text(encoding="utf-8")
    assert "Malort Gdynia" in alt_b
    assert "Scientific Calculator" not in alt_b


def test_activate_http_import_after_calculator_pollution(tmp_path: Path) -> None:
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    project_id = "http-example.net"
    project_dir = cinema / "imported_projects" / project_id
    source_dir = project_dir / "source"
    source_dir.mkdir(parents=True)
    (source_dir / "index.html").write_text(
        '<html><body><h1>Imported homepage</h1>https://example.net/</body></html>',
        encoding="utf-8",
    )
    (source_dir / "nexu-fetch-meta.json").write_text(
        json.dumps({"final_url": "https://example.net/"}),
        encoding="utf-8",
    )
    meta = {
        "id": project_id,
        "title": "Example Net",
        "import_kind": "http",
        "source": "https://example.net/",
        "source_dir": str(source_dir),
        "markpact_path": str(project_dir / "README.markpact.md"),
        "file_count": 2,
        "total_bytes": 100,
    }
    (project_dir / "README.markpact.md").write_text("# Markpact\n", encoding="utf-8")
    (project_dir / "project.json").write_text(json.dumps(meta), encoding="utf-8")
    (cinema / "stage0.html").write_text(
        '<html><body class="calc-body"><section id="functions">7</section></body></html>',
        encoding="utf-8",
    )
    (cinema / "intract_policy_ledger.json").write_text(
        '[{"stage":0,"keep":["sin"],"delete":["log"]}]',
        encoding="utf-8",
    )

    result = activate_imported_project(cinema, project_id)

    assert result["status"] == "project_imported"
    stage0 = (cinema / "stage0.html").read_text(encoding="utf-8")
    assert "<h1>Imported homepage</h1>" in stage0
    assert "calc-body" not in stage0
    assert json.loads((cinema / "intract_policy_ledger.json").read_text(encoding="utf-8")) == []
