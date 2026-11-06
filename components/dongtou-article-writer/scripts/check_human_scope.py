#!/usr/bin/env python3
"""Read-only scope wrapper for the unchanged human-writing check_prose.py.

Offsets are Python Unicode character offsets, with an exclusive end. The full
checker report and the editable-scope report remain separate; neither proves
human review, prose quality, or factual accuracy.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path


SOURCE_VERSION = "1.0.0"
SCOPE = (
    "只读调用 human-writing 原始检查器，分别记录原稿全文与可编辑范围的脚本结果；"
    "不证明人工审阅实际发生、活人感、内容质量或事实真实性"
)


def validate_protection(data, body, digest):
    if not isinstance(data, dict):
        raise ValueError("保护文件必须是 JSON 对象")
    recorded_digest = data.get("article_sha256")
    if not isinstance(recorded_digest, str) or not re.fullmatch(
        r"[0-9a-f]{64}", recorded_digest
    ):
        raise ValueError("article_sha256 必须是当前原稿的完整 SHA-256")
    if recorded_digest != digest:
        raise ValueError("保护文件指纹与当前原稿不一致")
    protected = data.get("protected")
    if not isinstance(protected, list):
        raise ValueError("protected 必须是列表；无保护范围时使用空列表")
    validated = []
    for index, item in enumerate(protected, 1):
        if not isinstance(item, dict):
            raise ValueError(f"第{index}个保护区间必须是对象")
        start, end = item.get("start"), item.get("end")
        if type(start) is not int or type(end) is not int:
            raise ValueError(f"第{index}个保护区间的 start/end 必须是整数字符位置")
        if not 0 <= start < end <= len(body):
            raise ValueError(f"第{index}个保护区间超出正文或为空")
        text = item.get("text")
        if not isinstance(text, str) or text != body[start:end]:
            raise ValueError(f"第{index}个保护区间的 text 与原稿精确字符不一致")
        basis = item.get("basis")
        if not isinstance(basis, str) or not basis.strip():
            raise ValueError(f"第{index}个保护区间缺少非空用户依据")
        validated.append({"start": start, "end": end, "text": text, "basis": basis})
    ordered = sorted(validated, key=lambda item: (item["start"], item["end"]))
    for previous, current in zip(ordered, ordered[1:]):
        if current["start"] < previous["end"]:
            raise ValueError("保护区间不能重叠")
    return ordered


def mask_protected(body, protected):
    characters = list(body)
    for item in protected:
        for offset in range(item["start"], item["end"]):
            if characters[offset] not in "\r\n":
                characters[offset] = " "
    return "".join(characters)


def run_original(checker, path):
    run = subprocess.run(
        [sys.executable, str(checker), str(path)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    return {
        "returncode": run.returncode,
        "checked": run.returncode in (0, 1),
        "covered_rules_passed": run.returncode == 0,
        "stdout": run.stdout,
        "stderr": run.stderr,
    }


def check(article, protection=None):
    raw = article.read_bytes()
    body = raw.decode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    protected = []
    if protection is not None:
        protected = validate_protection(
            json.loads(protection.read_text(encoding="utf-8")), body, digest
        )
    components = Path(__file__).resolve().parents[2]
    dependencies = json.loads(
        (components / "dongtou-wechat-writing/references/dependencies.json").read_text(encoding="utf-8")
    )["entries"]
    human = next((item for item in dependencies if item["id"] == "human-writing"), None)
    if not human or human.get("step") != 6 or 5 not in human.get("used_steps", []):
        raise ValueError("成稿范围检查缺少内置第六步 human-writing 依赖定义")
    human_root = (components / "human-writing").resolve()
    missing = []
    for relative in human.get("required_files", []):
        path = (human_root / relative).resolve()
        if human_root not in path.parents or not path.is_file():
            missing.append(relative)
    if not human.get("required_files") or missing:
        raise ValueError("缺少内置 human-writing 完整原包：" + "、".join(missing or ["完整文件清单"]))
    if (human_root / "VERSION").read_text(encoding="utf-8").strip() != SOURCE_VERSION:
        raise ValueError("内置 human-writing 原包版本必须为 1.0.0")
    checker = human_root / "scripts/check_prose.py"
    if not checker.is_file():
        raise ValueError("候选套件缺少 human-writing 原始 check_prose.py")
    full_report = run_original(checker, article)
    if protected:
        editable = mask_protected(body, protected)
        # System temporary storage is removed before returning, even on failure.
        with tempfile.TemporaryDirectory(prefix="dongtou-human-scope-") as temporary:
            editable_path = Path(temporary) / "editable-scope.txt"
            editable_path.write_bytes(editable.encode("utf-8"))
            editable_report = run_original(checker, editable_path)
    else:
        editable_report = dict(full_report)
    if not editable_report["checked"]:
        passed = False
        status = "范围受限" if protected else "未检查"
        script_status = "未运行"
        reason = "可编辑范围未完成检查；全部保护或无可检查汉字不能判为通过"
    elif editable_report["covered_rules_passed"]:
        passed = True
        status = "可编辑范围通过" if protected else "全文通过"
        script_status = status
        reason = (
            "仅可编辑范围没有命中原始检查器的硬禁项，保护范围保留在全文原始报告中"
            if protected
            else "全文没有命中原始检查器的硬禁项；警告仍需人工判断"
        )
    else:
        passed = False
        status = "未通过"
        script_status = "未通过"
        reason = "可编辑范围命中原始检查器的硬禁项"
    return {
        "passed": passed,
        "status": status,
        "script_status": script_status,
        "reason": reason,
        "source_version": SOURCE_VERSION,
        "article_sha256": digest,
        "scope": SCOPE,
        "checked_scope": "可编辑范围" if protected else "全文",
        "protected": protected,
        "protected_character_count": sum(item["end"] - item["start"] for item in protected),
        "human_review_required": True,
        "full_report": full_report,
        "editable_report": editable_report,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("article", type=Path, help="当前 UTF-8 原稿路径")
    parser.add_argument("--protection", type=Path, help="绑定当前原稿指纹的保护区间 JSON")
    args = parser.parse_args()
    try:
        result = check(args.article, args.protection)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        result = {
            "passed": False,
            "status": "待核验",
            "script_status": "未运行",
            "scope": SCOPE,
            "errors": [str(exc)],
        }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
