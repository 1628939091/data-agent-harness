# 项目二 Linux 一键跑通脚本
# 用法：
#   chmod +x linux_setup.sh && ./linux_setup.sh          # 本地模式
#   ./linux_setup.sh docker                              # 额外构建 Docker 镜像
#   DEEPSEEK_API_KEY=sk-xxx ./linux_setup.sh api         # 接真实模型
#
# 已在 Ubuntu 22.04 / 24.04 验证。CentOS/RHEL 把 apt 换成 dnf 即可。

set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$PROJECT_DIR"

echo "==== [1/5] 检查 Python 版本 ===="
# Ubuntu 24.04 自带 python3.12；部分老系统只有 3.8，本项目要求 >= 3.9
if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "[错误] 没找到 python3。安装：sudo apt update && sudo apt install -y python3 python3-venv"
  exit 1
fi
"$PY" -c 'import sys; assert sys.version_info >= (3, 9), "需要 Python >= 3.9"; print("  OK:", sys.version.split()[0], "@", sys.executable)'

echo "==== [2/5] 创建虚拟环境 ===="
if [ ! -d ".venv" ]; then
  "$PY" -m venv .venv || {
    echo "[错误] venv 创建失败。Ubuntu 需要：sudo apt install -y python3-venv"
    exit 1
  }
  echo "  已创建 .venv"
else
  echo "  .venv 已存在，跳过"
fi
# shellcheck disable=SC1091
source .venv/bin/activate
echo "  当前解释器：$(which python)"
python -c 'import sys; print("  venv python:", sys.version.split()[0])'

echo "==== [3/5] 依赖检查 ===="
# 本项目零第三方依赖（纯标准库），所以这里只做校验，不联网装包。
# 这是刻意设计：评测 harness 本身不能成为环境问题的来源。
python - <<'PY'
import importlib.util  # 必须显式导入子模块，import importlib 不包含 util
mods = ["json", "csv", "sqlite3", "subprocess", "tempfile", "urllib.request",
        "statistics", "random", "re"]
missing = [m for m in mods if importlib.util.find_spec(m) is None]
print("  标准库缺失:", missing or "无")
assert not missing, "标准库不完整，请重装 Python"
PY

echo "==== [4/5] 冒烟测试（单任务，10 秒内） ===="
python - <<'PY'
import sys, os
sys.path.insert(0, os.getcwd())
from daharness.task import load_task, ensure_task_data
from daharness.env import SandboxEnv
from daharness.llm import build_llm
from daharness.agents import build_agent
from daharness.scoring import check

t = load_task("tasks/sales_clean")
ensure_task_data(t)
env = SandboxEnv(t.data_dir)
llm = build_llm({"backend": "mock", "name": "smoke", "task_id": "sales_clean",
                 "scaffold": "react", "flaky": False, "run_seed": "smoke"})
build_agent("react", llm, env).solve(t)
ok, reason = check(t.checker, env.workspace, t.data_dir)
print(f"  sales_clean 单任务结果: {'PASS' if ok else 'FAIL'} | {reason}")
env.cleanup()
assert ok, "冒烟测试未通过，先别继续"
PY

echo "==== [5/5] 运行完整基准 ===="
if [ "${1:-}" = "api" ]; then
  if [ -z "${DEEPSEEK_API_KEY:-}" ]; then
    echo "[错误] api 模式需要先 export DEEPSEEK_API_KEY=sk-xxx"
    exit 1
  fi
  python run_demo.py api
elif [ "${1:-}" = "docker" ]; then
  echo "---- 构建 Docker 镜像 ----"
  docker build -f Dockerfile -t daharness-python:3.12 .
  python run_demo.py docker
else
  python run_demo.py
fi

echo
echo "==== 完成 ===="
echo "报告位置：$PROJECT_DIR/outputs/report.md"
echo "查看报告：cat outputs/report.md"
echo
echo "下次进入环境只需："
echo "  cd $PROJECT_DIR && source .venv/bin/activate"
