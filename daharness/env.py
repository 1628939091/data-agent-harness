"""沙箱环境：Agent 的工作台。

每次评测运行分配一个独立 workspace 目录（真实部署时换成 Docker 容器，
接口完全一致 —— 这就是 harness 的价值：环境与 agent 解耦）。

可用工具（Agent 通过 JSON 动作调用）：
  shell       执行命令（超时保护，cwd=workspace）
  sql         在任务 SQLite 数据库上执行查询（只读连接）
  write_file  写文件到 workspace
  read_file   读 workspace 里的文件
  finish      声明完成
"""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile

# 金标准文件的命名约定：这些前缀的文件是评分用的标准答案，
# 绝不能进入 agent 的 workspace —— 否则模型"自检"甚至直接抄答案，
# 评测就被污染了（benchmark contamination）。
GOLDEN_PREFIXES = ("expected_", "golden_", "answer_")


class SandboxEnv:
    def __init__(self, data_dir: str, db_file: str | None = None,
                 timeout: int = 60):
        self.workspace = tempfile.mkdtemp(prefix="daharness_")
        self.data_dir = os.path.abspath(data_dir)
        self.db_file = os.path.abspath(db_file) if db_file else None
        self.timeout = timeout
        self.steps: list[dict] = []
        # 把任务数据复制进 workspace：agent 的脚本用相对路径就能读到数据，
        # 同时原始数据目录保持只读（隔离原则：任务数据不可被 agent 污染）。
        # 金标准文件（expected_*）只留在 data_dir 供评分器使用，不复制。
        for name in os.listdir(self.data_dir):
            if name.startswith(GOLDEN_PREFIXES):
                continue
            src = os.path.join(self.data_dir, name)
            if os.path.isfile(src):
                shutil.copy(src, os.path.join(self.workspace, name))

    # ---------------- 工具实现 ----------------
    def run_tool(self, tool: str, args: dict) -> str:
        """执行一个工具调用，返回观测文本。所有异常都转成观测而不是崩溃 ——
        Agent 需要"看到"自己的错误才能反思重试。"""
        try:
            if tool == "shell":
                return self._shell(args.get("cmd", ""))
            if tool == "sql":
                return self._sql(args.get("query", ""))
            if tool == "write_file":
                return self._write(args.get("path", ""), args.get("content", ""))
            if tool == "read_file":
                return self._read(args.get("path", ""))
            if tool == "finish":
                return "任务声明完成"
            if tool == "plan":
                return "计划已记录"
            return f"[error] 未知工具: {tool}"
        except Exception as e:  # noqa: BLE001
            return f"[error] {type(e).__name__}: {e}"

    def _shell(self, cmd: str) -> str:
        try:
            # encoding 必须显式指定：Windows 中文系统默认 GBK，而 agent 脚本
            # 输出的是 UTF-8（如周报里的中文），GBK 解码会直接 UnicodeDecodeError。
            # errors="replace" 保证任何字节流都不会让 reader 线程崩溃。
            p = subprocess.run(cmd, shell=True, capture_output=True, text=True,
                               encoding="utf-8", errors="replace",
                               timeout=self.timeout, cwd=self.workspace)
        except subprocess.TimeoutExpired:
            # 超时是最常见的 agent 失败模式（死循环 / 等交互输入），必须变成观测
            return f"[error] 命令超时（>{self.timeout}s）：{cmd[:120]}"
        out = (p.stdout or "") + (p.stderr or "")
        return (out or "(no output)")[:4000]

    def _sql(self, query: str) -> str:
        if not self.db_file:
            raise RuntimeError("本任务没有配置数据库")
        con = sqlite3.connect(f"file:{self.db_file}?mode=ro", uri=True)
        try:
            cur = con.execute(query)
            rows = cur.fetchall()
            cols = [d[0] for d in cur.description] if cur.description else []
        finally:
            con.close()
        return " | ".join(cols) + "\n" + "\n".join(
            " | ".join(str(v) for v in r) for r in rows[:100])

    def _write(self, rel: str, content: str) -> str:
        # 防目录逃逸：只允许写 workspace 内
        path = os.path.abspath(os.path.join(self.workspace, rel))
        if not path.startswith(os.path.abspath(self.workspace)):
            raise RuntimeError("禁止写出 workspace")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(content)
        return f"已写入 {rel} ({len(content)} 字符)"

    def _read(self, rel: str) -> str:
        # read_file 同样不得读到金标准：按需复制时也过滤掉（堵住另一条泄漏路径）
        if os.path.basename(rel).startswith(GOLDEN_PREFIXES):
            return f"[error] 文件 {rel} 不存在或不可读"
        src = os.path.join(self.data_dir, rel)
        dst = os.path.join(self.workspace, rel)
        if os.path.exists(src) and not os.path.exists(dst):
            os.makedirs(os.path.dirname(dst) or ".", exist_ok=True)
            shutil.copy(src, dst)
        with open(dst, encoding="utf-8") as f:
            return f.read(4000)

    def cleanup(self):
        shutil.rmtree(self.workspace, ignore_errors=True)
