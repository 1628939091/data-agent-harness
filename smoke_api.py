# -*- coding: utf-8 -*-
"""真实 API 冒烟测试：先用 1 个任务 1 次，确认模型能跑通，再跑全量。

为什么需要它：
    Mock 模型永远听话，真实模型不会。常见坑有三个，这个脚本逐个暴露：
      1. 模型不输出纯 JSON（包了 ```json 代码块、或先写一段解释）
      2. 模型用 `python work.py` 而 PATH 里只有 python3（Ubuntu 24.04 默认）
      3. 模型提前 finish 但没写产物文件

用法：
    export DEEPSEEK_API_KEY=sk-xxx
    python smoke_api.py                       # 默认 deepseek-chat
    python smoke_api.py qwen-plus             # 换模型（仍需 DAH_BASE_URL 对应）
    DAH_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1 \
      DAH_MODEL=qwen-plus python smoke_api.py

成本：1 任务 × 1 scaffold × 1 次 ≈ 10 轮以内，几分钱。
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from daharness.task import load_task, ensure_task_data
from daharness.env import SandboxEnv
from daharness.llm import build_llm
from daharness.agents import build_agent
from daharness.scoring import check

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    # 密钥只从环境变量读，绝不写进代码——代码是要传 GitHub 的，
    # key 一旦进了文件，push 出去等于公开泄露（GitHub 爬虫几分钟就会扫到）
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("[错误] 没设置 DEEPSEEK_API_KEY")
        return 1

    model = sys.argv[1] if len(sys.argv) > 1 else os.environ.get("DAH_MODEL", "deepseek-chat")
    base_url = os.environ.get("DAH_BASE_URL", "https://api.deepseek.com/v1")
    task_id = os.environ.get("DAH_SMOKE_TASK", "region_sql")

    print(f"模型: {model}\n端点: {base_url}\n任务: {task_id}\n" + "-" * 60)

    task = load_task(os.path.join(HERE, "tasks", task_id))
    ensure_task_data(task)
    db = os.path.join(task.data_dir, "shop.db") if task_id == "region_sql" else None

    env = SandboxEnv(task.data_dir, db_file=db)
    try:
        llm = build_llm({"backend": "api", "name": model, "base_url": base_url,
                         "api_key": api_key, "model": model})
        agent = build_agent("react", llm, env)
        try:
            agent.solve(task)
        except Exception as e:  # noqa: BLE001
            print(f"[失败] 调用模型出错: {type(e).__name__}: {e}")
            print("\n排查顺序：")
            print("  1) key 有没有空格/引号  2) base_url 是否以 /v1 结尾")
            print("  3) 模型名是否存在  4) 是否需要代理")
            return 2

        ok, reason = check(task.checker, env.workspace, task.data_dir)
        print(f"\n结果: {'PASS' if ok else 'FAIL'} | {reason}")
        print(f"token: {llm.total_tokens}  步数: {len(env.steps)}")
        print("\n---- 轨迹 ----")
        for s in env.steps:
            print(f"[{s['step']}] {s['tool']}: {s['think'][:60]}")
            print(f"     obs: {s['obs'][:160].replace(chr(10), ' ')}")

        # 诊断常见失败模式
        if not ok:
            files = os.listdir(env.workspace)
            print(f"\n---- workspace 实际文件 ----\n{files}")
            if any("```" in s["think"] for s in env.steps):
                print("[诊断] 模型输出带 markdown 代码块，extract_action 只取第一个 {...}，"
                      "可能需要更稳的 JSON 提取")
            if any("not found" in s["obs"] or "未找到" in s["obs"] for s in env.steps):
                print("[诊断] 命令不存在 —— 很可能是 `python` 不在 PATH，"
                      "检查 payload 里是否提示了绝对路径")
        return 0 if ok else 3
    finally:
        env.cleanup()


if __name__ == "__main__":
    raise SystemExit(main())
