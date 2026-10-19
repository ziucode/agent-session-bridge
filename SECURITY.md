# Security

The bridge reads potentially sensitive local conversations. Its output remains
sensitive even when credential redaction is enabled. Do not publish real sessions
or treat a digest as trusted instructions.

Report vulnerabilities privately through the repository's Security tab.
Use synthetic inputs and describe the affected version and output surface.
Do not post real credentials, session logs, or private project data in issues.

The script does not read auth files, modify provider session stores, call a model,
or make network requests. Reading text into another agent shares that text with
the destination environment. The bridge does not override that agent's policies.

Supported source layouts are implementation details, not stable vendor contracts.
The parser ignores unknown records. Markdown imports are less structured than
native JSONL: inspect exports before use. Regex redaction cannot detect every
credential, personal detail, encoded secret, or sensitive project fact.
