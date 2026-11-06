# human-writing 范围检查与审阅记录

这是 `human-writing` 1.0.0 的接入记录格式。原始检查器只报告其覆盖的硬禁项与警告，人工审阅仍需依据当前文案判断材料、说话位置、推进和自然中文。记录校验通过不证明审阅或脚本实际执行，也不证明活人感、内容质量或事实真实性。

## 第六步范围检查

运行 `python3 components/dongtou-article-writer/scripts/check_human_scope.py <原稿路径> [--protection <保护JSON路径>]`，将 JSON 输出保存为独立检查报告。脚本只读原稿，并调用套件中未修改的 `human-writing/scripts/check_prose.py`。

保护文件必须绑定当前原稿的原始字节 SHA-256。`start`、`end` 是 Python 字符串的字符位置，汉字也计一个字符，`end` 不包含在区间内。区间不能重叠，`text` 必须与该字符区间逐字一致，`basis` 记录非空的用户明确依据。

```json
{
  "article_sha256": "当前原稿的64位小写SHA-256",
  "protected": [
    {"start": 0, "end": 4, "text": "精确原文", "basis": "用户明确要求保留该处原文"}
  ]
}
```

无保护范围也必须填写指纹并使用 `protected: []`；没有 `--protection` 时检查全文。脚本 JSON 分别保存 `full_report` 与 `editable_report` 的原始 stdout、stderr、returncode。受保护字符仅在系统临时副本中替换为空格，换行保留，原稿不变。保护原稿全部内容或剩余范围没有可检查汉字时，`passed` 为 false，不能当成通过。

存在保护范围时，即使可编辑范围通过，也只记录 `script_status: 可编辑范围通过`。全文原始报告中保留的违规不代表已修复。警告仍需人工判断。

## 第七步回执

既有六轮记录、`final_checks` 五项与作者视角记录继续保留。新增可选 `human_writing` 对象。新版执行使用 `--require-human-writing`，缺少该对象会被拒绝；不加此参数时旧回执仍兼容。

```json
{
  "human_writing": {
    "source_version": "1.0.0",
    "mode": "局部",
    "status": "范围受限",
    "reason": "人工审阅当前可编辑正文后的具体理由",
    "article_quotes": ["当前正文中的精确引句"],
    "script_status": "可编辑范围通过",
    "scope_exceptions": [
      {"text": "当前正文中受保护的精确原文", "basis": "用户明确要求保留该处原文"}
    ]
  }
}
```

以上是格式示例，不是已发生的审阅记录，不可直接作为真实稿件验收结果。

`mode` 仅用 `全文`、`局部`、`客观例外`。人工 `status` 仅用 `通过`、`范围受限`、`不通过`、`待补材料`、`待核验`。脚本 `script_status` 仅用 `全文通过`、`可编辑范围通过`、`未通过`、`未运行`，与人工结论分开记录。`reason` 非空，`article_quotes` 和每个范围例外的 `text` 都必须逐字出现在当前正文；每个例外的 `basis` 非空。

人工状态为 `通过` 时，必须有正文引句且脚本状态为 `全文通过`。人工状态为 `范围受限` 时，必须有正文引句、脚本状态为 `可编辑范围通过`，并至少有一个精确范围例外及其用户依据。`可交稿` 只接受这两种人工状态；其余人工状态不能交稿。范围例外由用户明确授权支持，脚本只验证记录非空与原文一致，不能证明授权本身。

总控交付校验透传 `--require-human-writing`，返回人工状态、脚本状态和完整 `human_writing` 对象。它只校验交付文件与回执的一致性。
