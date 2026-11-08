"""Discover ordinary bundled Hermes skills without contacting ComfyUI."""
from pathlib import Path
import re
import yaml


def skills_for_registration(skills_dir: Path, workflow_ids: set[str]) -> list[dict]:
    root = Path(skills_dir).resolve()
    rows = []
    for path in sorted(root.glob('*/SKILL.md')):
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            raise ValueError(f'Skill path escapes package: {path.name}')
        name = path.parent.name
        if not re.fullmatch(r'[a-z0-9][a-z0-9_-]{0,63}', name):
            raise ValueError(f'Invalid skill directory: {name}')
        text = resolved.read_text(encoding='utf-8-sig')
        parts = text.split('---', 2)
        if len(parts) != 3 or parts[0].strip():
            raise ValueError(f'Missing skill frontmatter: {name}')
        try:
            meta = yaml.safe_load(parts[1])
        except yaml.YAMLError as exc:
            raise ValueError(f'Invalid skill YAML: {name}') from exc
        if not isinstance(meta, dict) or meta.get('name') != name:
            raise ValueError(f'Skill name must match directory: {name}')
        description = meta.get('description')
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f'Missing skill description: {name}')
        metadata = meta.get('metadata', {})
        if not isinstance(metadata, dict):
            raise ValueError(f'Invalid skill metadata: {name}')
        local = metadata.get('comfy_recipe', {})
        if not isinstance(local, dict):
            raise ValueError(f'Invalid comfy_recipe metadata: {name}')
        refs = local.get('workflow_ids', [])
        if not isinstance(refs, list) or any(not isinstance(x, str) or x not in workflow_ids for x in refs):
            raise ValueError(f'Unknown or invalid workflow references: {name}')
        if len(set(refs)) != len(refs):
            raise ValueError(f'Duplicate workflow references: {name}')
        rows.append({'name': name, 'path': resolved, 'description': description.strip(), 'workflow_ids': refs})
    return rows
