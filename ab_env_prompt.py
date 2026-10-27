# -*- coding: utf-8 -*-
"""环境告知 A/B 消融：同一批任务跑两遍，只改提示词里"环境"那几句。

对照的两臂：
  臂 A（关，默认）：只告诉 agent"数据在当前工作目录"+ 解释器路径
  臂 B（开）：额外告诉它"只有标准库、没有 pandas"+ 当前目录文件清单

为什么值得单独跑一遍：这两句属于 harness 层的改动 —— **不换模型、不改任务、
不动评分器**，只改一句提示词。如果它能省下 1–2 轮环境摸索，就是"harness 本身
是研究对象"的直接证据（也顺手回答了"prompt 算不算 scaffold"这个争论）。

用法：
    python ab_env_prompt.py            # Mock 模型，验证脚本本身能不能跑
    python ab_env_prompt.py api        # 真实模型（需 DEEPSEEK_API_KEY）
    python ab_env_prompt.py api 5      # 每臂重复 5 次
成本：4 任务 × 3 scaffold × n × 2 臂 —— n=3 时 72 跑。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from daharness.runner import run_benchmark

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS_ROOT = os.path.join(HERE, "tasks")
TASKS = ["sales_clean", "region_sql", "weekly_report", "taxi_clean"]
SCAFFOLDS = ["react", "plan_execute", "reflect_retry"]


def run_arm(on: bool, k: int, use_api: bool) -> dict:
    """跑一臂。开关靠环境变量传（agents.new_messages 每次调用时读）。"""
    os.environ["DAH_ENV_PROMPT"] = "1" if on else "0"
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if use_api and not api_key:
        print("[错误] api 模式需要 DEEPSEEK_API_KEY")
        sys.exit(1)
    config = {
        "tasks": TASKS, "scaffolds": SCAFFOLDS, "repeats": k,
        "flaky": not use_api,
        "env": "local",
        "env_prompt": on,
        "model": None if not use_api else {
            "backend": "api",
            "name": os.environ.get("DAH_MODEL", "deepseek-chat"),
            "base_url": os.environ.get("DAH_BASE_URL", "https://api.deepseek.com/v1"),
            "api_key": api_key,
            "model": os.environ.get("DAH_MODEL", "deepseek-chat"),
        },
    }
    return run_benchmark(config, TASKS_ROOT)


def main() -> None:
    argv = sys.argv[1:]
    use_api = "api" in argv
    k = next((int(a) for a in argv if a.isdigit()), 3)
    mode = "真实 API" if use_api else "Mock（只验证脚本，Mock 不看提示词，两臂应当完全一致）"
    print(f"环境告知 A/B：{len(TASKS)} 任务 × {len(SCAFFOLDS)} scaffold × {k} 重复 × 2 臂"
          f" | {mode}\n")

    print("[1/2] 臂 A：环境告知关 ……")
    off = run_arm(False, k, use_api)
    print("[2/2] 臂 B：环境告知开 ……\n")
    on = run_arm(True, k, use_api)

    print("===== A/B 差值（B 相对 A）=====")
    print(f"  {'任务':<14}{'scaffold':<14}{'步数 A→B':<16}{'token A→B':<22}{'通过率 A→B'}")
    tot = {"steps": [0.0, 0.0], "tok": [0.0, 0.0], "pass": [0.0, 0.0]}
    for key in sorted(off["summary"]):
        a, b = off["summary"][key], on["summary"][key]
        d_steps = b["avg_steps"] - a["avg_steps"]
        d_tok = b["avg_tokens"] - a["avg_tokens"]
        pct = (d_tok / a["avg_tokens"] * 100) if a["avg_tokens"] else 0.0
        print(f"  {a['task']:<14}{a['scaffold']:<14}"
              f"{a['avg_steps']:>5.1f} → {b['avg_steps']:<6.1f}"
              f"{a['avg_tokens']:>7.0f} → {b['avg_tokens']:<7.0f}({pct:+5.1f}%)  "
              f"{a['pass@1']:.2f} → {b['pass@1']:.2f}")
        tot["steps"][0] += a["avg_steps"]; tot["steps"][1] += b["avg_steps"]
        tot["tok"][0] += a["avg_tokens"]; tot["tok"][1] += b["avg_tokens"]
        tot["pass"][0] += a["pass@1"]; tot["pass"][1] += b["pass@1"]
    n = len(off["summary"]) or 1
    d_tok = tot["tok"][1] / n - tot["tok"][0] / n
    print(f"\n  平均：步数 {tot['steps'][0]/n:.1f} → {tot['steps'][1]/n:.1f}"
          f" | token {tot['tok'][0]/n:.0f} → {tot['tok'][1]/n:.0f}"
          f"（{d_tok / (tot['tok'][0]/n) * 100:+.1f}%）"
          f" | pass@1 {tot['pass'][0]/n:.2f} → {tot['pass'][1]/n:.2f}")


if __name__ == "__main__":
    main()
