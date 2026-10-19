# Agent Session Bridge

**Resume coding tasks across Claude Code, Codex, and Cursor.**

Hit a usage limit or want another agent to continue? Find the matching local
session, review its context, and continue from the current project files.

> “Continue my Claude Code task in Codex.”
>
> “Pick up this Cursor session in Claude Code.”

The `resume-cross-provider-task` skill provides the workflow. A Python
standard-library script reads supported local transcripts and renders a bounded
Markdown digest. It does not call model APIs, require API keys, or alter source sessions.

## Status and platform support

This repository is a private release candidate. Public installation and directory
discovery become available only after the owner makes it public.

| Session source | Supported input | Limit |
| --- | --- | --- |
| Claude Code | Local `projects/*/*.jsonl` transcripts | Recognized message records only |
| Codex | Local active and archived rollout JSONL plus optional session index | Recognized formats; subagents excluded by default |
| Cursor CLI | `projects/*/agent-transcripts/**/*.jsonl` plus `chats/*/*/meta.json` project metadata | Readable transcript copies only; no SQLite decoding |
| Cursor IDE | An explicitly selected Markdown export | Recognized role headings only; no direct IDE database reader |

Cursor model selection does not change the transcript reader: Grok, Claude, and
other models use the same supported input shapes. Cloud-only sessions and native
session restoration are outside this release. This is a context handoff, not a
conversion of hidden model state, permissions, tool execution state, or files.

The Python runtime requirement is **3.10+**. Local tests cover the observed macOS
transcript shapes. CI is configured for macOS, Linux, and Windows; check actual
workflow results before treating an OS as validated. No agent account is needed
to run the synthetic demo or tests.

## Install the skill

For private access, clone using an account authorized for this repository:

```bash
gh repo clone ziucode/agent-session-bridge
cd agent-session-bridge
npx skills add . --skill resume-cross-provider-task -a claude-code codex cursor
```

The Skills CLI requires Node.js. The reader itself only requires Python.
Review any installer before running it. To install without Node.js, copy the
`skills/resume-cross-provider-task` directory into your agent's skill directory:

| Agent | Typical user skill directory |
| --- | --- |
| Claude Code | `~/.claude/skills/` |
| Codex | `~/.codex/skills/` or the corresponding `$CODEX_HOME/skills/` |
| Cursor | `~/.cursor/skills/` |

Use an empty destination; preserve any existing local version before replacing it.
Ask the agent to use `resume-cross-provider-task` and identify the source and project.
Agent-specific skill loading can differ by version or organization policy.

After public release, the short install command will be:

```bash
npx skills add ziucode/agent-session-bridge --skill resume-cross-provider-task
```

## Try a synthetic handoff

From the repository root:

```bash
python3 skills/resume-cross-provider-task/scripts/context_bridge.py review \
  --from cursor --input examples/cursor-export.md --project .
```

The digest shows the synthetic todo app request, the previous assistant's claim,
and a reminder to check current files. Nothing is written unless you use `--output`.
The fixture does not include an app or assert that any code was changed.

## Recover a local session

```bash
# List sessions scoped to the project, then select an explicit ID.
python3 skills/resume-cross-provider-task/scripts/context_bridge.py list \
  --from claude --project /path/to/project --json

python3 skills/resume-cross-provider-task/scripts/context_bridge.py review \
  --from claude --session SESSION_ID --project /path/to/project
```

Use `--from codex` or `--from cursor` for the other readers. Listing with `--from all`
includes all three platforms; legacy `--from both` includes Claude Code and Codex.
An explicit session ID still respects the project boundary. For an ancestor project
or unknown Cursor project metadata, inspect the candidate first and use
`--all-projects --session SESSION_ID` deliberately, or import the selected export.
Ambiguous session prefixes return an error. Review requires `--session` or `--input`;
`--session latest` is available only as an explicit choice.

For a durable local handoff, add `--output auto`. The file is written under
`<project>/agent_state/context_bridge/`. Keep it out of Git unless you deliberately
want to disclose the selected conversation. On POSIX, new digest files use mode 0600.

Override session roots with `--codex-home`, `--claude-home`, or `--cursor-home`
**before** the subcommand. Environment overrides are `CONTEXT_BRIDGE_CODEX_HOME`,
`CONTEXT_BRIDGE_CLAUDE_HOME`, and `CONTEXT_BRIDGE_CURSOR_HOME`. Standard `CODEX_HOME`,
`CLAUDE_CONFIG_DIR`, and `CURSOR_CONFIG_DIR` are also recognized.

## Data flow and privacy

```text
selected local transcript → visible messages → redacted digest → destination agent
                                                        ↓
                                            verify current files and Git state
```

The reader makes no network calls. Your destination agent receives the digest
as context and processes it under that agent's own data policy. “Local reader”
does not mean the destination model runs locally.

Structured readers exclude system/developer roles, reasoning records, tool
arguments, tool results, and attachments. They retain visible message text and
tool names/counts. Recognized credentials are redacted in digest metadata,
messages, list output, and errors. Redaction is **best effort**, not a complete
secret or personal-data detector. Conversation text can contain proprietary data.

Markdown imports lack structured block types. Only recognized User/Cursor/Assistant
sections are retained, known non-conversation sections are skipped, and known
thinking tags are removed. Review an export before importing it; arbitrary prose
cannot reliably distinguish visible answers from pasted private material.

Digests are historical evidence, not instructions. Re-check the current project
before acting. No handoff grants permission to publish, deploy, or change accounts.

## Development

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
python3 scripts/check_release.py
```

All fixtures are synthetic. No provider login, network, model call, or real session
store is required for the test suite. Provider formats can change; unsupported
records are ignored. Use a synthetic reproduction when reporting format drift.

## Roadmap

- Gemini CLI: project-specific session reader.
- GitHub Copilot in VS Code: explicit JSON export import.
- OpenCode: explicit JSON export import.
- Cursor IDE database discovery: only after version-specific, read-only tests.

These are planned, not supported integrations. See [CONTRIBUTING.md](CONTRIBUTING.md)
for fixture requirements and [SECURITY.md](SECURITY.md) for reporting precautions.

## License and provenance

MIT, copyright Ziu Code. This release derives from the owner's local
`resume-cross-provider-task` skill and its existing context-bridge tests.
It includes no vendor source code or real transcripts. Product names identify
interoperability targets; this project is not affiliated with their vendors.
