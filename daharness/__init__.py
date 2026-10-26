"""daharness — 面向数据分析任务的 Agent 评测 Harness
=====================================================
架构五要素（对标 Inspect AI / Terminal-Bench / Harbor 的标准范式）：
  task.py    任务定义   —— 每个任务 = 指令 + 数据 + 检查器（检查最终产物状态）
  env.py     沙箱环境   —— 每次运行一个隔离 workspace，工具: shell/sql/文件读写
  llm.py     模型后端   —— OpenAI 兼容 API + Mock 脚本模型（本地零成本演示）
  agents.py  Agent循环  —— 三种 scaffold: ReAct / Plan-and-Execute / Reflect-Retry
  scoring.py 评分器     —— 规则评分（结果比对），pass@1 与 pass^k 统计
"""

from .task import Task, load_task
from .env import SandboxEnv
from .llm import build_llm
from .agents import build_agent
from .runner import run_benchmark

__all__ = ["Task", "load_task", "SandboxEnv", "build_llm",
           "build_agent", "run_benchmark"]
