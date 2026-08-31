import json
import re
from pathlib import Path

from nexu.cinema_offline_options import write_goal_options_offline
from nexu.cinema_project_imports import import_http_project
from nexu.cinema_scope import (
    allowed_scope_ids,
    can_use_offline_fast_iterate,
    cinema_has_offline_baseline,
    default_scope_for_kind,
    inject_scope_style,
    load_cinema_ui_profile,
    normalize_focus_scope,
    offline_fast_scopes_for_kind,
    scope_option_variants,
    scope_supports_offline_fast_path,
    scoped_html_fragment,
    strip_scope_style,
)


def test_dashboard_disallows_keypad_scope():
    assert "keypad" not in allowed_scope_ids("dashboard")
    assert normalize_focus_scope("keypad", "dashboard") == "functions"
    assert default_scope_for_kind("dashboard") == "functions"


def test_calculator_allows_keypad_scope():
    assert "keypad" in allowed_scope_ids("calculator")
    assert normalize_focus_scope("keypad", "calculator") == "keypad"


def test_offline_fast_scopes_per_kind():
    calc = offline_fast_scopes_for_kind("calculator")
    assert "colors" in calc
    assert "keypad" in calc
    assert "functions" not in calc
    dash = offline_fast_scopes_for_kind("dashboard")
    assert "colors" in dash
    assert "keypad" not in dash
    assert scope_supports_offline_fast_path("colors", "calculator")
    assert scope_supports_offline_fast_path("keypad", "calculator")
    assert not scope_supports_offline_fast_path("functions", "calculator")
    assert scope_supports_offline_fast_path("colors", "dashboard")


def test_dashboard_colors_offline_labels(tmp_path: Path):
    (tmp_path / "active_project.json").write_text(
        '{"id":"web_app_dashboard","kind":"dashboard"}',
        encoding="utf-8",
    )
    for name in ("stage0.html", "stage1.html", "stage2.html"):
        (tmp_path / name).write_text(
            "<!DOCTYPE html><html><head></head><body>"
            "<div class='app-shell kpi-grid'></div></body></html>",
            encoding="utf-8",
        )
    labels = write_goal_options_offline(
        tmp_path,
        user_goal="KPI cards",
        focus_scope="colors",
    )
    assert any("colors:" in label for label in labels)
    html = (tmp_path / "alt_a.html").read_text(encoding="utf-8")
    assert "nexu-scope-variant" in html


def test_scope_option_variants_dashboard_functions():
    specs = scope_option_variants("functions", "dashboard")
    assert specs[0][1].startswith("Option A (functions:")


def test_strip_and_inject_scope_style():
    html = "<html><head></head><body></body></html>"
    patched = inject_scope_style(html, "shapes", "c", project_kind="dashboard")
    assert "nexu-scope-variant" in patched
    assert "border-radius:999px" in patched
    assert strip_scope_style(patched) == html


def test_scoped_html_fragment_for_calculator_colors() -> None:
    html = (
        "<html><body><div class='calc-body'>"
        "<div class='screen'>0</div></div></body></html>"
    )
    fragment = scoped_html_fragment(html, "colors", "calculator")
    assert fragment is not None
    assert "calc-body" in fragment


def test_cinema_has_offline_baseline(tmp_path: Path) -> None:
    assert not cinema_has_offline_baseline(tmp_path)
    (tmp_path / "stage0.html").write_text("<html><body>x</body></html>", encoding="utf-8")
    assert not cinema_has_offline_baseline(tmp_path)
    html = "<!DOCTYPE html><html><body>" + ("x" * 200) + "</body></html>"
    (tmp_path / "stage0.html").write_text(html, encoding="utf-8")
    assert cinema_has_offline_baseline(tmp_path)


def test_inject_scope_style_calculator_colors():
    html = (
        "<html><head></head><body><div class='calc-body'>"
        "<div class='screen'></div></div></body></html>"
    )
    patched = inject_scope_style(html, "colors", "b", project_kind="calculator")
    assert "nexu-scope-variant" in patched
    assert ".calc-body" in patched
    assert "#facc15" in patched


