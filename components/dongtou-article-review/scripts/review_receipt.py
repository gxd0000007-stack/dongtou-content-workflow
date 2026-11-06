#!/usr/bin/env python3
"""Validate receipt consistency, never semantic quality or factual truth."""
import argparse
import hashlib
import json
import re
from pathlib import Path

CHECKS = ("want_read", "understandable", "credible", "fulfilled", "structure")
STATUSES = {"通过", "不通过", "待补材料", "待核验"}
VERDICTS = {"可交稿", "退修", "待补材料", "待核验"}
HUMAN_MODES = {"全文", "局部", "客观例外"}
HUMAN_STATUSES = {"通过", "范围受限", "不通过", "待补材料", "待核验"}
SCRIPT_STATUSES = {"全文通过", "可编辑范围通过", "未通过", "未运行"}


def validate(article, receipt, require_author_view=False, require_human_writing=False):
    raw = article.read_bytes()
    body = raw.decode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    data = json.loads(receipt.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("记录必须是 JSON 对象")
    errors = []
    verdict = data.get("verdict")
    if verdict not in VERDICTS:
        errors.append("整体结论无效")
    if data.get("final_sha256") != digest:
        errors.append("当前文案与最终指纹不一致")
    rounds = data.get("rounds")
    if not isinstance(rounds, list):
        rounds = []
        errors.append("rounds 必须是列表")
    if len(rounds) < 6:
        errors.append("实际检查记录不足六轮")
    for index, item in enumerate(rounds, 1):
        if not isinstance(item, dict):
            errors.append(f"第{index}轮不是对象")
            continue
        if item.get("round") != index:
            errors.append(f"第{index}轮编号不连续")
        focus = item.get("focus")
        if index <= 5 and focus != CHECKS[index - 1]:
            errors.append(f"第{index}轮重点不符合五项顺序")
        if index == 6 and focus != "full":
            errors.append("第六轮必须完整终检")
        if focus not in (*CHECKS, "full"):
            errors.append(f"第{index}轮重点无效")
        if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("reviewed_sha256", ""))):
            errors.append(f"第{index}轮版本指纹无效")
        for key in ("findings", "actions"):
            values = item.get(key)
            if not isinstance(values, list) or not values or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                errors.append(f"第{index}轮缺少具体{key}记录")
    if rounds and isinstance(rounds[-1], dict):
        if rounds[-1].get("focus") != "full":
            errors.append("最后一轮必须完整终检")
        if rounds[-1].get("reviewed_sha256") != digest:
            errors.append("最后终检没有对应当前完整文案")
    final = data.get("final_checks")
    if not isinstance(final, dict):
        final = {}
        errors.append("缺少最终五项检查")
    if set(final) != set(CHECKS):
        errors.append("最终检查项目必须恰好包含五项")
    for key in CHECKS:
        item = final.get(key)
        if not isinstance(item, dict):
            errors.append(f"缺少{key}检查对象")
            continue
        status = item.get("status")
        if status not in STATUSES:
            errors.append(f"{key}状态无效")
        if not isinstance(item.get("reason"), str) or not item["reason"].strip():
            errors.append(f"{key}缺少具体理由")
        quotes = item.get("article_quotes")
        if not isinstance(quotes, list):
            quotes = []
            errors.append(f"{key}引句必须是列表")
        if status == "通过" and not quotes:
            errors.append(f"{key}通过项没有当前正文引句")
        for quote in quotes:
            if not isinstance(quote, str) or not quote.strip() or quote not in body:
                errors.append(f"{key}引句不在当前正文中")
        if verdict == "可交稿" and status != "通过":
            errors.append(f"可交稿却存在未通过项目{key}")
    author_view = data.get("author_view")
    if author_view is None:
        if require_author_view:
            errors.append("新版执行缺少作者视角验收记录")
    elif not isinstance(author_view, dict):
        errors.append("author_view 必须是对象")
    else:
        required = author_view.get("required")
        if not isinstance(required, bool):
            errors.append("author_view.required 必须明确为布尔值")
        for key in ("mode", "viewpoint_source", "viewpoint_status", "reason"):
            value = author_view.get(key)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"作者视角缺少{key}记录")
        status = author_view.get("status")
        if required is True:
            if status not in STATUSES:
                errors.append("作者视角状态无效")
            core_view = author_view.get("core_view")
            if not isinstance(core_view, str) or not core_view.strip():
                errors.append("作者视角缺少核心观点")
            if verdict == "可交稿" and status != "通过":
                errors.append("可交稿却未通过作者视角约定")
        elif required is False and status != "不适用":
            errors.append("不要求作者视角时必须记录不适用及理由")
        quotes = author_view.get("article_quotes")
        if not isinstance(quotes, list):
            quotes = []
            errors.append("作者视角引句必须是列表")
        if required is True and status == "通过" and not quotes:
            errors.append("作者视角通过项没有当前正文引句")
        for quote in quotes:
            if not isinstance(quote, str) or not quote.strip() or quote not in body:
                errors.append("作者视角引句不在当前正文中")
    human_writing = data.get("human_writing")
    if human_writing is None:
        if require_human_writing:
            errors.append("新版执行缺少 human-writing 验收记录")
    elif not isinstance(human_writing, dict):
        errors.append("human_writing 必须是对象")
    else:
        if human_writing.get("source_version") != "1.0.0":
            errors.append("human_writing.source_version 必须为 1.0.0")
        if human_writing.get("mode") not in HUMAN_MODES:
            errors.append("human_writing.mode 无效")
        human_status = human_writing.get("status")
        if human_status not in HUMAN_STATUSES:
            errors.append("human_writing.status 无效")
        reason = human_writing.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            errors.append("human_writing 缺少具体人工审阅理由")
        script_status = human_writing.get("script_status")
        if script_status not in SCRIPT_STATUSES:
            errors.append("human_writing.script_status 无效")
        quotes = human_writing.get("article_quotes")
        if not isinstance(quotes, list):
            quotes = []
            errors.append("human_writing.article_quotes 必须是列表")
        if human_status in {"通过", "范围受限"} and not quotes:
            errors.append("human-writing 通过或范围受限项没有当前正文引句")
        for quote in quotes:
            if not isinstance(quote, str) or not quote.strip() or quote not in body:
                errors.append("human-writing 引句不在当前正文中")
        exceptions = human_writing.get("scope_exceptions")
        if not isinstance(exceptions, list):
            exceptions = []
            errors.append("human_writing.scope_exceptions 必须是列表")
        for index, exception in enumerate(exceptions, 1):
            if not isinstance(exception, dict):
                errors.append(f"human-writing 第{index}个范围例外必须是对象")
                continue
            text = exception.get("text")
            if not isinstance(text, str) or not text.strip() or text not in body:
                errors.append(f"human-writing 第{index}个范围例外不是当前正文精确引句")
            basis = exception.get("basis")
            if not isinstance(basis, str) or not basis.strip():
                errors.append(f"human-writing 第{index}个范围例外缺少非空用户依据")
        if human_status == "通过" and script_status != "全文通过":
            errors.append("human-writing 通过却没有记录脚本全文通过")
        if human_status == "范围受限":
            if script_status != "可编辑范围通过":
                errors.append("human-writing 范围受限却没有记录可编辑范围通过")
            if not exceptions:
                errors.append("human-writing 范围受限缺少精确范围例外及用户依据")
        if verdict == "可交稿" and human_status not in {"通过", "范围受限"}:
            errors.append("可交稿却存在未通过的 human-writing 验收")
    return {"passed": not errors,
            "scope": "记录结构、当前全文指纹、正文引句和脚本结果记录一致性；不证明人工审阅或脚本实际发生、活人感、内容质量或事实真实性",
            "final_sha256": digest, "round_count": len(rounds),
            "verdict": verdict, "author_view_recorded": isinstance(author_view, dict),
            "author_view_status": author_view.get("status") if isinstance(author_view, dict) else None,
            "human_writing_recorded": isinstance(human_writing, dict),
            "human_writing": human_writing if isinstance(human_writing, dict) else None,
            "human_writing_status": human_writing.get("status") if isinstance(human_writing, dict) else None,
            "human_writing_script_status": human_writing.get("script_status") if isinstance(human_writing, dict) else None,
            "errors": errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--article", type=Path, required=True)
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--require-author-view", action="store_true",
                        help="新版执行要求作者视角记录；不自动判断观点或作者感")
    parser.add_argument("--require-human-writing", action="store_true",
                        help="新版执行要求 human-writing 记录；只验证记录一致性")
    args = parser.parse_args()
    try:
        result = validate(args.article, args.receipt, args.require_author_view, args.require_human_writing)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {"passed": False, "errors": [str(exc)]}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
