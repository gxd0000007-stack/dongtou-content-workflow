#!/usr/bin/env python3
"""Read-only entrypoint discovery; semantic DNA selection is performed by Codex."""
import argparse
import json
import os
import re
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]

def expand(raw, project_root):
    return Path(raw.replace('{project_root}', str(project_root))).expanduser()

def inspect_entry(item, project_root, skill_roots):
    choices = [expand(p, project_root) for p in item.get('paths', [])]
    for root in skill_roots:
        choices.extend(root / p for p in item.get('skill_relative_paths', []))
    seen = set()
    checked = []
    for path in choices:
        label = str(path)
        if label in seen:
            continue
        seen.add(label)
        readable = path.is_file() and os.access(path, os.R_OK)
        checked.append({'path': label, 'readable': readable})
    found = next((p['path'] for p in checked if p['readable']), None)
    version = None
    missing_files = []
    if found:
        match = re.search(r'^\s*version:\s*["\x27]?([^"\x27\s]+)', Path(found).read_text(encoding='utf-8'), re.M)
        version = match.group(1) if match else None
        if item.get('version_file'):
            version_path = (Path(found).parent / item['version_file']).resolve()
            if version_path.parent == Path(found).parent.resolve() and version_path.is_file():
                version = version_path.read_text(encoding='utf-8').strip()
        for relative in item.get('required_files', []):
            base = Path(found).parent.resolve()
            path = (base / relative).resolve()
            if base not in path.parents or not path.is_file() or not os.access(path, os.R_OK):
                missing_files.append(relative)
    return {**{k:v for k,v in item.items() if k not in ('paths','skill_relative_paths')},
            'entry_status': 'readable' if found and not missing_files else 'missing',
            'resolved_entry': found, 'checked_paths': checked,
            'missing_files': missing_files,
            'complete_files_verified': bool(found) and not missing_files if item.get('required_files') else False,
            'observed_version': version,
            'sample_contents_verified': False}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-root', type=Path)
    parser.add_argument('--skill-root', action='append', type=Path, default=[])
    parser.add_argument('--catalog', type=Path, default=PACKAGE/'references/dna-catalog.json')
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--from-step', type=int, choices=range(1,8), default=1)
    mode.add_argument('--only-step', type=int, choices=range(1,8))
    for step in range(1,8):
        mode.add_argument(f'--from-step{step}', dest='from_step', action='store_const', const=step,
                          help=argparse.SUPPRESS)
        mode.add_argument(f'--only-step{step}', dest='only_step', action='store_const', const=step,
                          help=argparse.SUPPRESS)
    args = parser.parse_args()
    catalog = json.loads(args.catalog.read_text(encoding='utf-8'))
    project_root = (args.project_root or Path(catalog['default_project_root']).expanduser()).resolve()
    codex_root = Path(os.environ.get('CODEX_HOME', str(Path.home()/'.codex'))).expanduser() / 'skills'
    roots = [p.expanduser().resolve() for p in args.skill_root] + [codex_root, Path.home()/'.agents/skills']
    roots = list(dict.fromkeys(roots))
    entries = catalog['entries']
    ids = [e['id'] for e in entries]
    if len(ids) != len(set(ids)):
        parser.error('Catalog entry IDs must be unique.')
    dna = [inspect_entry(e, project_root, roots) for e in entries]
    deps = json.loads((PACKAGE/'references/dependencies.json').read_text(encoding='utf-8'))['entries']
    # Core dependencies are fixed siblings of this controller, never fallback roots.
    bundled = PACKAGE.parent.name == 'components'
    core_roots = [PACKAGE.parent]
    dependencies = [inspect_entry({**e, 'paths': []}, project_root, core_roots) for e in deps]
    needed = [e for e in dependencies if args.only_step in e.get('used_steps', [e['step']])] if args.only_step else [e for e in dependencies if any(s >= args.from_step for s in e.get('used_steps', [e['step']]))]
    result = {
        'mode': 'read_only_discovery_not_semantic_matching',
        'project_root': str(project_root),
        'skill_roots': [str(r) for r in roots],
        'core_roots': [str(r) for r in core_roots],
        'bundled': bundled,
        'stage_count': 7,
        'dna_count': len(dna), 'dna_readable': sum(e['entry_status']=='readable' for e in dna),
        'dna': dna, 'dependencies': dependencies,
        'needed_steps': sorted({s for e in needed for s in e.get('used_steps', [e['step']]) if (s == args.only_step if args.only_step else s >= args.from_step)}),
        'needed_components': [e['id'] for e in needed],
        'required_helpers': [e['id'] for e in needed if e.get('role') == 'assistant'],
        'pre_read_dependencies': [e['id'] for e in needed if any(s in e.get('pre_read_steps', []) for s in ([args.only_step] if args.only_step else range(args.from_step, 8)))],
        'reference_dependencies': [e['id'] for e in needed if any(s in e.get('reference_steps', []) for s in ([args.only_step] if args.only_step else range(args.from_step, 8)))],
        'missing_core_dependencies': [e['id'] for e in needed if e.get('required') and e['entry_status']=='missing'],
        'version_drift': [e['id'] for e in needed if e['observed_version'] and e['observed_version']!=e.get('tested_version')],
        'notice': 'Readable entrypoints do not establish sample availability or that any text has been read. Codex must inspect selected instructions and evidence.'
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result['missing_core_dependencies'] else 0

if __name__ == '__main__':
    raise SystemExit(main())