def test_load_cinema_ui_profile_from_active_and_stage(tmp_path: Path) -> None:
    (tmp_path / "stage0.html").write_text(
        "<html><body><div class='calc-body'><div class='btn-eq'></div></div></body></html>",
        encoding="utf-8",
    )
    profile = load_cinema_ui_profile({"kind": "", "title": "Demo"}, tmp_path)
    assert profile["ui_type"] == "calculator"
    profile = load_cinema_ui_profile({"kind": "dashboard", "title": "Ops"}, tmp_path)
    assert profile["ui_type"] == "dashboard"


def test_ui_profile_ignores_runtime_script_tokens(tmp_path: Path) -> None:
    (tmp_path / "stage0.html").write_text(
        "<!DOCTYPE html><html><body><main>Imported page</main>"
        "<script>if (id === 'btn-eq') return '=';</script></body></html>",
        encoding="utf-8",
    )

    profile = load_cinema_ui_profile({"kind": "imported", "title": "Site"}, tmp_path)

    assert profile["ui_type"] == "web"


def test_can_use_offline_fast_iterate(tmp_path: Path) -> None:
    html = "<!DOCTYPE html><html><body>" + ("x" * 200) + "</body></html>"
    (tmp_path / "stage0.html").write_text(html, encoding="utf-8")
    assert can_use_offline_fast_iterate("colors", "calculator", tmp_path)
    assert not can_use_offline_fast_iterate("functions", "calculator", tmp_path)
    assert not can_use_offline_fast_iterate(
        "colors",
        "calculator",
        tmp_path,
        force_llm=True,
    )
    assert not can_use_offline_fast_iterate(
        "colors",
        "calculator",
        tmp_path,
        fast_scope_options=False,
    )
    assert not can_use_offline_fast_iterate("colors", "calculator", tmp_path / "missing")
    assert can_use_offline_fast_iterate("colors", "imported", tmp_path)


def test_imported_kind_uses_web_scopes() -> None:
    assert "keypad" not in allowed_scope_ids("imported")
    assert default_scope_for_kind("imported") == "functions"


def test_http_import_offline_colors_keeps_site_markers(tmp_path: Path, monkeypatch) -> None:
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    body = (
        b"<!DOCTYPE html><html><head></head>"
        b'<body data-nexu-import-preview="http"><main id="site-hero">'
        b"<h1>Malort Site</h1></main></body></html>"
    )

    class FakeResp:
        headers = {"Content-Type": "text/html; charset=utf-8"}
        url = "https://malort.example/"

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

    monkeypatch.setattr(
        "repatch.web_fetch._SAFE_OPENER.open",
        lambda req, timeout=0: FakeResp(),
    )
    monkeypatch.setattr(
        "repatch.web_fetch.socket.getaddrinfo",
        lambda host, port: [(None, None, None, None, ("93.184.216.34", 0))],
    )
    monkeypatch.setattr("repatch.web_fetch._render_with_playwright", lambda url: None)
    imported = import_http_project(cinema, "https://malort.example/", allow_network=True)
    project_id = imported["project"]["id"]
    (cinema / "alt_a.html").write_text(
        '<div class="calc-body"><div class="screen" id="screen">0</div></div>',
        encoding="utf-8",
    )
    (cinema / "intract_policy_ledger.json").write_text(
        '[{"stage":0,"keep":["sin","cos"],"delete":["log"]}]',
        encoding="utf-8",
    )

    labels = write_goal_options_offline(
        cinema,
        keep_els=["sin", "cos"],
        delete_els=["log"],
        user_goal="nowoczesny design strony dla młodych",
        focus_scope="colors",
    )

    assert any("colors:" in label for label in labels)
    for name in ("alt_a.html", "alt_b.html", "alt_c.html"):
        html = (cinema / name).read_text(encoding="utf-8")
        assert "Malort Site" in html
        assert 'data-nexu-import-preview="http"' in html
        assert "calc-body" not in html
        assert "nexu-scope-variant" in html
    policy = json.loads((cinema / "intract_policy.json").read_text(encoding="utf-8"))
    assert policy["capsule"]["is_calculator"] is False
    assert project_id.startswith("http-")


