from __future__ import annotations

import hashlib
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from . import __version__
from .blueprint import build_blueprint
from .capsule import create_capsule, list_capsules
from .export_prompt import export_iteration_prompt
from .freeze import freeze_project
from .init_project import init_project
from .iterate import iterate_capsule
from .orchestrate import build_capsule_orchestration
from .plan import build_iteration_plan
from .promote import build_promotion_plan
from .report import build_capsule_report
from .review import build_review_packet
from .runtime import build_capsule_runtime
from .status import capsule_status
from .verify import verify_capsule


def _schema(properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
    return {"type": "object", "properties": properties, "required": required or []}


MIME_JSON = "application/json"
MIME_YAML = "application/yaml"


ToolHandler = Callable[[Path, dict[str, Any]], Any]
_MAX_STEPS = 100
_MAX_RESULT_CHARS = 50_000
_MCP_PROMOTE_ENV = "NEXU_MCP_ALLOW_PROMOTE"


def _bounded_steps(arguments: dict[str, Any], *, default: int) -> int:
    return max(1, min(int(arguments.get("steps") or default), _MAX_STEPS))


def _approval_hash(action: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        {"action": action, "payload": payload},
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _promotion_enabled() -> bool:
    return os.getenv(_MCP_PROMOTE_ENV, "").strip().lower() in {"1", "true", "yes", "on"}


TOOL_SPECS: list[dict[str, Any]] = [
    {
        "name": "nexu_init",
        "description": "Initialize nexu.yaml, intract.yaml and .nexu folders in the project root.",
        "inputSchema": _schema({}),
        "handler": lambda root, args: {"created": [str(p) for p in init_project(root)]},
    },
    {
        "name": "nexu_freeze",
        "description": "Create a lightweight hash snapshot of selected project files.",
        "inputSchema": _schema(
            {
                "name": {"type": "string", "default": "baseline"},
                "include": {"type": "array", "items": {"type": "string"}},
            }
        ),
        "handler": lambda root, args: freeze_project(
            root,
            name=str(args.get("name") or "baseline"),
            include=args.get("include"),
        ).to_dict(),
    },
    {
        "name": "nexu_capsule_create",
        "description": (
            "Create an isolated project capsule from selected files, routes and endpoints."
        ),
        "inputSchema": _schema(
            {
                "name": {"type": "string"},
                "domain": {"type": "string", "default": "general"},
                "include": {"type": "array", "items": {"type": "string"}},
                "routes": {"type": "array", "items": {"type": "string"}},
                "endpoints": {"type": "array", "items": {"type": "string"}},
                "snapshot_id": {"type": "string"},
            },
            ["name"],
        ),
        "handler": lambda root, args: create_capsule(
            root,
            str(args["name"]),
            domain=str(args.get("domain") or "general"),
            include=args.get("include"),
            routes=args.get("routes"),
            endpoints=args.get("endpoints"),
            snapshot_id=args.get("snapshot_id"),
        ).to_dict(),
    },
    {
        "name": "nexu_capsule_list",
        "description": "List local nexu capsules.",
        "inputSchema": _schema({}),
        "handler": lambda root, args: {"capsules": list_capsules(root)},
    },
    {
        "name": "nexu_capsule_status",
        "description": (
            "Return capsule status, latest iteration, diff counters and verification summary."
        ),
        "inputSchema": _schema({"name": {"type": "string"}}, ["name"]),
        "handler": lambda root, args: capsule_status(root, str(args["name"])),
    },
    {
        "name": "nexu_capsule_plan",
        "description": "Create deterministic S1..Sn iteration plan for a capsule.",
        "inputSchema": _schema(
            {
                "name": {"type": "string"},
                "steps": {"type": "integer", "minimum": 1, "maximum": _MAX_STEPS, "default": 10},
                "goal": {"type": "string", "default": ""},
            },
            ["name"],
        ),
        "handler": lambda root, args: build_iteration_plan(
            root,
            str(args["name"]),
            steps=_bounded_steps(args, default=10),
            goal=str(args.get("goal") or ""),
        ),
    },
    {
        "name": "nexu_capsule_blueprint",
        "description": (
            "Generate UI/API/test blueprint from capsule selection and Intract contracts."
        ),
        "inputSchema": _schema({"name": {"type": "string"}}, ["name"]),
        "handler": lambda root, args: build_blueprint(root, str(args["name"])),
    },
    {
        "name": "nexu_capsule_iterate",
        "description": "Create planned iteration folders and prompts inside a capsule.",
        "inputSchema": _schema(
            {
                "name": {"type": "string"},
                "steps": {"type": "integer", "minimum": 1, "maximum": _MAX_STEPS, "default": 1},
                "goal": {"type": "string", "default": "Evolve capsule safely."},
            },
            ["name"],
        ),
        "handler": lambda root, args: {
            "created": iterate_capsule(
                root,
                str(args["name"]),
                steps=_bounded_steps(args, default=1),
                goal=str(args.get("goal") or "Evolve capsule safely."),
            )
        },
    },
    {
        "name": "nexu_capsule_orchestrate",
        "description": (
            "Build offline or LLM-assisted orchestration plan for safe capsule evolution."
        ),
        "inputSchema": _schema(
            {
                "name": {"type": "string"},
                "steps": {"type": "integer", "minimum": 1, "maximum": _MAX_STEPS, "default": 10},
                "goal": {"type": "string", "default": ""},
                "call_llm": {"type": "boolean", "default": False},
                "model": {"type": "string"},
            },
            ["name"],
        ),
        "handler": lambda root, args: build_capsule_orchestration(
            root,
            str(args["name"]),
            steps=_bounded_steps(args, default=10),
            goal=str(args.get("goal") or ""),
            call_llm=bool(args.get("call_llm", False)),
            model=args.get("model"),
        ),
    },
    {
        "name": "nexu_capsule_export_prompt",
        "description": (
            "Export an LLM-ready iteration prompt constrained by contracts and blueprint."
        ),
        "inputSchema": _schema(
            {"name": {"type": "string"}, "iteration": {"type": "string"}}, ["name"]
        ),
        "handler": lambda root, args: export_iteration_prompt(
            root,
            str(args["name"]),
            iteration=args.get("iteration"),
        ).to_dict(),
    },
    {
        "name": "nexu_capsule_runtime",
        "description": "Build a static HTML runtime/mock for the capsule.",
        "inputSchema": _schema({"name": {"type": "string"}}, ["name"]),
        "handler": lambda root, args: build_capsule_runtime(root, str(args["name"])),
    },
    {
        "name": "nexu_capsule_verify",
        "description": "Verify capsule against deterministic intent-contract gates.",
        "inputSchema": _schema({"name": {"type": "string"}}, ["name"]),
        "handler": lambda root, args: verify_capsule(root, str(args["name"])).to_dict(),
    },
    {
        "name": "nexu_capsule_review",
        "description": (
            "Build evidence-based review packet. LLM review is optional and disabled by default."
        ),
        "inputSchema": _schema(
            {
                "name": {"type": "string"},
                "iteration": {"type": "string"},
                "call_llm": {"type": "boolean", "default": False},
                "model": {"type": "string"},
            },
            ["name"],
        ),
        "handler": lambda root, args: build_review_packet(
            root,
            str(args["name"]),
            iteration=args.get("iteration"),
            call_llm=bool(args.get("call_llm", False)),
            model=args.get("model"),
        ),
    },
    {
        "name": "nexu_capsule_report",
        "description": "Build Markdown/HTML/YAML capsule report with evidence.",
        "inputSchema": _schema({"name": {"type": "string"}}, ["name"]),
        "handler": lambda root, args: build_capsule_report(root, str(args["name"])),
    },
    {
        "name": "nexu_capsule_promote_plan",
        "description": "Build dry-run promotion plan. This tool never applies file changes.",
        "inputSchema": _schema({"name": {"type": "string"}}, ["name"]),
        "handler": lambda root, args: build_promotion_plan(root, str(args["name"])),
    },
    {
        "name": "nexu_capsule_promote_apply",
        "description": "Apply an exact promotion plan after actor-bound hash approval.",
        "inputSchema": _schema(
            {
                "name": {"type": "string"},
                "actor": {"type": "string", "description": "Human or system approving the change."},
                "approval_hash": {
                    "type": "string",
                    "description": (
                        "Exact hash returned by the preceding approval-required response."
                    ),
                },
            },
            ["name"],
        ),
        "handler": lambda root, args: _apply_promotion_from_mcp(
            root,
            str(args["name"]),
            actor=str(args.get("actor") or ""),
            approval_hash=str(args.get("approval_hash") or ""),
        ),
    },
]


def _promotion_approval_payload(root: Path, plan: dict[str, Any]) -> dict[str, Any]:
    from .paths import capsule_dir

    base = capsule_dir(root, str(plan["capsule"]))
    files: list[dict[str, str]] = []
    for item in plan.get("promotion_map", []):
        source = base / str(item["capsule_path"])
        content_hash = hashlib.sha256(source.read_bytes()).hexdigest() if source.is_file() else ""
        files.append(
            {
                "capsule_path": str(item["capsule_path"]),
                "target_path": str(item["target_path"]),
                "content_sha256": content_hash,
            }
        )
    return {
        "capsule": str(plan["capsule"]),
        "source_project_root": str(root.resolve()),
        "files": files,
    }


def _apply_promotion_from_mcp(
    root: Path,
    name: str,
    *,
    actor: str = "",
    approval_hash: str = "",
) -> dict[str, Any]:
    from .promote import apply_promotion_plan, build_promotion_plan

    plan = build_promotion_plan(root, name)
    if not plan.get("ready_for_apply"):
        return {
            "status": "blocked",
            "requires_approval": False,
            "prechecks": plan.get("prechecks", {}),
            "blocked_by": plan.get("blocked_by", []),
            "message": "Promotion prechecks failed; fix verification or source drift first.",
        }
    payload = _promotion_approval_payload(root, plan)
    normalized_actor = actor.strip()
    expected_hash = _approval_hash(
        "nexu_capsule_promote_apply",
        {**payload, "actor": normalized_actor},
    )
    if not _promotion_enabled() or not normalized_actor or approval_hash.strip() != expected_hash:
        return {
            "status": "approval_required",
            "requires_approval": True,
            "approval_hash": expected_hash,
            "approval_payload": payload,
            "required_env": _MCP_PROMOTE_ENV,
            "message": (
                f"Review the exact file hashes, enable {_MCP_PROMOTE_ENV}=1, then repeat "
                "with actor and approval_hash."
            ),
        }
    apply_promotion_plan(root, plan)
    return {
        "status": "success",
        "requires_approval": False,
        "approved_by": normalized_actor,
        "approval_hash": expected_hash,
        "files_applied": len(payload["files"]),
        "message": f"Applied promotion plan for capsule {name}",
    }


MCP_TOOLS: list[dict[str, Any]] = [
    {key: value for key, value in spec.items() if key != "handler"} for spec in TOOL_SPECS
]


TOOL_HANDLERS: dict[str, ToolHandler] = {str(spec["name"]): spec["handler"] for spec in TOOL_SPECS}


def _bind_tool(root: Path, handler: ToolHandler) -> Callable[[dict[str, Any]], Any]:
    return lambda arguments: handler(root, arguments)


def _tool_map(root: Path) -> dict[str, Callable[[dict[str, Any]], Any]]:
    return {name: _bind_tool(root, handler) for name, handler in TOOL_HANDLERS.items()}


def call_tool(root: Path, tool_name: str, arguments: dict[str, Any] | None = None) -> Any:
    tools = _tool_map(root)
    if tool_name not in tools:
        raise KeyError(f"Unknown nexu MCP tool: {tool_name}")
    return tools[tool_name](arguments or {})


def _result_content(data: Any) -> dict[str, Any]:
    text = json.dumps(data, indent=2, ensure_ascii=False, default=str)
    truncated = len(text) > _MAX_RESULT_CHARS
    if truncated:
        text = text[:_MAX_RESULT_CHARS] + "\n... MCP response truncated ..."
    return {
        "content": [
            {
                "type": "text",
                "text": text,
            }
        ],
        "truncated": truncated,
    }


def _resource_list(root: Path) -> list[dict[str, str]]:
    resources = [
        {"uri": "nexu://config", "name": "nexu project config", "mimeType": MIME_YAML},
        {"uri": "nexu://capsules", "name": "nexu capsule list", "mimeType": MIME_JSON},
    ]
    for name in list_capsules(root):
        resources.append(
            {
                "uri": f"nexu://capsules/{name}/status",
                "name": f"Capsule status: {name}",
                "mimeType": MIME_JSON,
            }
        )
    return resources


def _read_resource(root: Path, uri: str) -> dict[str, Any]:
    if uri == "nexu://config":
        path = root / "nexu.yaml"
        text = path.read_text(encoding="utf-8") if path.exists() else ""
        return {"contents": [{"uri": uri, "mimeType": MIME_YAML, "text": text}]}
    if uri == "nexu://capsules":
        return {
            "contents": [
                {"uri": uri, "mimeType": MIME_JSON, "text": json.dumps(list_capsules(root))}
            ]
        }
    prefix = "nexu://capsules/"
    if uri.startswith(prefix) and uri.endswith("/status"):
        name = uri[len(prefix) : -len("/status")]
        text = json.dumps(capsule_status(root, name), indent=2, ensure_ascii=False)
        return {"contents": [{"uri": uri, "mimeType": MIME_JSON, "text": text}]}
    raise KeyError(f"Unknown nexu resource: {uri}")


def _prompts_list() -> list[dict[str, Any]]:
    return [
        {
            "name": "nexu_capsule_iteration",
            "description": "Prompt template for one safe capsule iteration.",
            "arguments": [
                {"name": "capsule", "description": "Capsule name", "required": True},
                {"name": "goal", "description": "Iteration goal", "required": False},
            ],
        }
    ]


def _prompt_get(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    if name != "nexu_capsule_iteration":
        raise KeyError(f"Unknown prompt: {name}")
    args = arguments or {}
    capsule = args.get("capsule", "<capsule>")
    goal = args.get("goal", "Evolve the capsule safely.")
    return {
        "description": "Safe nexu capsule iteration prompt",
        "messages": [
            {
                "role": "user",
                "content": {
                    "type": "text",
                    "text": (
                        f"Work only inside nexu capsule `{capsule}`. Goal: {goal}. "
                        "Preserve Intract contracts, leave evidence for outputs, and run "
                        "verification before promotion."
                    ),
                },
            }
        ],
    }


def _rpc_initialize(params: dict[str, Any]) -> dict[str, Any]:
    return {
        "protocolVersion": params.get("protocolVersion", "2024-11-05"),
        "serverInfo": {"name": "nexu", "version": __version__},
        "capabilities": {"tools": {}, "resources": {}, "prompts": {}},
    }


def _rpc_handlers(root: Path) -> dict[str, Callable[[dict[str, Any]], dict[str, Any]]]:
    return {
        "initialize": lambda params: _rpc_initialize(params),
        "tools/list": lambda params: {"tools": MCP_TOOLS},
        "tools/call": lambda params: _result_content(
            call_tool(root, str(params.get("name")), params.get("arguments") or {})
        ),
        "resources/list": lambda params: {"resources": _resource_list(root)},
        "resources/read": lambda params: _read_resource(root, str(params.get("uri"))),
        "prompts/list": lambda params: {"prompts": _prompts_list()},
        "prompts/get": lambda params: _prompt_get(
            str(params.get("name")), params.get("arguments") or {}
        ),
        "ping": lambda params: {},
    }


def handle_mcp_message(root: Path, message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    msg_id = message.get("id")
    params = message.get("params") or {}
    try:
        if method == "notifications/initialized":
            return None
        handlers = _rpc_handlers(root)
        handler = handlers.get(str(method))
        if handler is None:
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "error": {"code": -32601, "message": f"Method not found: {method}"},
            }
        result = handler(params)
        return {"jsonrpc": "2.0", "id": msg_id, "result": result}
    except Exception as exc:
        return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32000, "message": str(exc)}}


def run_mcp_stdio(root: Path) -> None:
    """Run a minimal MCP-compatible JSON-RPC stdio service.

    The implementation exposes tools, resources and prompts without shelling out.
    Source promotion requires an actor-bound approval of the exact file hashes.
    """
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except json.JSONDecodeError as exc:
            response = {
                "jsonrpc": "2.0",
                "id": None,
                "error": {"code": -32700, "message": str(exc)},
            }
        else:
            response = handle_mcp_message(root, message)
        if response is not None:
            sys.stdout.write(json.dumps(response, ensure_ascii=False) + "\n")
            sys.stdout.flush()
