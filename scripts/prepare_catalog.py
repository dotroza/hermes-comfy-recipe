"""Print the catalog entry for clean HEAD; never commit, push, install or open a PR."""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPO = 'https://github.com/dotroza/hermes-comfy-recipe'
SHOTS = [
    'visible-session-cat-generation.png',
    'visible-session-image-editing.png',
    'visible-session-pet-sheet.png',
]


def render_entry(manifest: dict, sha: str) -> str:
    if not re.fullmatch(r'[0-9a-f]{40}', sha):
        raise ValueError('Catalog pins must be full 40-character lowercase commit SHAs')
    fields = {
        'name': manifest['name'],
        'title': 'Comfy Recipe',
        'repo': REPO,
        'sha': sha,
        'subdir': 'plugin',
        'description': 'Visible ComfyUI sessions, consent-based setup, workflow tools and media preparation inside Hermes.',
        'maintainer': manifest['author'],
        'tier': 'community',
        'category': 'desktop',
        'requires_hermes': manifest['requires_hermes'],
        'version': str(manifest['version']),
        'docs_url': f'{REPO}/blob/{sha}/README.md',
    }
    lines = [f'{key}: {json.dumps(value)}' for key, value in fields.items()]
    lines += ['readme: true', 'platforms: []', 'screenshots:']
    raw = f'https://raw.githubusercontent.com/dotroza/hermes-comfy-recipe/{sha}/docs/screenshots'
    lines += [f'  - {json.dumps(raw + "/" + name)}' for name in SHOTS]
    lines += ['known_issues:', '  - "Windows 11 verified; macOS and Linux paths are implemented but not live-verified."',
              '  - "Workflow models, suitable hardware and optional custom nodes are separate requirements; cloud runs need ComfyUI sign-in, credits and consent."',
              'capabilities:']
    for key in ('provides_tools', 'provides_hooks', 'provides_middleware', 'requires_env'):
        values = manifest.get(key) or []
        lines.append(f'  {key}:' + (' []' if not values else ''))
        lines += [f'    - {json.dumps(value)}' for value in values]
    return '\n'.join(lines) + '\n'


def git(*args: str) -> str:
    return subprocess.run(['git', '-C', str(ROOT), *args], check=True, capture_output=True,
                          text=True, encoding='utf-8', timeout=30).stdout.strip()


def main() -> int:
    if git('status', '--porcelain', '--untracked-files=all'):
        print('Refusing to pin stale HEAD: commit the reviewed changes first, then push and rerun.', file=sys.stderr)
        return 1
    sha = git('rev-parse', 'HEAD')
    manifest = yaml.safe_load(git('show', f'{sha}:plugin/plugin.yaml'))
    # Check the catalog-site README and screenshots exist at the exact commit, not just on disk.
    for name in ['plugin/README.md', *('docs/screenshots/' + s for s in SHOTS)]:
        git('cat-file', '-e', f'{sha}:{name}')
    print(render_entry(manifest, sha), end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
