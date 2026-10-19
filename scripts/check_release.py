#!/usr/bin/env python3
"""Check tracked release contents without reading any provider home directories."""
from pathlib import Path
import hashlib
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
REQUIRED = {
    'README.md', 'LICENSE', 'AGENTS.md', 'CLAUDE.md', '.gitignore',
    'CONTRIBUTING.md', 'SECURITY.md', '.github/workflows/ci.yml',
    'skills/resume-cross-provider-task/SKILL.md',
    'skills/resume-cross-provider-task/agents/openai.yaml',
    'skills/resume-cross-provider-task/scripts/context_bridge.py',
    'scripts/check_release.py', 'examples/cursor-export.md',
    'tests/test_context_bridge.py', 'tests/test_release_behavior.py',
    'media/README.md', 'media/agent-session-bridge-intro-en.srt',
    'media/agent-session-bridge-intro-en.mp4',
}


APPROVED_MEDIA = {
    'media/agent-session-bridge-intro-en.mp4': '99d0ce086bac57b187c759fbeeb31db3da1dfc151552c4378d4a1d7a3b9fd0b0',
}

def main():
    if (ROOT / '.git').exists():
        result = subprocess.run(['git', 'ls-files', '-z'], cwd=ROOT, capture_output=True, check=True)
        files = {item for item in result.stdout.decode().split('\0') if item}
    else:
        files = {str(path.relative_to(ROOT)).replace('\\', '/') for path in ROOT.rglob('*') if path.is_file() and 'agent_state' not in path.relative_to(ROOT).parts and '__pycache__' not in path.parts}
    errors = []
    for missing in sorted(REQUIRED - files):
        errors.append(f'missing required release file: {missing}')
    for name in sorted(files):
        if name not in REQUIRED:
            errors.append(f'not in reviewed release allowlist: {name}')
            continue
        path = ROOT / name
        if path.is_symlink():
            errors.append(f'symlink not allowed: {name}')
            continue
        if name in APPROVED_MEDIA:
            if hashlib.sha256(path.read_bytes()).hexdigest() != APPROVED_MEDIA[name]:
                errors.append(f'approved media hash mismatch: {name}')
            continue
        text = path.read_text(encoding='utf-8')
        # No real account home paths or private-key material belongs in the package.
        if re.search(r'/Users/[A-Za-z0-9_.-]+/|/home/[A-Za-z0-9_.-]+/', text):
            errors.append(f'personal absolute path in {name}')
        if re.search(r'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----', text):
            errors.append(f'private-key block in {name}')
        if re.search(r'\b(?:ghp|github_pat)_[A-Za-z0-9]{20,}\b|\bsk-(?:ant-)?[A-Za-z0-9]{20,}\b', text):
            errors.append(f'credential-shaped literal in {name}')
    if (ROOT / 'CLAUDE.md').read_text().strip() != '@AGENTS.md':
        errors.append('CLAUDE.md must only point to AGENTS.md')
    if errors:
        print('\n'.join(errors), file=sys.stderr)
        return 1
    print(f'Release hygiene: {len(files)} allowlisted files; text scan passed; approved media hashes match.')
    print('This check is not a complete secret detector or a provenance audit.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
