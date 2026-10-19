import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(
    os.environ.get("CONTEXT_BRIDGE_MODULE", Path(__file__).parents[1] / "skills/resume-cross-provider-task/scripts/context_bridge.py")
)
SPEC = importlib.util.spec_from_file_location("context_bridge", MODULE_PATH)
bridge = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = bridge
SPEC.loader.exec_module(bridge)


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")


class ContextBridgeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.project = self.root / "workspace" / "project"
        self.project.mkdir(parents=True)
        self.codex_home = self.root / "codex"
        self.claude_home = self.root / "claude"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_codex_digest_uses_visible_events_and_excludes_private_records(self) -> None:
        session_id = "11111111-2222-3333-4444-555555555555"
        path = self.codex_home / "sessions" / "2026" / "07" / "15" / f"rollout-{session_id}.jsonl"
        write_jsonl(
            path,
            [
                {
                    "type": "session_meta",
                    "timestamp": "2026-07-15T01:00:00Z",
                    "payload": {"id": session_id, "cwd": str(self.project)},
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-07-15T01:00:01Z",
                    "payload": {"type": "message", "role": "developer", "content": [{"text": "PRIVATE SYSTEM"}]},
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-07-15T01:00:02Z",
                    "payload": {"type": "user_message", "message": "Fix the parser. api_key=super-secret-value"},
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-07-15T01:00:03Z",
                    "payload": {"type": "reasoning", "summary": "PRIVATE REASONING"},
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-07-15T01:00:04Z",
                    "payload": {"type": "custom_tool_call", "name": "exec_command", "input": "PRIVATE COMMAND"},
                },
                {
                    "type": "response_item",
                    "timestamp": "2026-07-15T01:00:05Z",
                    "payload": {"type": "custom_tool_call_output", "output": "PRIVATE OUTPUT"},
                },
                {
                    "type": "event_msg",
                    "timestamp": "2026-07-15T01:00:06Z",
                    "payload": {"type": "agent_message", "message": "I found the failing branch."},
                },
            ],
        )
        write_jsonl(
            self.codex_home / "session_index.jsonl",
            [{"id": session_id, "thread_name": "Fix parser", "updated_at": "2026-07-15T01:01:00Z"}],
        )

        sessions = bridge.discover_codex(self.codex_home)
        self.assertEqual(len(sessions), 1)
        digest = bridge.render_digest(sessions[0])
        self.assertIn("Fix the parser", digest)
        self.assertIn("I found the failing branch", digest)
        self.assertIn("exec_command: 1", digest)
        self.assertIn("api_key=[REDACTED]", digest)
        for private_text in ("PRIVATE SYSTEM", "PRIVATE REASONING", "PRIVATE COMMAND", "PRIVATE OUTPUT"):
            self.assertNotIn(private_text, digest)

    def test_claude_digest_excludes_tool_results_meta_and_thinking(self) -> None:
        session_id = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        path = self.claude_home / "projects" / "encoded-project" / f"{session_id}.jsonl"
        write_jsonl(
            path,
            [
                {
                    "type": "user",
                    "sessionId": session_id,
                    "cwd": str(self.project),
                    "timestamp": "2026-07-15T02:00:00Z",
                    "message": {"role": "user", "content": [{"type": "text", "text": "Continue the report"}]},
                },
                {"type": "ai-title", "sessionId": session_id, "aiTitle": "Continue report"},
                {
                    "type": "assistant",
                    "sessionId": session_id,
                    "cwd": str(self.project),
                    "timestamp": "2026-07-15T02:00:01Z",
                    "message": {
                        "role": "assistant",
                        "content": [
                            {"type": "thinking", "thinking": "PRIVATE THINKING"},
                            {"type": "text", "text": "I will inspect the draft."},
                            {"type": "tool_use", "name": "Read", "input": {"file_path": "secret.txt"}},
                        ],
                    },
                },
                {
                    "type": "user",
                    "sessionId": session_id,
                    "cwd": str(self.project),
                    "sourceToolAssistantUUID": "tool-id",
                    "message": {"role": "user", "content": [{"type": "tool_result", "content": "PRIVATE RESULT"}]},
                },
                {
                    "type": "user",
                    "sessionId": session_id,
                    "cwd": str(self.project),
                    "isMeta": True,
                    "message": {"role": "user", "content": [{"type": "text", "text": "PRIVATE META"}]},
                },
            ],
        )

        sessions = bridge.discover_claude(self.claude_home)
        self.assertEqual(len(sessions), 1)
        digest = bridge.render_digest(sessions[0])
        self.assertIn("Continue the report", digest)
        self.assertIn("I will inspect the draft", digest)
        self.assertIn("Read: 1", digest)
        for private_text in ("PRIVATE THINKING", "PRIVATE RESULT", "PRIVATE META", "secret.txt"):
            self.assertNotIn(private_text, digest)

    def test_claude_filename_wins_over_parent_queue_metadata(self) -> None:
        session_id = "12345678-1111-2222-3333-444444444444"
        parent_id = "87654321-9999-8888-7777-666666666666"
        path = self.claude_home / "projects" / "encoded-project" / f"{session_id}.jsonl"
        write_jsonl(
            path,
            [
                {"type": "queue-operation", "sessionId": parent_id, "timestamp": "2026-07-15T01:00:00Z"},
                {
                    "type": "user",
                    "sessionId": session_id,
                    "cwd": str(self.project),
                    "timestamp": "2026-07-15T01:00:01Z",
                    "message": {"content": [{"type": "text", "text": "Branched request"}]},
                },
            ],
        )
        session = bridge.parse_claude_session(path)
        self.assertIsNotNone(session)
        self.assertEqual(session.session_id, session_id)

    def test_codex_discovery_prefers_active_copy_over_archive(self) -> None:
        session_id = "99999999-2222-3333-4444-555555555555"
        rows = [
            {
                "type": "session_meta",
                "timestamp": "2026-07-15T01:00:00Z",
                "payload": {"id": session_id, "cwd": str(self.project)},
            }
        ]
        active = self.codex_home / "sessions" / "2026" / "07" / "15" / f"rollout-{session_id}.jsonl"
        archived = self.codex_home / "archived_sessions" / f"rollout-{session_id}.jsonl"
        write_jsonl(active, rows)
        write_jsonl(archived, rows)
        sessions = bridge.discover_codex(self.codex_home)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].path, active)

    def test_codex_discovery_excludes_subagent_rollouts_by_default(self) -> None:
        session_id = "77777777-2222-3333-4444-555555555555"
        path = self.codex_home / "sessions" / "2026" / "07" / "15" / f"rollout-{session_id}.jsonl"
        write_jsonl(
            path,
            [
                {
                    "type": "session_meta",
                    "timestamp": "2026-07-15T01:00:00Z",
                    "payload": {
                        "id": session_id,
                        "cwd": str(self.project),
                        "thread_source": "subagent",
                    },
                }
            ],
        )
        self.assertEqual(bridge.discover_codex(self.codex_home), [])
        self.assertEqual(
            [item.session_id for item in bridge.discover_codex(self.codex_home, include_subagents=True)],
            [session_id],
        )

    def test_project_scope_and_explicit_session_selection(self) -> None:
        inside = bridge.Session(
            "codex", "abc123", Path("inside.jsonl"), self.project, "Inside", "", "2026-07-15T03:00:00Z"
        )
        nested = bridge.Session(
            "claude", "def456", Path("nested.jsonl"), self.project / "nested", "Nested", "", "2026-07-15T04:00:00Z"
        )
        outside = bridge.Session(
            "claude", "xyz789", Path("outside.jsonl"), self.root / "other", "Outside", "", "2026-07-15T05:00:00Z"
        )
        filtered = bridge._filter_sessions([inside, outside, nested], self.project, False)
        self.assertEqual([item.session_id for item in filtered], ["def456", "abc123"])
        self.assertEqual(bridge._select_session(filtered, "abc").session_id, "abc123")

    def test_long_context_keeps_the_opening_and_recent_messages(self) -> None:
        messages = [bridge.Message("user" if index % 2 == 0 else "assistant", f"message-{index}") for index in range(20)]
        selected, omitted = bridge._select_messages(messages, max_messages=6, max_chars=1000)
        self.assertEqual([item.text for item in selected[:2]], ["message-0", "message-1"])
        self.assertEqual(selected[-1].text, "message-19")
        self.assertEqual(omitted, 14)


if __name__ == "__main__":
    unittest.main()
