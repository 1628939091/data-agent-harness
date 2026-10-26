"""Docker 沙箱环境：与 SandboxEnv 接口完全一致，但每个任务跑在独立容器里。

为什么需要它（面试必答题）：
  1. **隔离**：agent 可以任意写 `rm -rf`、装包、跑死循环，容器一删全没了；
     tempfile 目录方案挡不住 `rm -rf ~`。
  2. **可复现**：镜像固定了 Python 版本和预装库，"我本地能跑"不再成立。
  3. **资源限制**：--memory / --cpus / --network none，防止 agent 挖矿或跑飞。
  4. **贴近生产**：真实 Agent 产品（Cursor、Claude Code、Manus）都是容器沙箱。

与 SandboxEnv 的唯一区别是 `_shell` 的实现：本地 -> `docker exec`。
换环境不改 agent 一行代码 —— 这就是 harness 的核心价值。

用法：
    from daharness.docker_env import DockerEnv
    env = DockerEnv(task.data_dir, image="daharness-python:3.12")
    ...
    env.cleanup()   # 停止并删除容器

要求：本机已装 Docker，且镜像已构建（见 linux_setup.sh）。
非 Linux/无 Docker 时自动回退到 SandboxEnv。
"""

from __future__ import annotations

import os
import shutil
import subprocess
import uuid

from .env import SandboxEnv


class DockerEnv(SandboxEnv):
    """继承 SandboxEnv，只替换 shell 执行方式与文件写入方式。"""

    def __init__(self, data_dir: str, image: str = "daharness-python:3.12",
                 db_file: str | None = None, timeout: int = 60,
                 memory: str = "1g", cpus: str = "2",
                 network: str = "none"):
        super().__init__(data_dir, db_file=db_file, timeout=timeout)
        self.image = image
        self.container = "daharness_" + uuid.uuid4().hex[:12]
        self._workdir = "/workspace"
        self.timeout = timeout
        # 1) 起容器：把 workspace 挂进去，等价于 SandboxEnv 里"数据已复制进 workspace"
        subprocess.run(
            ["docker", "run", "-d", "--name", self.container,
             "--memory", memory, "--cpus", cpus,
             f"--network={network}",
             "--workdir", self._workdir,
             "-v", f"{self.workspace}:{self._workdir}",
             self.image, "sleep", "infinity"],
            check=True, capture_output=True, text=True,
            encoding="utf-8", errors="replace")
        # 2) 数据库文件也在 workspace 里，容器内路径同步转换
        if db_file:
            self.db_file = os.path.join(self.workspace, os.path.basename(db_file))

    # ---------------- 覆盖：工具实现 ----------------
    def _shell(self, cmd: str) -> str:
        p = subprocess.run(
            ["docker", "exec", "--workdir", self._workdir, self.container,
             "bash", "-lc", cmd],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=self.timeout)
        out = (p.stdout or "") + (p.stderr or "")
        return (out or "(no output)")[:4000]

    def _sql(self, query: str) -> str:
        """容器内用 sqlite3 CLI 执行（只读模式），确保 agent 不能改数据。"""
        dbname = os.path.basename(self.db_file) if self.db_file else ""
        if not dbname:
            raise RuntimeError("本任务没有配置数据库")
        p = subprocess.run(
            ["docker", "exec", "--workdir", self._workdir, self.container,
             "sqlite3", "-readonly", f"file:{dbname}?mode=ro", query],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", timeout=self.timeout)
        out = (p.stdout or "") + (p.stderr or "")
        return (out or "(no output)")[:8000]

    def _write(self, rel: str, content: str) -> str:
        # 宿主机侧写入即可（workspace 已挂载进容器，双向可见）
        return super()._write(rel, content)

    def cleanup(self):
        subprocess.run(["docker", "rm", "-f", self.container],
                       capture_output=True)
        shutil.rmtree(self.workspace, ignore_errors=True)


def docker_available() -> bool:
    """环境探测：Docker 可用且镜像存在时返回 True。"""
    if not shutil.which("docker"):
        return False
    try:
        r = subprocess.run(["docker", "images", "-q", "daharness-python:3.12"],
                           capture_output=True, text=True, timeout=10)
        return bool(r.stdout.strip())
    except Exception:  # noqa: BLE001
        return False


def build_env(data_dir: str, db_file: str | None = None,
              prefer_docker: bool = True, **kw):
    """工厂：优先 Docker，不可用则回退本地 SandboxEnv。runner 只调这个。"""
    if prefer_docker and docker_available():
        return DockerEnv(data_dir, db_file=db_file, **kw)
    return SandboxEnv(data_dir, db_file=db_file, **kw)
