# -*- coding: utf-8 -*-
"""不用调试器也能看轨迹：跑 1 个任务 × 1 个 scaffold，把每一轮打印出来。

练习 1 的替代方案——如果你在 PyCharm 调试器里看不到变量，直接用这个：

    python watch_agent.py                            # Mock：sales_clean × react
    python watch_agent.py region_sql react           # Mock：看稳定失败的任务
    python watch_agent.py sales_clean react api      # 真实模型（需 DEEPSEEK_API_KEY）
                                                     # ← 用这个回放真模型的失败轨迹
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from daharness.task import load_task, ensure_task_data
from daharness.env import SandboxEnv
from daharness.llm import build_llm
from daharness.agents import build_agent, env_prompt_enabled
from daharness.scoring import check

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS_ROOT = os.path.join(HERE, "tasks")


def main() -> None:
    # 参数宽容处理：api 写在第几个位置都行（如 `api`、`sales_clean react api`），
    # 剩下的按 [任务名, scaffold] 顺序取，缺省 sales_clean × react
    args = [a for a in sys.argv[1:] if a != "api"]
    use_api = any(a == "api" for a in sys.argv[1:])
    task_id = args[0] if len(args) > 0 else "sales_clean"
    scaffold = args[1] if len(args) > 1 else "react"

    task = load_task(os.path.join(TASKS_ROOT, task_id))
    ensure_task_data(task)
    db = os.path.join(task.data_dir, "shop.db") if task_id == "region_sql" else None

    env = SandboxEnv(task.data_dir, db_file=db)
    if use_api:
        key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
        if not key:
            print("[错误] api 模式需要 DEEPSEEK_API_KEY，但当前终端里没有这个变量。")
            print("  PyCharm 的 Run Configuration 里填的变量只在「点三角运行」时生效，")
            print("  下方的终端是另一个进程，需要在本窗口里重新设置一次（只对当前窗口有效）：")
            print("")
            print('    PowerShell:  $env:DEEPSEEK_API_KEY = "sk-你的key"')
            print('    CMD:         set DEEPSEEK_API_KEY=sk-你的key')
            print('    Git Bash:    export DEEPSEEK_API_KEY="sk-你的key"')
            print("")
            print("  设置完再跑同一条命令；关掉这个终端窗口就失效，下次要重设。")
            sys.exit(1)
        cfg = {"backend": "api", "name": os.environ.get("DAH_MODEL", "deepseek-chat"),
               "base_url": os.environ.get("DAH_BASE_URL",
                                          "https://api.deepseek.com/v1"),
               "api_key": key, "model": os.environ.get("DAH_MODEL", "deepseek-chat")}
        tag = f"真实模型 {cfg['model']}"
    else:
        cfg = {"backend": "mock", "name": "mock", "task_id": task_id,
               "scaffold": scaffold, "flaky": True,
               "run_seed": task_id + scaffold}
        tag = "Mock flaky"
    llm = build_llm(cfg)
    agent = build_agent(scaffold, llm, env)

    agent.solve(task)
    ok, reason = check(task.checker, env.workspace, task.data_dir)

    arm = "环境告知=开" if env_prompt_enabled() else "环境告知=关"
    print(f"\n========== 轨迹回放：{task_id} × {scaffold}（{tag}，{arm}）"
          f" | 判卷: {'PASS' if ok else 'FAIL'} ({reason}) ==========")
    print(f"token 消耗: {llm.total_tokens}")
    for s in env.steps:
        print(f"\n--- 第 {s['step']} 轮 | 模型选的工具: {s['tool']} ---")
        if s["think"]:
            print(f"  模型想: {s['think']}")
        print(f"  环境回: {s['obs'][:300]}")
    env.cleanup()


if __name__ == "__main__":
    main()
