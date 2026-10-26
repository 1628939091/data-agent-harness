# -*- coding: utf-8 -*-
"""项目二入口：一键跑完 任务 × scaffold × 重复次数 的基准评测。

用法（Linux / macOS / Windows 通用）：
    python run_demo.py                  # Mock 模型演示（flaky 注入典型错误）
    python run_demo.py api              # 接真实模型（需 DEEPSEEK_API_KEY）
    python run_demo.py docker           # 用 Docker 容器沙箱（需先构建镜像）
    python run_demo.py api docker       # 真实模型 + 容器沙箱（最接近生产）

真实模型配置全部读环境变量，不写死在代码里：
    export DEEPSEEK_API_KEY=sk-xxx
    export DAH_BASE_URL=https://api.deepseek.com/v1   # 可换成 Qwen/GLM/vLLM
    export DAH_MODEL=deepseek-chat
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from daharness.runner import run_benchmark
from daharness.report import render_report

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS_ROOT = os.path.join(HERE, "tasks")


def main() -> None:
    argv = sys.argv[1:]
    use_api = "api" in argv
    use_docker = "docker" in argv

    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if use_api and not api_key:
        print("[错误] 启用 api 模式但没设置 DEEPSEEK_API_KEY。\n"
              "       Linux/macOS: export DEEPSEEK_API_KEY=sk-xxx\n"
              "       Windows PS : $env:DEEPSEEK_API_KEY='sk-xxx'")
        sys.exit(1)

    # 重复次数可用环境变量覆盖（n=3 只能定性；下结论前建议 DAH_REPEATS=10）
    repeats = int(os.environ.get("DAH_REPEATS", "3"))

    config = {
        "tasks": ["sales_clean", "region_sql", "weekly_report", "taxi_clean"],
        "scaffolds": ["react", "plan_execute", "reflect_retry"],
        "repeats": repeats,
        "flaky": not use_api,   # Mock 模式注入 ≈50% 错误；真实模型天然有波动
        "env": "docker" if use_docker else "local",
        "model": None if not use_api else {
            "backend": "api",
            "name": os.environ.get("DAH_MODEL", "deepseek-chat"),
            "base_url": os.environ.get("DAH_BASE_URL",
                                       "https://api.deepseek.com/v1"),
            "api_key": api_key,
            "model": os.environ.get("DAH_MODEL", "deepseek-chat"),
        },
    }
    mock_note = "（真实 API）" if use_api else "（Mock flaky 模式）"
    env_note = "docker 容器沙箱" if use_docker else "本地 workspace"
    print(f"[1/2] 运行基准：{len(config['tasks'])} 任务 × 3 scaffold × {repeats} 重复 "
          f"{mock_note} | 环境：{env_note}")
    result = run_benchmark(config, TASKS_ROOT)

    out = os.path.join(HERE, "outputs", "report.md")
    render_report(result, out)
    print(f"[2/2] 报告已生成: {out}\n")
    print("===== 核心指标速览 =====")
    k = config["repeats"]
    for m in sorted(result["summary"].values(),
                    key=lambda x: (x["task"], x["scaffold"])):
        print(f"  {m['task']:<14} {m['scaffold']:<14} "
              f"pass@1={m['pass@1']:.2f}  pass^{k}={m['pass_k']:.2f}  "
              f"steps={m['avg_steps']:.1f}  tokens={m['avg_tokens']:.0f}")


if __name__ == "__main__":
    main()
