"""Agent 循环与三种 Scaffold —— 项目二的核心研究变量。

Scaffold（脚手架）= 包裹在模型外面的循环策略。同一个模型配不同 scaffold，
成绩可以差 20 个点（Terminal-Bench 论文的实证结论）——你的消融实验就在测这个：

  react          : 最朴素 —— 思考→行动→观测 循环直到 finish
  plan_execute   : 先用 plan 工具产出显式计划，再按计划行动
  reflect_retry  : ReAct 之外，检查失败后把失败原因喂回模型让它重试

Harness 的意义：三种 scaffold 跑在完全相同的环境/数据/评分器上，
差异才能归因到 scaffold 本身（matched-comparison，Harness-Bench 的设计思想）。
"""

from __future__ import annotations

import json
import re
import sys

from .llm import SYSTEM_PROMPT


def extract_action(text: str) -> dict | None:
    """从模型回复中抠出第一个合法 JSON 动作（对啰嗦/带代码块的回复也健壮）。"""
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None
    try:
        obj = json.loads(m.group(0))
        return obj if isinstance(obj, dict) and "tool" in obj else None
    except json.JSONDecodeError:
        return None


class BaseAgent:
    """通用 ReAct 循环。所有 scaffold 共享这个类，差异只在 runner 的调用方式。"""

    def __init__(self, llm, env, max_steps: int = 12):
        self.llm = llm
        self.env = env
        self.max_steps = max_steps

    def new_messages(self, instruction: str, extra: str = "") -> list[dict]:
        user = (f"# 任务\n{instruction}\n\n"
                f"# 工作目录\n数据文件就在当前工作目录下（如 sales_raw.csv、shop.db），"
                f"可直接 read_file 或用 shell 处理。\n"
                f"# 运行环境\n解释器是 {sys.executable}；如果 `python` 不在 PATH 里，"
                f"请用这个绝对路径执行脚本。\n")
        if extra:
            user += f"\n# 补充信息\n{extra}\n"
        return [{"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user}]

    def run_loop(self, messages: list[dict], first_action: dict | None = None) -> dict:
        """驱动 思考→行动→观测 循环，返回轨迹摘要。"""
        steps = 0
        action = first_action
        while steps < self.max_steps:
            if action is None:
                text = self.llm.chat(messages)
                messages.append({"role": "assistant", "content": text})
                action = extract_action(text)
                if action is None:
                    messages.append({"role": "user",
                                     "content": "输出格式错误：请只输出一个JSON动作 "
                                                '{"think":..., "tool":..., "args":...}'})
                    steps += 1
                    continue
            if action["tool"] == "finish":
                return {"steps": steps, "ok": True}
            obs = self.env.run_tool(action["tool"], action.get("args", {}))
            self.env.steps.append({"step": steps, "tool": action["tool"],
                                   "think": action.get("think", ""),
                                   "obs": obs[:200]})
            messages.append({"role": "user",
                             "content": f"观测：\n{obs}\n\n请继续输出下一个JSON动作。"})
            action = None
            steps += 1
        return {"steps": steps, "ok": False}

    def solve(self, task, feedback: str = "") -> dict:
        """子类覆写。默认 = ReAct。"""
        return self.run_loop(self.new_messages(task.instruction, feedback))


class PlanExecuteAgent(BaseAgent):
    """Plan-and-Execute：第一轮强制先产出计划，再进入普通循环。"""

    def solve(self, task, feedback: str = "") -> dict:
        messages = self.new_messages(task.instruction, feedback +
                                     "\n（要求：先用 plan 工具给出完整计划，再逐步执行）")
        plan_action = {"think": "先规划", "tool": "plan",
                       "args": {"plan": "理解数据 → 写脚本 → 执行 → 产出指定文件"}}
        self.env.steps.append({"step": 0, "tool": "plan",
                               "think": "scaffold 注入的计划轮", "obs": ""})
        return self.run_loop(messages, first_action=plan_action)


class ReflectRetryAgent(BaseAgent):
    """Reflect-Retry：普通循环 + 失败后带反馈重试（重试逻辑在 runner 中编排，
    因为"检查是否失败"需要评分器介入 —— 这体现了 harness 对 agent 的元控制）。"""
    pass


def build_agent(scaffold: str, llm, env) -> BaseAgent:
    if scaffold == "plan_execute":
        return PlanExecuteAgent(llm, env)
    # react 与 reflect_retry 的单轮循环相同，重试由 runner 编排
    return BaseAgent(llm, env)
