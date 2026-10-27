"""harness 报告：Markdown 表格，简历/博客/tech report 的直接底稿。"""

from __future__ import annotations

import os
from datetime import datetime


def render_report(result: dict, out_path: str) -> str:
    s = result["summary"]
    lines = [
        "# DataAgent-Harness 评测报告",
        f"\n生成时间：{datetime.now():%Y-%m-%d %H:%M} | 每配置重复 {result['k']} 次"
        f" | 环境告知：{'开' if result.get('env_prompt') else '关'}",
        "\n## 一、pass@1 / pass^k / 成本总览\n",
        "| 任务 | Scaffold | pass@1 | 95%CI | pass^k | 平均步数 | 平均token | 平均耗时(s) |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for m in sorted(s.values(), key=lambda x: (x["task"], x["scaffold"])):
        lo, hi = m["ci"]
        lines.append(
            f"| {m['task']} | {m['scaffold']} | {m['pass@1']:.2f} "
            f"| [{lo:.2f},{hi:.2f}] | {m['pass_k']:.2f} "
            f"| {m['avg_steps']:.1f} | {m['avg_tokens']:.0f} "
            f"| {m['avg_wall']:.2f} |")

    lines += [
        "\n**指标解读**",
        "- **pass@1**：单次运行成功率（带 Bootstrap 95% CI）。",
        "- **pass^k**：k 次运行全部成功的概率。生产环境要的是'每次都对'，"
        "pass@1 高但 pass^k 低的 agent 上线就是定时炸弹。",
        "- **平均 token / 步数**：成本与效率。Reflect 重试会用 token 换成功率 ——"
        "值不值，正是你消融实验要回答的问题。",
    ]

    lines += ["\n## 二、Scaffold 消融结论（自动生成）\n"]
    tasks = sorted({m["task"] for m in s.values()})
    for t in tasks:
        row = {m["scaffold"]: m for m in s.values() if m["task"] == t}
        if {"react", "plan_execute", "reflect_retry"} <= set(row):
            lines.append(
                f"- **{t}**：pass@1 react={row['react']['pass@1']:.2f}, "
                f"plan_execute={row['plan_execute']['pass@1']:.2f}, "
                f"reflect_retry={row['reflect_retry']['pass@1']:.2f}；"
                f"reflect 相比 react 的提升 = "
                f"{row['reflect_retry']['pass@1'] - row['react']['pass@1']:+.2f}，"
                f"代价 = 平均多 {(row['reflect_retry']['avg_tokens'] - row['react']['avg_tokens']):.0f} token")

    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return out_path
