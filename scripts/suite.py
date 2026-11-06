#!/usr/bin/env python3
"""Read-only bundled entrypoint and delivery consistency helper."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
CONTROLLER = ROOT / 'components/dongtou-wechat-writing'

def inspect():
    data = json.loads((ROOT / 'references/components.json').read_text(encoding='utf-8'))
    items = []
    errors = []
    ids = [item['id'] for item in data['components']]
    expected = {'dongtou-source-reader','dongtou-angle-finder','dongtou-title-opening','dongtou-body-plan','dongtou-article-writer','dongtou-article-review','dongtou-wechat-writing','human-writing'}
    if set(ids) != expected or len(ids) != 8 or data.get('component_count') != 8:
        errors.append('必须包含八个唯一组件：七工序与创作总控')
    expected_steps = {'dongtou-source-reader': 1, 'dongtou-angle-finder': 2,
        'dongtou-title-opening': 3, 'dongtou-body-plan': 4,
        'dongtou-article-writer': 5, 'human-writing': 6,
        'dongtou-article-review': 7, 'dongtou-wechat-writing': None}
    if data.get('stage_count') != 7 or data.get('execution_order') != [1, 2, '3A', 4, 5, 6, 7]:
        errors.append('执行顺序必须完整包含七工序')
    for item in data['components']:
        if item.get('step') != expected_steps.get(item['id']):
            errors.append('组件工序位置不符：' + item['id'])
        expected_role = 'controller' if item['id'] == 'dongtou-wechat-writing' else 'execution'
        if item.get('role') != expected_role:
            errors.append('组件角色必须是七工序或总控：' + item['id'])
        if item['id'] == 'human-writing' and item.get('used_steps') != [5, 6, 7]:
            errors.append('human-writing 必须覆盖第五步预读、第六步改稿和第七步复核')
        entry = (ROOT / item['entry']).resolve()
        if ROOT not in entry.parents:
            errors.append('组件入口超出套件根：' + item['id'])
            continue
        found = entry.is_file()
        text = entry.read_text(encoding='utf-8') if found else ''
        name = re.search(r'^name: ([a-z0-9-]+)$', text, re.M)
        version = re.search(r'^\s*version: ["\x27]?([^"\x27\s]+)', text, re.M)
        observed_version = version.group(1) if version else None
        if item.get('version_file'):
            version_path = (entry.parent / item['version_file']).resolve()
            if version_path.parent != entry.parent or not version_path.is_file():
                errors.append('组件版本文件缺失或超出目录：' + item['id'])
            else:
                observed_version = version_path.read_text(encoding='utf-8').strip()
        file_count = sum(p.is_file() for p in entry.parent.rglob('*')) if found else 0
        ok = found and name is not None and name.group(1) == item['id'] and observed_version == item['version'] and file_count == item['file_count']
        if not ok:
            errors.append('组件入口、版本或完整文件数不符：' + item['id'])
        items.append({**item, 'resolved_entry': str(entry), 'actual_file_count': file_count, 'observed_version': observed_version, 'valid': bool(ok)})
    return {'complete': not errors, 'suite': data['suite'], 'version': data['version'], 'component_count': len(items), 'stage_count': 7, 'components': items, 'errors': errors,
        'scope': '仅检查内置组件入口、标识、版本与文件数；不表示创作或质检已发生'}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['inspect', 'resolve', 'verify-delivery'], nargs='?', default='inspect')
    args, rest = parser.parse_known_args()
    if args.command == 'inspect':
        if rest:
            parser.error('inspect 不接受额外参数')
        result = inspect()
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result['complete'] else 1
    if args.command == 'resolve':
        script = CONTROLLER / 'scripts/resolve_assets.py'
    else:
        script = CONTROLLER / 'scripts/verify_delivery.py'
        if any(arg == '--review-skill' or arg.startswith('--review-skill=') for arg in rest):
            parser.error('套件校验仅使用本包内置第七步，不能覆盖为外部路径')
    if not script.is_file():
        print(json.dumps({'complete': False, 'errors': ['内置总控辅助脚本缺失']}, ensure_ascii=False))
        return 1
    return subprocess.run([sys.executable, str(script), *rest]).returncode

if __name__ == '__main__':
    raise SystemExit(main())
