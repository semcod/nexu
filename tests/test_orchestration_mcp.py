from pathlib import Path

from nexu.capsule import create_capsule
from nexu.freeze import freeze_project
from nexu.init_project import init_project
from nexu.mcp_server import (
    MCP_TOOLS,
    _bounded_steps,
    _result_content,
    call_tool,
    handle_mcp_message,
)
from nexu.orchestrate import build_capsule_orchestration


def _make_project(tmp_path: Path) -> None:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "app.py").write_text(
        "# @intract.v1 scope:function intent:preview:item priority:1 domain:demo "
        "input:item output:evolved_capsule,promotion_plan,evidence_map effect:read "
        "forbid:write,secret_leak validate:output_presence,no_forbidden_effect "
        'meaning:"demo"\n'
        "def preview_item(item):\n"
        '    evidence_map = {"item": item}\n'
        '    return {"evolved_capsule": item, "promotion_plan": [], '
        '"evidence_map": evidence_map}\n',
        encoding="utf-8",
    )


def test_orchestration_offline(tmp_path: Path):
    _make_project(tmp_path)
    init_project(tmp_path)
    create_capsule(
        tmp_path, "demo", include=["src/**"], routes=["/demo"], endpoints=["GET:/api/demo"]
    )

    result = build_capsule_orchestration(tmp_path, "demo", steps=3, goal="orchestrate demo")

    assert Path(result["yaml"]).exists()
    assert Path(result["prompt"]).exists()
    assert result["mode"] == "offline_deterministic"
    assert result["steps"] == 3


def test_mcp_tool_dispatch_and_protocol(tmp_path: Path):
    _make_project(tmp_path)
    init_project(tmp_path)
    assert any(tool["name"] == "nexu_capsule_orchestrate" for tool in MCP_TOOLS)

    created = call_tool(
        tmp_path,
        "nexu_capsule_create",
        {
            "name": "demo",
            "include": ["src/**"],
            "routes": ["/demo"],
            "endpoints": ["GET:/api/demo"],
        },
    )
    assert created["name"] == "demo"

    response = handle_mcp_message(
        tmp_path,
        {"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
    )
    assert response is not None
    assert response["result"]["tools"]

    called = handle_mcp_message(
        tmp_path,
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "tools/call",
            "params": {
                "name": "nexu_capsule_orchestrate",
                "arguments": {"name": "demo", "steps": 2},
            },
        },
    )
    assert called is not None
    assert "content" in called["result"]


def test_mcp_promotion_requires_actor_bound_exact_hash(tmp_path: Path, monkeypatch):
    import nexu.promote as promote

    _make_project(tmp_path)
    init_project(tmp_path)
    snapshot = freeze_project(tmp_path, "baseline")
    create_capsule(tmp_path, "demo", include=["src/**"], snapshot_id=snapshot.id)
    capsule_file = tmp_path / ".nexu" / "capsules" / "demo" / "src" / "src" / "app.py"
    capsule_file.write_text(
        capsule_file.read_text(encoding="utf-8") + "\n# approved MCP change\n",
        encoding="utf-8",
    )
    build_plan = promote.build_promotion_plan

    def build_ready_plan(root, name):
        plan = build_plan(root, name)
        plan["ready_for_apply"] = True
        return plan

    monkeypatch.setattr(promote, "build_promotion_plan", build_ready_plan)

    proposed = call_tool(
        tmp_path,
        "nexu_capsule_promote_apply",
        {"name": "demo", "actor": "reviewer"},
    )
    assert proposed["status"] == "approval_required"
    assert "# approved MCP change" not in (tmp_path / "src" / "app.py").read_text(encoding="utf-8")

    approved_content = capsule_file.read_text(encoding="utf-8")
    capsule_file.write_text(approved_content + "# changed after approval\n", encoding="utf-8")
    stale = call_tool(
        tmp_path,
        "nexu_capsule_promote_apply",
        {"name": "demo", "actor": "reviewer", "approval_hash": proposed["approval_hash"]},
    )
    assert stale["status"] == "approval_required"
    assert stale["approval_hash"] != proposed["approval_hash"]
    capsule_file.write_text(approved_content, encoding="utf-8")

    denied = call_tool(
        tmp_path,
        "nexu_capsule_promote_apply",
        {
            "name": "demo",
            "actor": "another-reviewer",
            "approval_hash": proposed["approval_hash"],
        },
    )
    assert denied["status"] == "approval_required"

    capability_blocked = call_tool(
        tmp_path,
        "nexu_capsule_promote_apply",
        {"name": "demo", "actor": "reviewer", "approval_hash": proposed["approval_hash"]},
    )
    assert capability_blocked["status"] == "approval_required"
    assert capability_blocked["required_env"] == "NEXU_MCP_ALLOW_PROMOTE"

    monkeypatch.setenv("NEXU_MCP_ALLOW_PROMOTE", "1")
    applied = call_tool(
        tmp_path,
        "nexu_capsule_promote_apply",
        {"name": "demo", "actor": "reviewer", "approval_hash": proposed["approval_hash"]},
    )
    assert applied["status"] == "success"
    assert applied["approved_by"] == "reviewer"
    assert "# approved MCP change" in (tmp_path / "src" / "app.py").read_text(encoding="utf-8")


def test_mcp_step_count_and_result_size_are_bounded(tmp_path: Path):
    plan_schema = next(tool for tool in MCP_TOOLS if tool["name"] == "nexu_capsule_plan")
    assert plan_schema["inputSchema"]["properties"]["steps"]["maximum"] == 100
    assert _bounded_steps({"steps": 10_000}, default=10) == 100

    result = _result_content({"value": "x" * 60_000})
    assert result["truncated"] is True
    assert len(result["content"][0]["text"]) < 51_000
