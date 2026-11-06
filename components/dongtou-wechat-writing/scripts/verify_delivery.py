#!/usr/bin/env python3
"""Read-only final file/receipt consistency check, not a content audit."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

def check(article, report, receipt, review_skill=None, require_author_view=False, require_human_writing=False):
    package=Path(__file__).resolve().parents[1]
    bundled=package.parent.name == 'components'
    if bundled:
        if review_skill is not None:
            raise ValueError('套件交付仅使用内置第七步，不能指定外部 --review-skill')
        dependencies=json.loads((package/'references/dependencies.json').read_text(encoding='utf-8'))['entries']
        human=next((item for item in dependencies if item['id']=='human-writing'),None)
        if not human or human.get('step') != 6 or 7 not in human.get('used_steps',[]):
            raise ValueError('第七步缺少内置第六步 human-writing 依赖定义')
        human_root=(package.parent/'human-writing').resolve()
        missing=[]
        for relative in human.get('required_files',[]):
            path=(human_root/relative).resolve()
            if human_root not in path.parents or not path.is_file():
                missing.append(relative)
        if not human.get('required_files') or missing:
            raise ValueError('第七步缺少内置 human-writing 完整原包：'+'、'.join(missing or ['完整文件清单']))
        if (human_root/'VERSION').read_text(encoding='utf-8').strip() != human.get('tested_version'):
            raise ValueError('内置 human-writing 原包版本不符合依赖约定')
    for p in (article,report,receipt):
        if not p.is_file() or not p.stat().st_size:
            raise ValueError('缺少非空交付文件：'+str(p))
    digest=hashlib.sha256(article.read_bytes()).hexdigest()
    if digest not in report.read_text(encoding='utf-8'):
        raise ValueError('质检报告没有对应当前全文指纹')
    if review_skill:
        choices=[review_skill/'scripts/review_receipt.py']
    elif bundled:
        choices=[package.parent/'dongtou-article-review/scripts/review_receipt.py']
    else:
        choices=[package.parent/'dongtou-article-review/scripts/review_receipt.py']
    validator=next((p for p in choices if p.is_file()),None)
    if not validator:
        raise ValueError('第七步回执校验脚本不可读；套件必须包含内置组件')
    command=[sys.executable,str(validator),'--article',str(article),'--receipt',str(receipt)]
    if require_author_view:
        command.append('--require-author-view')
    if require_human_writing:
        command.append('--require-human-writing')
    run=subprocess.run(command,capture_output=True,text=True)
    result=json.loads(run.stdout)
    if run.returncode or not result.get('passed'):
        raise ValueError('当前全文与六轮记录不一致：'+'；'.join(result.get('errors',[])))
    return {'consistent':True,'article':str(article.resolve()),'report':str(report.resolve()),'sha256':digest,'round_count':result['round_count'],'content_verdict':result['verdict'],'author_view_recorded':result.get('author_view_recorded',False),'author_view_status':result.get('author_view_status'),'human_writing_recorded':result.get('human_writing_recorded',False),'human_writing':result.get('human_writing'),'human_writing_status':result.get('human_writing_status'),'human_writing_script_status':result.get('human_writing_script_status'),'validator':str(validator.resolve()),
            'review_stage':7,'human_writing_stage':6,
            'scope':'只核对文件、当前全文指纹、第七步质检记录与第六步活人感记录；不证明审阅或脚本实际发生、活人感、事实或结构语义正确，也不把退修变成通过'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--article',type=Path,required=True)
    p.add_argument('--report',type=Path,required=True)
    p.add_argument('--receipt',type=Path,required=True)
    p.add_argument('--review-skill',type=Path)
    p.add_argument('--require-author-view',action='store_true')
    p.add_argument('--require-human-writing',action='store_true')
    args=p.parse_args()
    try:
        result=check(args.article,args.report,args.receipt,args.review_skill,args.require_author_view,args.require_human_writing)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        result={'consistent':False,'errors':[str(exc)]}
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result['consistent'] else 1

if __name__=='__main__':
    raise SystemExit(main())
