"""任务定义与内置任务数据生成。

任务 = 企业风格的数据分析场景。每个任务目录：
  task.json   —— 指令、检查器配置
  gen_data.py —— 首次运行时确定性生成数据（保证所有 agent 拿到完全相同的数据）
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field


@dataclass
class Task:
    task_id: str
    instruction: str
    checker: dict          # 评分器配置，见 scoring.py
    path: str              # 任务目录

    @property
    def data_dir(self) -> str:
        return os.path.join(self.path, "data")


def load_task(task_dir: str) -> Task:
    with open(os.path.join(task_dir, "task.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    return Task(task_id=cfg["task_id"], instruction=cfg["instruction"],
                checker=cfg["checker"], path=os.path.abspath(task_dir))


def ensure_task_data(task: Task) -> None:
    """确保任务数据存在（首次运行时生成，用固定种子保证确定性）。"""
    if os.path.isdir(task.data_dir) and os.listdir(task.data_dir):
        return
    os.makedirs(task.data_dir, exist_ok=True)
    gen = os.path.join(task.path, "gen_data.py")
    ns: dict = {}
    with open(gen, encoding="utf-8") as f:
        exec(compile(f.read(), gen, "exec"), ns)
    ns["generate"](task.data_dir)