def test_http_import_offline_colors_recolors_marked_buttons(tmp_path: Path) -> None:
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    (cinema / "active_project.json").write_text(
        json.dumps(
            {
                "id": "http-malortgdynia.pl",
                "kind": "imported",
                "import_kind": "http",
                "title": "Malort",
            }
        ),
        encoding="utf-8",
    )
    stage = """<!DOCTYPE html><html><head></head><body data-nexu-import-preview="http">
<a class="kb-btn2_237106-a1" href="#">Zapisz dziecko</a>
<button class="kb-btn2_999">Nasza lokalizacja</button>
</body></html>"""
    (cinema / "stage0.html").write_text(stage, encoding="utf-8")

    labels = write_goal_options_offline(
        cinema,
        keep_els=[],
        delete_els=["Zapisz dziecko", "Nasza lokalizacja"],
        focus_scope="colors",
    )

    assert any("colors:" in label for label in labels)
    alts = {
        name: (cinema / name).read_text(encoding="utf-8")
        for name in ("alt_a.html", "alt_b.html", "alt_c.html")
    }
    assert alts["alt_a.html"] != alts["alt_b.html"]
    for html in alts.values():
        assert "nexu-scope-variant" in html
        assert "background-color:" in html
        assert ".kb-btn2_237106-a1" in html or '[data-nexu-target="Zapisz dziecko"]' in html
    assert "background-color:#38bdf8" in alts["alt_a.html"]
    assert "background-color:#facc15" in alts["alt_b.html"]
    assert "background-color:#e879f9" in alts["alt_c.html"]


def test_http_import_offline_colors_respects_keep_marks(tmp_path: Path) -> None:
    """Mixed KEEP + DELETE: only DELETE-marked buttons get offline recolor CSS."""
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    (cinema / "active_project.json").write_text(
        json.dumps(
            {
                "id": "http-malortgdynia.pl",
                "kind": "imported",
                "import_kind": "http",
                "title": "Malort",
            }
        ),
        encoding="utf-8",
    )
    stage = """<!DOCTYPE html><html><head></head><body data-nexu-import-preview="http">
<button class="button header-button">Zapisz swoje dziecko</button>
<a class="button kb-btn2_237106-a1" href="#">Zapisz dziecko</a>
<button class="button kb-btn2_487f06-54">Nasza lokalizacja</button>
</body></html>"""
    (cinema / "stage0.html").write_text(stage, encoding="utf-8")

    labels = write_goal_options_offline(
        cinema,
        keep_els=["Zapisz dziecko", "Nasza lokalizacja"],
        delete_els=["Zapisz swoje dziecko"],
        focus_scope="colors",
    )

    assert any("colors:" in label for label in labels)
    for name in ("alt_a.html", "alt_b.html", "alt_c.html"):
        html = (cinema / name).read_text(encoding="utf-8")
        assert "nexu-scope-variant" in html
        style_match = re.search(
            r'<style id="nexu-scope-variant">\s*(.*?)\s*</style>',
            html,
            flags=re.I | re.S,
        )
        assert style_match is not None
        scope_css = style_match.group(1)
        assert "background-color:" in scope_css
        assert '[data-nexu-target="Zapisz swoje dziecko"]' in scope_css
        assert ".button" not in scope_css
        assert ".kb-btn2_237106-a1" not in scope_css
        assert ".kb-btn2_487f06-54" not in scope_css
        assert "html,body" not in scope_css


def test_http_import_offline_orientation_marks_create_two_column_patch(
    tmp_path: Path,
) -> None:
    """#orientation marks should change layout containers, not only marked leaves."""
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    (cinema / "active_project.json").write_text(
        json.dumps(
            {
                "id": "http-malortgdynia.pl",
                "kind": "imported",
                "import_kind": "http",
                "title": "Malort",
            }
        ),
        encoding="utf-8",
    )
    stage = """<!DOCTYPE html><html><head></head><body data-nexu-import-preview="http">
<main class="site-content"><div class="entry-content">
<h2>Pracownia Malort Gdynia</h2>
<p>Zapraszamy do wyjątkowego miejsca</p>
<a class="kb-btn2_237106-a1" href="#">Zapisz dziecko</a>
<a class="kb-btn2_487f06-54" href="#">Nasza lokalizacja</a>
</div></main>
</body></html>"""
    (cinema / "stage0.html").write_text(stage, encoding="utf-8")

    labels = write_goal_options_offline(
        cinema,
        delete_els=[
            "Pracownia Malort Gdynia",
            "Zapraszamy do wyjątkowego miejsca",
            "Zapisz dziecko",
            "Nasza lokalizacja",
        ],
        user_goal="podziel na dwie kolumny",
        focus_scope="orientation",
    )

    assert any("orientation:" in label for label in labels)
    html = (cinema / "alt_b.html").read_text(encoding="utf-8")
    style_match = re.search(
        r'<style id="nexu-scope-variant">\s*(.*?)\s*</style>',
        html,
        flags=re.I | re.S,
    )
    assert style_match is not None
    scope_css = style_match.group(1)
    assert ":has(" in scope_css
    assert "grid-template-columns:1fr 1fr" in scope_css
    assert '[data-nexu-target="Zapisz dziecko"]' in scope_css
    assert "Zapisz dziecko" in html


