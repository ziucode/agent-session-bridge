# Contributing

Keep changes focused on reliable context handoffs. Run the unittest suite and
release check in the README before opening a pull request.

For a new reader, provide a synthetic fixture with user and assistant messages,
project identity, a tool call/result, reasoning, and unknown records. Test that
only intended visible text reaches the digest. Test project scoping, malformed
files, source immutability, redaction, and end-to-end CLI behavior.

Do not attach real session logs, provider databases, auth files, account identifiers,
private repository paths, tool arguments, or personal digests to issues or PRs.
Reproduce format problems with hand-written data. State which product version
and OS the format represents. A fixture proves that input shape, not every version.

New platform names belong in the supported table only after their reader and
tests are included. Keep native restoration, cloud agents, and provider accounts
outside this tool's scope. Keep runtime dependencies in Python's standard library.
