import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from test_context_bridge import bridge, write_jsonl


class ReleaseBehaviorTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / 'project with spaces'
        self.project.mkdir()
        self.codex = self.root / 'codex'
        self.claude = self.root / 'claude'
        self.cursor = self.root / 'cursor'

    def tearDown(self):
        self.temp.cleanup()

    def cli(self, *args):
        # Every provider root is synthetic; tests never scan the user's history.
        return subprocess.run([
            sys.executable, '-B', str(bridge.__file__),
            '--codex-home', str(self.codex), '--claude-home', str(self.claude),
            '--cursor-home', str(self.cursor), *map(str, args)
        ], capture_output=True, text=True, check=False)

    def cursor_fixture(self, session_id='cursor-synthetic', cwd=None, subagent=False):
        path = self.cursor / 'projects' / 'irreversibly-encoded-name' / 'agent-transcripts' / session_id / f'{session_id}.jsonl'
        write_jsonl(path, [
            {'role': 'system', 'message': {'content': [{'type': 'text', 'text': 'SYSTEM CANARY'}]}},
            {'role': 'user', 'message': {'content': [
                {'type': 'text', 'text': '<environment_context>ENV CANARY</environment_context><user_query>Fix the synthetic cache</user_query>'},
                {'type': 'image', 'data': 'IMAGE CANARY'}]}},
            {'role': 'assistant', 'message': {'content': [
                {'type': 'text', 'text': 'The cache omits the locale.'},
                {'type': 'thinking', 'thinking': 'THINKING CANARY'},
                {'type': 'tool_use', 'name': 'Read', 'input': {'secret': 'INPUT CANARY'}}]}},
            {'role': 'tool', 'content': 'TOOL CANARY'},
            {'role': 'assistant', 'channel': 'analysis', 'content': 'ANALYSIS CANARY'},
        ])
        sidecar = self.cursor / 'chats' / 'hash' / session_id / 'meta.json'
        sidecar.parent.mkdir(parents=True)
        sidecar.write_text(json.dumps({'cwd': str(cwd or self.project), 'schemaVersion': 1, 'isSubagent': subagent}))
        return path

    def test_cursor_discovery_uses_sidecar_project_and_visible_blocks(self):
        self.cursor_fixture()
        sessions = bridge.discover_cursor(self.cursor)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0].cwd, self.project)
        digest = bridge.render_digest(sessions[0])
        self.assertIn('Fix the synthetic cache', digest)
        self.assertIn('The cache omits the locale.', digest)
        self.assertIn('Read: 1', digest)
        for canary in ['SYSTEM CANARY', 'ENV CANARY', 'IMAGE CANARY', 'THINKING CANARY', 'INPUT CANARY', 'TOOL CANARY', 'ANALYSIS CANARY']:
            self.assertNotIn(canary, digest)

    def test_cursor_unknown_project_is_not_guessed_from_encoded_name(self):
        path = self.cursor_fixture()
        next(self.cursor.glob('chats/*/*/meta.json')).unlink()
        sessions = bridge.discover_cursor(self.cursor)
        self.assertIsNone(sessions[0].cwd)
        self.assertEqual(bridge._filter_sessions(sessions, self.project, False), [])
        result = self.cli('review', '--from', 'cursor', '--input', path, '--project', self.project)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('Fix the synthetic cache', result.stdout)

    def test_cursor_conflicting_sidecars_do_not_assign_arbitrary_project(self):
        self.cursor_fixture()
        other = self.cursor / 'chats' / 'other-hash' / 'cursor-synthetic' / 'meta.json'
        other.parent.mkdir(parents=True)
        other.write_text(json.dumps({'cwd': str(self.root / 'different-project')}))
        self.assertIsNone(bridge.discover_cursor(self.cursor)[0].cwd)

    def test_cursor_subagent_is_excluded_by_default(self):
        self.cursor_fixture(subagent=True)
        self.assertEqual(bridge.discover_cursor(self.cursor), [])
        self.assertEqual(len(bridge.discover_cursor(self.cursor, include_subagents=True)), 1)

    def test_cursor_partial_final_line_and_flat_layout(self):
        path = self.cursor / 'projects' / 'encoded' / 'agent-transcripts' / 'flat.jsonl'
        write_jsonl(path, [{'role': 'user', 'message': {'content': [{'type': 'text', 'text': 'Visible request'}]}}])
        with path.open('a') as handle:
            handle.write('{"role":')
        self.assertEqual(len(bridge.discover_cursor(self.cursor)), 1)

    def test_cursor_markdown_preserves_code_and_excludes_explicit_private_sections(self):
        path = self.root / 'export.md'
        path.write_text('''# Synthetic export
**User**
Fix the example.
**Cursor**
```markdown
**User**
This line is example code.
```
<thinking>THINKING CANARY</thinking>
Visible answer.
**Tool**
TOOL CANARY
## System
SYSTEM CANARY
## User
Continue with a test.
''')
        session = bridge.parse_cursor_markdown(path, self.project)
        self.assertEqual([message.role for message in session.messages], ['user', 'assistant', 'user'])
        digest = bridge.render_digest(session)
        self.assertIn('This line is example code.', digest)
        self.assertIn('Visible answer.', digest)
        for text in ['THINKING CANARY', 'TOOL CANARY', 'SYSTEM CANARY']:
            self.assertNotIn(text, digest)

    def test_unknown_cursor_export_fails_without_writing(self):
        path = self.root / 'unsupported.md'
        path.write_text('No supported role headings here.')
        result = self.cli('review', '--from', 'cursor', '--input', path, '--project', self.project, '--output', 'auto')
        self.assertEqual(result.returncode, 2)
        self.assertIn('No supported visible messages', result.stderr)
        self.assertFalse((self.project / 'agent_state').exists())

    def test_cursor_review_and_listing_are_read_only(self):
        path = self.cursor_fixture()
        files = list(self.cursor.rglob('*'))
        before = {file: hashlib.sha256(file.read_bytes()).hexdigest() for file in files if file.is_file()}
        listing = self.cli('list', '--from', 'cursor', '--project', self.project, '--json')
        self.assertEqual(listing.returncode, 0, listing.stderr)
        self.assertEqual(json.loads(listing.stdout)[0]['session_id'], 'cursor-synthetic')
        review = self.cli('review', '--from', 'cursor', '--session', 'cursor-synthetic', '--project', self.project)
        self.assertEqual(review.returncode, 0, review.stderr)
        self.assertIn('The cache omits the locale.', review.stdout)
        after = {file: hashlib.sha256(file.read_bytes()).hexdigest() for file in self.cursor.rglob('*') if file.is_file()}
        self.assertEqual(before, after)
        self.assertFalse((self.project / 'agent_state').exists())

    def test_all_includes_three_sources_and_both_preserves_legacy_meaning(self):
        self.cursor_fixture()
        write_jsonl(self.codex / 'sessions' / 'one.jsonl', [
            {'type': 'session_meta', 'payload': {'id': 'codex-one', 'cwd': str(self.project)}},
            {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': 'Codex request'}}])
        write_jsonl(self.claude / 'projects' / 'encoded' / 'one.jsonl', [
            {'type': 'user', 'sessionId': 'claude-one', 'cwd': str(self.project), 'message': {'content': 'Claude request'}}])
        all_result = self.cli('list', '--project', self.project, '--json')
        self.assertEqual({item['provider'] for item in json.loads(all_result.stdout)}, {'claude', 'codex', 'cursor'})
        both = self.cli('list', '--from', 'both', '--project', self.project, '--json')
        self.assertEqual({item['provider'] for item in json.loads(both.stdout)}, {'claude', 'codex'})

    def test_redaction_covers_metadata_lists_and_message_text(self):
        token = 'sk-' + 'SYNTHETIC1234567890'
        session = bridge.Session('codex', 'synthetic', Path(f'/fixture/{token}.jsonl'), self.project, f'Title {token}', '', '', f'Request {token}', [bridge.Message('user', f'api_key={token}')])
        digest = bridge.render_digest(session)
        data = json.dumps(bridge._session_json(session, self.project))
        self.assertNotIn(token, digest)
        self.assertNotIn(token, data)
        self.assertIn(token, bridge.render_digest(session, redact=False))

    def test_list_cli_redacts_title_and_first_request(self):
        token = 'sk-' + 'SYNTHETIC1234567890'
        path = self.codex / 'sessions' / 'synthetic.jsonl'
        write_jsonl(path, [
            {'type': 'session_meta', 'payload': {'id': 'synthetic', 'cwd': str(self.project)}},
            {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': f'Fix api_key={token}'}}])
        write_jsonl(self.codex / 'session_index.jsonl', [{'id': 'synthetic', 'thread_name': f'Title {token}'}])
        for extra in [[], ['--json']]:
            result = self.cli('list', '--from', 'codex', '--project', self.project, *extra)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertNotIn(token, result.stdout)
            self.assertIn('[REDACTED]', result.stdout)

    def test_redaction_happens_before_title_truncation(self):
        token = 'sk-' + 'SYNTHETIC1234567890' * 20
        path = self.codex / 'sessions' / 'synthetic.jsonl'
        write_jsonl(path, [
            {'type': 'session_meta', 'payload': {'id': 'synthetic', 'cwd': str(self.project)}},
            {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': 'x' * 83 + ' ' + token}}])
        session = bridge.parse_codex_session(path, {})
        self.assertNotIn('sk-SYN', session.title)

    def test_codex_fallback_excludes_analysis_and_non_text_content(self):
        path = self.codex / 'sessions' / 'older.jsonl'
        write_jsonl(path, [
            {'type': 'session_meta', 'payload': {'id': 'older', 'cwd': str(self.project)}},
            {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'channel': 'analysis', 'content': [{'type': 'output_text', 'text': 'ANALYSIS CANARY'}]}},
            {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'channel': 'final', 'content': [{'type': 'output_text', 'text': 'Visible answer'}, {'type': 'reasoning', 'text': 'REASONING CANARY'}]}}])
        digest = bridge.render_digest(bridge.parse_codex_session(path, {}))
        self.assertIn('Visible answer', digest)
        self.assertNotIn('ANALYSIS CANARY', digest)
        self.assertNotIn('REASONING CANARY', digest)

    def test_current_codex_subagent_source_is_excluded(self):
        write_jsonl(self.codex / 'sessions' / 'subagent.jsonl', [
            {'type': 'session_meta', 'payload': {'id': 'subagent', 'cwd': str(self.project), 'source': {'subagent': {'thread_spawn': {}}}}}])
        self.assertEqual(bridge.discover_codex(self.codex), [])

    def test_explicit_session_cannot_silently_escape_project_scope(self):
        self.cursor_fixture(cwd=self.root / 'unrelated')
        result = self.cli('review', '--from', 'cursor', '--session', 'cursor-synthetic', '--project', self.project)
        self.assertEqual(result.returncode, 2)
        permitted = self.cli('review', '--from', 'cursor', '--session', 'cursor-synthetic', '--project', self.project, '--all-projects')
        self.assertEqual(permitted.returncode, 0, permitted.stderr)

    def test_exact_id_wins_and_ambiguous_prefix_is_rejected(self):
        sessions = [bridge.Session('codex', value, Path('synthetic'), self.project, '', '', '') for value in ['abc', 'abcdef', 'abcghi']]
        self.assertEqual(bridge._select_session(sessions, 'abc').session_id, 'abc')
        with self.assertRaisesRegex(LookupError, 'ambiguous'):
            bridge._select_session(sessions, 'ab')

    def test_review_does_not_default_to_latest(self):
        result = self.cli('review', '--from', 'cursor', '--project', self.project)
        self.assertEqual(result.returncode, 2)
        self.assertIn('explicit --session', result.stderr)

    def test_invalid_limits_and_missing_files_return_errors(self):
        self.cursor_fixture()
        for args in [
            ['list', '--limit', '0'],
            ['review', '--from', 'cursor', '--session', 'cursor-synthetic', '--project', self.project, '--max-chars', '0'],
            ['review', '--from', 'cursor', '--input', self.root / 'missing.md'],
            ['review', '--from', 'claude', '--input', self.root / 'missing.md'],
        ]:
            with self.subTest(args=args):
                result = self.cli(*args)
                self.assertEqual(result.returncode, 2)
                self.assertNotIn('Traceback', result.stderr)

    def test_auto_output_sanitizes_session_id_and_creates_private_file(self):
        session = bridge.Session('cursor', '../../escape', Path('synthetic'), self.project, '', '', '')
        output = bridge._write_output('synthetic digest', 'auto', self.project, session)
        self.assertEqual(output.parent, self.project / 'agent_state' / 'context_bridge')
        self.assertEqual(output.read_text(), 'synthetic digest')
        if os.name == 'posix':
            self.assertEqual(stat.S_IMODE(output.stat().st_mode), 0o600)
        self.assertEqual(list(output.parent.glob('.context-bridge-*')), [])

    def test_auto_output_cli_requires_explicit_output(self):
        path = self.cursor_fixture()
        result = self.cli('review', '--from', 'cursor', '--input', path, '--project', self.project, '--output', 'auto')
        self.assertEqual(result.returncode, 0, result.stderr)
        destination = Path(result.stdout.strip())
        self.assertTrue(destination.is_file())
        self.assertIn('Fix the synthetic cache', destination.read_text())

    def test_character_budget_limits_conversation_payload(self):
        session = bridge.Session('codex', 'synthetic', Path('synthetic'), self.project, '', '', '', messages=[bridge.Message('user', 'A' * 1000), bridge.Message('assistant', 'B' * 1000)])
        digest = bridge.render_digest(session, max_chars=30)
        conversation = digest.split('## Conversation\n', 1)[1].split('## Incoming-agent checklist', 1)[0]
        payload_size = sum(len(match) for match in re.findall(r'(?m)^[AB]+$', conversation))
        self.assertLessEqual(payload_size, 30)
        self.assertIn('[Message truncated]', digest)

    def test_malformed_codex_content_and_project_metadata_are_ignored(self):
        path = self.codex / 'sessions' / 'malformed.jsonl'
        write_jsonl(path, [
            {'type': 'session_meta', 'payload': {'id': 'malformed', 'cwd': 123}},
            {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'content': None}},
            {'type': 'response_item', 'payload': {'type': 'message', 'role': 'assistant', 'content': 7}},
            {'type': 'event_msg', 'payload': {'type': 'user_message', 'message': 'Visible request'}},
        ])
        result = self.cli('list', '--from', 'codex', '--all-projects', '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)[0]['cwd'], None)
        self.assertEqual(json.loads(result.stdout)[0]['first_request'], 'Visible request')

    def test_empty_source_listing_is_valid_json(self):
        result = self.cli('list', '--project', self.project, '--json')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), [])


if __name__ == '__main__':
    unittest.main()
