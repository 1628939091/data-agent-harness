"""评分器：只看最终产物，不看过程（Terminal-Bench 的设计哲学）。

"Agent 用的什么方法不重要，容器里最终状态对了才算过" —— 这让评分对
任何 scaffold / 任何模型都公平。规则评分器的类型：

  csv_equals         : 产出的 CSV 与标准答案文件逐行一致
  json_key_equals    : JSON 文件指定 key 与期望值一致（数值带容差）
  number_in_text     : 文本中用正则抠出的数字落在期望值容差内
"""

from __future__ import annotations

import csv
import json
import os
import re


def check(checker: dict, workspace: str, data_dir: str) -> tuple[bool, str]:
    """在 agent 的 workspace 上执行检查。返回 (是否通过, 失败原因)。"""
    t = checker["type"]
    if t == "csv_equals":
        return _csv_equals(checker, workspace, data_dir)
    if t == "json_key_equals":
        return _json_key(checker, workspace, data_dir)
    if t == "number_in_text":
        return _number_in_text(checker, workspace)
    if t == "number_in_text_computed":
        return _number_in_text_computed(checker, workspace, data_dir)
    return False, f"未知检查器类型 {t}"


def _csv_equals(c, workspace, data_dir):
    got = os.path.join(workspace, c["file"])
    exp = os.path.join(data_dir, c["expected"])
    if not os.path.exists(got):
        return False, f"产物文件 {c['file']} 不存在"
    if not os.path.exists(exp):
        return False, f"标准答案缺失（harness 配置错误）: {exp}"
    with open(got, encoding="utf-8") as f:
        g = list(csv.reader(f))
    with open(exp, encoding="utf-8") as f:
        e = list(csv.reader(f))
    if len(g) != len(e):
        return False, f"行数不符: 产出 {len(g)} 行 vs 期望 {len(e)} 行（检查清洗规则是否遗漏）"
    for i, (rg, re_) in enumerate(zip(g, e)):
        if rg != re_:
            return False, f"第 {i + 1} 行不一致: {rg} vs {re_}"
    return True, "OK"


def _json_key(c, workspace, data_dir=""):
    path = os.path.join(workspace, c["file"])
    if not os.path.exists(path):
        return False, f"产物文件 {c['file']} 不存在"
    with open(path, encoding="utf-8") as f:
        try:
            data = json.load(f)
        except json.JSONDecodeError:
            return False, "JSON 解析失败"
    # 期望值可以静态给定，也可以由 harness 现场执行"金标准 SQL"算出
    # （后者保证期望值与数据生成逻辑永不脱节 —— 评测基准建设的常见坑）
    if c.get("sql"):
        import sqlite3
        db = os.path.join(data_dir, c["db"])
        con = sqlite3.connect(db)
        try:
            rows = con.execute(c["sql"]).fetchall()
        finally:
            con.close()
        exp = {k: round(float(v), 2) for k, v in rows}
    else:
        exp = c["expected"]
    key = c["key"]
    node = data
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return False, f"缺少 key: {key}"
        node = node[part]
    tol = c.get("tolerance", 0.0)
    if isinstance(exp, dict):
        if set(node) != set(exp):
            return False, f"key 集合不符: {sorted(node)} vs {sorted(exp)}"
        for k, v in exp.items():
            if abs(float(node[k]) - float(v)) > tol:
                return False, f"{k}: {node[k]} vs 期望 {v} (±{tol})"
        return True, "OK"
    if abs(float(node) - float(exp)) > tol:
        return False, f"{key}: {node} vs 期望 {exp} (±{tol})"
    return True, "OK"


def _number_in_text(c, workspace):
    return _number_in_text_core(c, workspace, c["expected"])


def _number_in_text_computed(c, workspace, data_dir):
    """金标准数字从源数据现场计算（销售额类统计的期望值不硬编码）。

    spec: {"csv": 文件名, "qty_col": 列名, "price_col": 列名, "min_qty": 0}
    金标准 = sum(qty * price), 仅统计 qty > min_qty 的行。
    """
    import csv as _csv
    src = os.path.join(data_dir, c["csv"])
    total = 0.0
    with open(src, encoding="utf-8") as f:
        for r in _csv.DictReader(f):
            if float(r[c["qty_col"]]) > float(c.get("min_qty", 0)):
                total += float(r[c["qty_col"]]) * float(r[c["price_col"]])
    return _number_in_text_core(c, workspace, round(total, 2))


def _number_in_text_core(c, workspace, expected):
    path = os.path.join(workspace, c["file"])
    if not os.path.exists(path):
        return False, f"产物文件 {c['file']} 不存在"
    text = open(path, encoding="utf-8").read()
    m = re.search(c["pattern"], text)
    if not m:
        return False, f"未在文本中找到匹配 /{c['pattern']}/ 的内容"
    val = float(m.group(1).replace(",", ""))
    exp = float(expected)
    tol = abs(exp) * float(c.get("rel_tol", 0.01))
    if abs(val - exp) > tol:
        return False, f"数值 {val} 偏离期望 {exp} (±{tol:.2f})，检查统计口径"
    return True, "OK"
