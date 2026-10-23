# Sovereign MCP server

Lets DeepSeek Harness, Claude Code or any MCP client drive Sovereign Creative Studio's
production pipeline. Official MCP Python SDK (`mcp` 2.3), stdio transport. It calls
Sovereign's own HTTP API, so the app's validation and ownership rules still apply.

## Install / run

```bash
python3 -m venv ~/ai/venvs/sovereign-mcp
~/ai/venvs/sovereign-mcp/bin/pip install mcp httpx
~/ai/venvs/sovereign-mcp/bin/python tools/sovereign_mcp/server.py   # Sovereign must be running
```

Environment:

| Variable | Default | Meaning |
| --- | --- | --- |
| `SOVEREIGN_API` | `http://127.0.0.1:8012` | Sovereign backend |
| `SOVEREIGN_MCP_ALLOWED_DIRS` | `$HOME:/mnt/storage/Projects` | Only files under these folders can be read or written |

DeepSeek Harness: registered as `mcp-sovereign` in `~/.dsh/profiles/web/cordis.patch.yml`.
Claude Code: `claude mcp add sovereign -- ~/ai/venvs/sovereign-mcp/bin/python /mnt/storage/Projects/sovereign-creative-studio/tools/sovereign_mcp/server.py`

## Tools

Names use underscores because several MCP clients reject dots (`sovereign.render_video` in the
original design is `sovereign_render_video` here).

| Tool | What it does | Costly (needs `confirm=true`) |
| --- | --- | --- |
| `sovereign_inspect_project` | Renderer readiness, music engine, installed enhancement models, performances | |
| `sovereign_create_avatar` | Photo avatar from a local picture | |
| `sovereign_generate_scene` | Still image (e.g. a stage) with Sovereign's image engine | |
| `sovereign_import_song` | Import a song into Music Lab | |
| `sovereign_separate_vocals` | Demucs vocals / instrumental | yes |
| `sovereign_create_performance` | New Multi-Performer Director project | |
| `sovereign_assign_performer` | Identity picture, own vocal stem, name, role, stage position | |
| `sovereign_compose_duet` | Master song, stage, mode; detect each singer's parts | |
| `sovereign_animate_performer` | Replace a performer's state timeline | |
| `sovereign_generate_lipsync` | Per-performer gated lip-sync audio | |
| `sovereign_preview_timeline` | Director sheet, camera plan, what is still missing | |
| `sovereign_render_video` | Local Wan 2.1 + InfiniteTalk render (plan + estimate first) | yes |
| `sovereign_export_project` | Save the finished video and master shot to a folder | |
| `sovereign_enhance_image` / `_audio` | Non-destructive enhancement | |
| `sovereign_enhance_video` | Non-destructive video enhancement | yes |

Nothing in this server deletes user content. Errors are returned to the agent verbatim.

## Dedicated local Harness executor

For a Harness session that exclusively owns its local Ollama executor, set
`SOVEREIGN_MCP_OLLAMA_EXECUTOR_MODEL` to the exact model name, for example
`qwen3.6:35b-a3b-coding`, in the MCP server's environment. Before a confirmed GPU
render, scene generation, stem separation or model enhancement, the server unloads
that executor with Ollama's `keep_alive: 0` request and verifies it has released
its model. The inference response containing the tool call has already completed.
Ollama can reload the executor after the tool finishes.

This is opt-in and never unloads an unrelated model: another loaded model blocks
the production with an explicit error. Configure it only for a dedicated session,
and use `wait=true` for rendering so the agent does not reload during generation
or upscaling. Other external GPU clients still require ownership coordination.
`SOVEREIGN_MCP_OLLAMA_URL` overrides the local Ollama URL. Model-release failure
blocks production instead of trying to load both large models together.

Test the release protocol without loading a model:
`~/ai/venvs/sovereign-mcp/bin/python tools/sovereign_mcp/test_executor_yield.py`.
