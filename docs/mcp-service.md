# MCP service

nexu 0.5 exposes a conservative MCP-compatible stdio service so IDE agents can call nexu operations as tools.

The service is intentionally limited:

- no shell execution,
- source-file replacement is limited to the explicit `nexu_capsule_promote_apply` tool,
- promotion requires an actor-bound approval hash for the exact capsule file contents,
- dry-run promotion planning remains available as `nexu_capsule_promote_plan`,
- LLM calls remain disabled unless `nexu.yaml` explicitly allows network calls.

## List tools

```bash
nexu mcp tools
```

## Run stdio service

```bash
nexu mcp serve --path . --transport stdio
```

This command writes only JSON-RPC responses to stdout, so it can be wired into an MCP-capable IDE/client.

## Exposed tools

Important tools:

```text
nexu_init
nexu_freeze
nexu_capsule_create
nexu_capsule_list
nexu_capsule_status
nexu_capsule_plan
nexu_capsule_blueprint
nexu_capsule_iterate
nexu_capsule_orchestrate
nexu_capsule_export_prompt
nexu_capsule_runtime
nexu_capsule_verify
nexu_capsule_review
nexu_capsule_report
nexu_capsule_promote_plan
nexu_capsule_promote_apply
```

## Resources and prompts

The service also exposes lightweight resources:

```text
nexu://config
nexu://capsules
nexu://capsules/<name>/status
```

And a prompt template:

```text
nexu_capsule_iteration
```

## Minimal JSON-RPC example

Send one line to the process stdin:

```json
{"jsonrpc":"2.0","id":1,"method":"tools/list","params":{}}
```

Call a tool:

```json
{"jsonrpc":"2.0","id":2,"method":"tools/call","params":{"name":"nexu_capsule_list","arguments":{}}}
```

## Security model

MCP tools are powerful because an external agent can trigger local operations. Treat `nexu_capsule_promote_apply` as a write-capable operation: expose it only to trusted clients and prefer `nexu_capsule_promote_plan` for review-first workflows.

- `nexu_capsule_promote_plan` creates a review plan only.
- The first `nexu_capsule_promote_apply` call returns `approval_hash` and does not
  replace source files. Review `approval_payload`, then repeat the call with a
  non-empty `actor` and the exact returned hash. The server must also be started
  with `NEXU_MCP_ALLOW_PROMOTE=1`. Any content change invalidates the hash.
- `nexu_capsule_orchestrate` uses offline mode unless the project config enables LLM network calls.
- all operations are rooted under the configured project path.
