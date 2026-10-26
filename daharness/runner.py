"""基准编排器：任务 × scaffold × 重复次数 → pass@1 / pass^k / 成本。

核心统计（与项目一共享思想，两份简历互相呼应）：
  pass@1 : 单次运行成功率
  pass^k : k 次运行全部成功的任务占比（tau-bench 式可靠性 —— 上线前必须看这个）
"""

from __future__ import annotations

import os
import time
from collections import defaultdict

from .task import load_task, ensure_task_data
from .env import SandboxEnv
from .docker_env import build_env
from .llm import build_llm
from .agents import build_agent, BaseAgent, PlanExecuteAgent, ReflectRetryAgent
from .scoring import check
from .metrics import mean, bootstrap_ci


def run_benchmark(config: dict, tasks_root: str) -> dict:
    """config: {"tasks":[task_id...], "scaffolds":[...], "repeats":k,
                "model": {...}|None, "flaky": bool}
    model 为 None 时用 MockLLM（按任务×scaffold 自动构建）。"""
    results = []
    k = config.get("repeats", 3)
    # env：local（默认，tempfile 目录）| docker（容器隔离，需 Docker）| auto（有则用）
    env_mode = config.get("env", "local")
    prefer_docker = env_mode in ("docker", "auto")

    for task_id in config["tasks"]:
        task = load_task(os.path.join(tasks_root, task_id))
        ensure_task_data(task)
        db = os.path.join(task.data_dir, "shop.db") \
            if task_id == "region_sql" else None

        for scaffold in config["scaffolds"]:
            for rep in range(k):
                env = build_env(task.data_dir, db_file=db,
                                prefer_docker=prefer_docker)
                try:
                    mcfg = dict(config["model"] or {
                        "backend": "mock", "name": f"mock-{scaffold}",
                        "task_id": task_id, "scaffold": scaffold,
                        "flaky": config.get("flaky", False)})
                    if mcfg["backend"] == "mock":
                        mcfg.setdefault("task_id", task_id)
                        mcfg.setdefault("scaffold", scaffold)
                        mcfg.setdefault("flaky", config.get("flaky", False))
                    mcfg.setdefault("run_seed", f"{task_id}|{scaffold}|{rep}")
                    llm = build_llm(mcfg)
                    agent = build_agent(scaffold, llm, env)
                    t0 = time.time()
                    _run_with_scaffold(agent, task, scaffold, max_attempts=2)
                    wall = time.time() - t0
                    ok, reason = check(task.checker, env.workspace,
                                       task.data_dir)
                    results.append({
                        "task": task_id, "scaffold": scaffold, "rep": rep,
                        "ok": float(ok), "reason": reason,
                        "steps": len(env.steps),
                        "tokens": llm.total_tokens, "wall": wall,
                        "trajectory": list(env.steps),
                    })
                finally:
                    env.cleanup()
    return {"records": results, "k": k, "summary": _summarize(results, k)}


def _run_with_scaffold(agent: BaseAgent, task, scaffold: str,
                       max_attempts: int = 2) -> None:
    """scaffold 的差异在这里落地：
       react          : 跑一次就结束
       plan_execute   : PlanExecuteAgent.solve 注入计划轮
       reflect_retry  : 失败后带评分反馈重跑（最多 max_attempts 次）"""
    if scaffold == "plan_execute":
        agent.solve(task)
        return
    # react / reflect_retry
    feedback = ""
    for attempt in range(max_attempts):
        agent.solve(task, feedback)
        ok, reason = check(task.checker, agent.env.workspace, task.data_dir)
        if ok:
            return
        if scaffold != "reflect_retry":
            return  # react：失败也不重试 —— 这就是它和 reflect 的区别
        feedback = f"上一次尝试未通过检查：{reason}。请修正后重新完成任务。"


def _summarize(records, k: int) -> dict:
    out = {}
    by_pair = defaultdict(list)
    for r in records:
        by_pair[(r["task"], r["scaffold"])].append(r)
    for (task, scaffold), rs in by_pair.items():
        ok_flags = [bool(r["ok"]) for r in rs]
        p1, lo, hi = bootstrap_ci(ok_flags)
        all_ok = mean(1.0 if all(bool(x["ok"]) for x in rs[i:i + k]) else 0.0
                      for i in range(0, len(rs) - k + 1, k)) if len(rs) >= k else 0.0
        # pass^k 标准定义：每个任务 k 次全过的概率；这里任务粒度 = task
        per_task = defaultdict(list)
        for r in rs:
            per_task[r["task"]].append(bool(r["ok"]))
        passk = mean(1.0 if all(v) else 0.0 for v in per_task.values()) \
            if per_task else 0.0
        out[f"{task}|{scaffold}"] = {
            "task": task, "scaffold": scaffold,
            "pass@1": p1, "ci": (lo, hi), "pass_k": passk,
            "avg_steps": mean(r["steps"] for r in rs),
            "avg_tokens": mean(r["tokens"] for r in rs),
            "avg_wall": mean(r["wall"] for r in rs),
        }
    return out