def test_http_import_offline_colors_recolors_kadence_heading_inline(tmp_path: Path) -> None:
    """DELETE on Kadence h2: offline colors beat inline color on nested strong."""
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    (cinema / "active_project.json").write_text(
        json.dumps(
            {
                "id": "http-malortgdynia.pl",
                "kind": "imported",
                "import_kind": "http",
                "title": "Malort",
            }
        ),
        encoding="utf-8",
    )
    mark = "Pracownia Malort Gdynia – przestrzeń dla kreatywności Twojego dziecka"
    stage = f"""<!DOCTYPE html><html><head></head><body data-nexu-import-preview="http">
<h2 class="kt-adv-heading2_289857-94 wp-block-kadence-advancedheading" data-kb-block="kb-adv-heading289857-94">
<strong style="color: #007D13;">Pracownia Malort Gdynia – </strong>przestrzeń dla kreatywności Twojego dziecka
</h2>
</body></html>"""
    (cinema / "stage0.html").write_text(stage, encoding="utf-8")

    labels = write_goal_options_offline(
        cinema,
        keep_els=[],
        delete_els=[mark],
        focus_scope="colors",
    )

    assert any("colors:" in label for label in labels)
    alts = {
        name: (cinema / name).read_text(encoding="utf-8")
        for name in ("alt_a.html", "alt_b.html", "alt_c.html")
    }
    for html in alts.values():
        assert "nexu-scope-variant" in html
        assert ".kt-adv-heading2_289857-94" in html
        assert ".kt-adv-heading2_289857-94 *" in html
        assert "color:" in html and "!important" in html
    assert "color:#0f172a!important" in alts["alt_a.html"]
    assert "color:#000!important" in alts["alt_b.html"]
    assert "color:#1e1b4b!important" in alts["alt_c.html"]


def test_http_import_offline_colors_recolors_all_marked_kadence_headings(
    tmp_path: Path,
) -> None:
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    (cinema / "active_project.json").write_text(
        json.dumps(
            {
                "id": "http-malortgdynia.pl",
                "kind": "imported",
                "import_kind": "http",
                "title": "Malort",
            }
        ),
        encoding="utf-8",
    )
    heading = "Pracownia Malort Gdynia – przestrzeń dla kreatywności Twojego dziecka"
    body = (
        "Zapraszamy do wyjątkowego miejsca, gdzie dzieci rozwijają wyobraźnię i "
        "pewność siebie poprzez spontaniczną twórczość artystyczną."
    )
    stage = f"""<!DOCTYPE html><html><head></head><body data-nexu-import-preview="http">
<h2 class="kt-adv-heading2_289857-94 wp-block-kadence-advancedheading">
<strong style="color: #007D13;">Pracownia Malort Gdynia&nbsp;&#8211; </strong>przestrzeń dla kreatywności Twojego dziecka
</h2>
<h2 class="kt-adv-heading2_79aa1a-c6 wp-block-kadence-advancedheading">{body}</h2>
</body></html>"""
    (cinema / "stage0.html").write_text(stage, encoding="utf-8")

    labels = write_goal_options_offline(
        cinema,
        keep_els=[],
        delete_els=[body, heading],
        focus_scope="colors",
    )

    assert any("colors:" in label for label in labels)
    html = (cinema / "alt_c.html").read_text(encoding="utf-8")
    assert ".kt-adv-heading2_289857-94" in html
    assert ".kt-adv-heading2_79aa1a-c6" in html
    assert ".kt-adv-heading2_289857-94 *" in html
    assert ".kt-adv-heading2_79aa1a-c6 *" in html
    assert "background-color:#e879f9" in html
    assert "color:#1e1b4b!important" in html


