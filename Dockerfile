# Agent 沙箱镜像：固定版本 + 预装数据分析常用工具
# 构建：docker build -f Dockerfile -t daharness-python:3.12 .
# 用途：python run_demo.py docker  （每个任务一个容器，跑完即删）

FROM python:3.12-slim

# 数据分析 agent 真实会用到的工具链（也是评测维度的一部分：
# 环境里有什么，agent 就能用什么；缺少工具本身会让它失败）
RUN apt-get update && apt-get install -y --no-install-recommends \
        sqlite3 \
        jq \
        curl \
        ca-certificates \
        git \
    && rm -rf /var/lib/apt/lists/*

# 常用 Python 库（pandas/duckdb 是数据分析 agent 的主力）
RUN pip install --no-cache-dir \
        pandas==2.2.3 \
        duckdb==1.1.3 \
        pyarrow==18.1.0

# 非 root 用户：agent 不能有 root 权限（真实沙箱的基本要求）
RUN useradd -m -u 1000 agent
USER agent
WORKDIR /workspace

# 容器常驻，由 harness 用 docker exec 逐步驱动
CMD ["sleep", "infinity"]