def test_http_import_offline_orientation_two_columns_with_delete_marks(
    tmp_path: Path,
) -> None:
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    (cinema / "active_project.json").write_text(
        json.dumps(
            {
                "id": "http-malortgdynia.pl",
                "kind": "imported",
                "import_kind": "http",
                "title": "Malort",
            }
        ),
        encoding="utf-8",
    )
    stage = """<!DOCTYPE html><html><head></head><body data-nexu-import-preview="http">
<main class="site-content"><div class="entry-content">
<section>Left</section><section>Right</section>
</div></main>
<a class="kb-btn2_237106-a1" href="#">Zapisz dziecko</a>
<button class="kb-btn2_999">Nasza lokalizacja</button>
</body></html>"""
    (cinema / "stage0.html").write_text(stage, encoding="utf-8")

    labels = write_goal_options_offline(
        cinema,
        keep_els=[],
        delete_els=["Zapisz dziecko", "Nasza lokalizacja"],
        user_goal="podziel na dwie kolumny",
        focus_scope="orientation",
    )

    assert any("two columns" in label for label in labels)
    alt_b = (cinema / "alt_b.html").read_text(encoding="utf-8")
    style_match = re.search(
        r'<style id="nexu-scope-variant">\s*(.*?)\s*</style>',
        alt_b,
        flags=re.I | re.S,
    )
    assert style_match is not None
    scope_css = style_match.group(1)
    assert "grid-template-columns" in scope_css
    assert "1fr 1fr" in scope_css
    assert "body{" in scope_css or ".entry-content{" in scope_css


def test_http_import_offline_display_keeps_entry_content_headings(
    tmp_path: Path,
) -> None:
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    (cinema / "active_project.json").write_text(
        json.dumps(
            {
                "id": "http-malortgdynia.pl",
                "kind": "imported",
                "import_kind": "http",
                "title": "Malort",
            }
        ),
        encoding="utf-8",
    )
    stage = """<!DOCTYPE html><html><head></head><body data-nexu-import-preview="http">
<main class="site-content"><div class="entry-content">
<h1>Hero</h1><p>Intro</p>
</div></main>
<button class="kb-btn2_237106-a1">Zapisz dziecko</button>
</body></html>"""
    (cinema / "stage0.html").write_text(stage, encoding="utf-8")

    labels = write_goal_options_offline(
        cinema,
        keep_els=[],
        delete_els=["Zapisz dziecko"],
        focus_scope="display",
    )

    assert any("display:" in label for label in labels)
    alt_b = (cinema / "alt_b.html").read_text(encoding="utf-8")
    style_match = re.search(
        r'<style id="nexu-scope-variant">\s*(.*?)\s*</style>',
        alt_b,
        flags=re.I | re.S,
    )
    assert style_match is not None
    scope_css = style_match.group(1)
    assert ".entry-content h1" in scope_css
    assert "font-size:1.65rem" in scope_css
    assert '[data-nexu-target="Zapisz dziecko"]' in scope_css


def test_http_import_offline_shapes_keeps_content_button_radii(
    tmp_path: Path,
) -> None:
    cinema = tmp_path / "cinema"
    cinema.mkdir()
    (cinema / "active_project.json").write_text(
        json.dumps(
            {
                "id": "http-malortgdynia.pl",
                "kind": "imported",
                "import_kind": "http",
                "title": "Malort",
            }
        ),
        encoding="utf-8",
    )
    stage = """<!DOCTYPE html><html><head></head><body data-nexu-import-preview="http">
<div class="entry-content">
<button class="kb-btn2_237106-a1">Zapisz dziecko</button>
</div></body></html>"""
    (cinema / "stage0.html").write_text(stage, encoding="utf-8")

    labels = write_goal_options_offline(
        cinema,
        keep_els=[],
        delete_els=["Zapisz dziecko"],
        focus_scope="shapes",
    )

    assert any("shapes:" in label for label in labels)
    alt_c = (cinema / "alt_c.html").read_text(encoding="utf-8")
    style_match = re.search(
        r'<style id="nexu-scope-variant">\s*(.*?)\s*</style>',
        alt_c,
        flags=re.I | re.S,
    )
    assert style_match is not None
    scope_css = style_match.group(1)
    assert ".entry-content button" in scope_css
    assert "border-radius:999px" in scope_css
