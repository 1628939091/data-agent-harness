# DataAgent-Harness — 面向数据分析任务的 Agent 评测 Harness

> 应用统计学研一 · 项目二 · 简历主力项目（Agent 岗 + 大数据开发岗双命中）
> **状态：Linux / Windows 均已跑通，零第三方依赖（纯标准库），Docker 沙箱可选**

## 一句话介绍

一个容器化的 Agent 评测运行时：**给数据分析 Agent 出题、给沙箱、自动判卷、统计 pass@1 / pass^k**——这就是大厂 Agent 基建团队（评测方向）日常工作的微缩版。

## 快速开始

```bash
# Linux / macOS 一键（推荐）
chmod +x linux_setup.sh && ./linux_setup.sh

# 手动（任意平台，Python >= 3.9）
python3 -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
python run_demo.py                # Mock 模型演示
python run_demo.py api            # 真实模型（需 DEEPSEEK_API_KEY）
python run_demo.py docker         # Docker 沙箱（需先构建镜像）
```

详细步骤（含 PyCharm 配置、常见报错、逐行代码导读）见
**`../../项目二_从零跑通与面试手册.md`**。

## 背景：为什么"harness"本身值得做成项目

2026 年的共识（Terminal-Bench 论文、Harness-Bench）：**同一个模型换一套 harness（脚手架/运行环境），成绩能差 20 个点**。所以：

- 评测结果 = 模型 × harness 的联合产物，harness 本身是研究对象；
- 大厂需要的人 = 能搭建"公平、可复现、自动化"评测体系的人 —— 本项目就是这样一个体系。

## 项目结构

```
data-agent-harness/
├── run_demo.py                 # 一键入口：4任务 × 3 scaffold × k重复
├── ab_env_prompt.py            # 环境告知 A/B 消融（两臂对跑，直接出差值表）
├── smoke_api.py                # 真实 API 单任务冒烟（先跑这个再跑全量）
├── linux_setup.sh              # Linux 一键部署（5 步，每步可验证）
├── Dockerfile                  # 沙箱镜像（sqlite3/jq/pandas/duckdb，非 root 用户）
├── daharness/
│   ├── task.py                 # 任务定义 = 指令 + 数据 + 检查器
│   ├── env.py                  # 沙箱环境（隔离workspace / shell / SQLite / 文件工具）
│   ├── docker_env.py           # 容器沙箱（接口与 env.py 完全一致）+ build_env 工厂
│   ├── llm.py                  # LLM后端（OpenAI兼容API + Mock剧本模型）
│   ├── agents.py               # Agent循环 + 3种scaffold
│   ├── scoring.py              # 规则评分器（只看最终产物，不看过程）
│   ├── runner.py               # 基准编排：pass@1 / pass^k / 成本统计
│   ├── metrics.py              # Bootstrap CI 等统计工具
│   └── report.py               # Markdown 报告生成
└── tasks/                      # 4个企业风格任务
    ├── sales_clean/            # 销售流水清洗（CSV脏数据：负数/重复/日期混杂）
    ├── region_sql/             # 区域销售额聚合（SQLite，含退款负数的统计口径坑）
    ├── weekly_report/          # 自动周报生成（数字必须对得上源数据）
    └── taxi_clean/             # ★真实数据清洗（NYC出租车2019-03公开数据，6433行底表）
```

## 核心设计决策（面试必聊）

1. **只看最终产物，不看过程**（学 Terminal-Bench）：评分器检查 `clean.csv` / `result.json` / `report.md` 的内容对不对，不管 agent 用了什么方法——保证对任何模型/任何 scaffold 公平。
2. **Provider 无关的动作协议**：模型每轮输出 `{"think":..., "tool":..., "args":...}` JSON，不用 OpenAI 原生 function calling——任何模型（包括没工具调用能力的）都能跑同一套 harness，跨模型对比才成立。
3. **环境与 agent 解耦**：`build_env()` 工厂——有 Docker 用容器（文件系统隔离 + 非 root + 断网 + 内存/CPU 上限），没有就回退本地临时目录，**agent 代码一行不改**。这就是"harness"的架构意义。
4. **金标准现场计算**：期望答案由检查器直接对源数据跑金标准 SQL/汇总算出，不维护静态答案文件——评测基准建设最容易踩的坑（答案和数据脱节）被结构性避免。
5. **异常即观测**：工具出错（含超时）全部转成观测文本返回给模型，不抛异常——agent 必须"看到"自己的错误才能反思。
6. **环境自述，提示词不撒谎**：解释器路径、可用库、目录文件清单都由 `env.describe()` 提供，
   本地后端与 Docker 后端各说各的真话；提示词只拿"环境元信息"，不拿任务内容（行列数、脏数据分布）。
7. **统计素养**：所有 pass@1 带 Bootstrap 95% CI；pass^k（k 次全对概率）作为上线可靠性指标——这是统计学生做工程项目的差异化标签。

## 三种 Scaffold（消融实验的研究变量）

| Scaffold | 机制 | 直觉 |
|---|---|---|
| react | 思考→行动→观测，循环到 finish | 最朴素，错了就错了 |
| plan_execute | 先强制产出一轮计划再执行 | 用规划换方向正确性 |
| reflect_retry | 失败后把评分反馈喂回模型重试 | 用 token 换可靠性 |

## Mock 演示结果（已跑通，解读给你听）

```
task           scaffold       pass@1  pass^3  steps  tokens
region_sql     react          0.00    0.00    2.0    306    ← 3 次全错：稳定失败
sales_clean    react          0.67    0.00    2.0    415    ← 单次看着能用
weekly_report  react          0.67    0.00    2.0    428
region_sql     plan_execute   0.33    0.00    5.0    362    ← 多一轮规划没救回来
sales_clean    plan_execute   0.67    0.00    5.0    466
weekly_report  plan_execute   0.67    0.00    5.0    479
*              reflect_retry  1.00    1.00   3.3   525-711 ← 全补救，token 涨约 50%
```

**这就是 pass^k 存在的意义**：pass@1 = 0.67 的 agent 看起来"还挺准"，但生产环境要求"每次都对"——pass^3 = 0 直接判死刑。Mock 的 flaky 模式注入的是真实 LLM 最常犯的错（漏去重规则、忘剔除退款、统计口径错），这三种错误你的消融实验都能捕捉到。

## 换真实模型

```bash
export DEEPSEEK_API_KEY=sk-xxx
python smoke_api.py           # 先单任务冒烟，看轨迹和失败模式
python run_demo.py api        # 全量

# 换任意 OpenAI 兼容端点（Qwen / GLM / vLLM 本地服务）
export DAH_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
export DAH_MODEL=qwen-plus
python smoke_api.py qwen-plus
```

实验参数同样走环境变量（默认值 = 上文 120 跑的口径）：

| 变量 | 作用 | 默认 |
|---|---|---|
| `DAH_REPEATS` | 每个配置重复次数 k | `3` |
| `DAH_ENV_PROMPT` | 提示词里补"只有标准库 + 文件清单" | `0`（关） |
| `DAH_OUT` | 报告文件名（A/B 时分开存） | `report.md` |

## 真实数据任务：taxi_clean（真实分布 + 受控污染）

前三个任务用合成数据（可复现、脏数据可控）；第四个任务接入**真实公开数据**：
NYC 出租车 2019-03 运营记录（seaborn `taxis` 数据集，6433 行 × 14 列，849 KB）。
真实数据自带天然脏数据（96 行 0 乘客、51 行里程≤0、26 行区域缺失），
唯一受控注入的是 40 条精确重复（模拟采集端重复上报，种子固定可复现）。

这就是企业评测的标准做法——**真实分布 + 受控污染**：比纯合成更可信
（模型的失败发生在真实数据形态上），比纯真实更可控（每一条脏数据都有
明确定义的金标准）。清洗规则：剔除无效行程（passengers=0 或 distance≤0）、
剔除区域缺失、精确去重，金标准由参考实现现场生成（`tasks/taxi_clean/gen_data.py`）。

```bash
python watch_agent.py taxi_clean react api   # 真实模型单次回放
```

## 真实模型结果：一次"评测污染"的发现与修复（deepseek-chat，重点面试素材）

### 干净数据（金标准隔离修复后，3 任务 × 3 scaffold × 3 重复）

```
task           scaffold       pass@1  pass^3  steps  tokens
region_sql     plan_execute   1.00    1.00    7.7    6395
region_sql     react          1.00    1.00    4.0    3939
region_sql     reflect_retry  1.00    1.00    4.0    3825
sales_clean    plan_execute   0.67    0.00    8.3   16286   ← 唯一失败列
sales_clean    react          1.00    1.00    6.3   34617   ← 全对，但 token 最贵
sales_clean    reflect_retry  1.00    1.00    6.0   14317   ← 性价比最优
weekly_report  plan_execute   1.00    1.00   10.7   12672
weekly_report  react          1.00    1.00    7.3   10215
weekly_report  reflect_retry  1.00    1.00    7.3   10709
```

### 我发现并修复了什么

第一版 `env.py` 把任务数据目录**全量**复制进 agent 的 workspace——包括
`sales_clean` 的金标准文件 `expected_clean.csv`。回放真实轨迹时发现模型
第 1 轮就"看到"了标准答案，第 5 轮直接拿它对比验证（`305 305 MATCH`），
且 `read_file("expected_clean.csv")` 这条抄答案路径也完全敞开——
这就是**评测污染（benchmark contamination）**：等于把答案发给了考生。

修复：引入金标准命名约定 `expected_* / golden_* / answer_*`，
初始化复制与 `read_file` 按需复制两处都过滤；评分器独立从数据目录读金标准，
不受影响。修复后重跑全部实验，替换本文所有数字。

### 修复前后结论翻转（n=3，最重要的教训）

| sales_clean | 修复前（污染） | 修复后（干净） |
|---|---|---|
| react | pass@1=0.33, pass^3=0, steps=2.0 | pass@1=1.00, pass^3=1.00, steps=6.3 |
| plan_execute | **1.00 / 1.00（唯一全过）** | **0.67 / 0.00（唯一失败）** |
| reflect_retry | 0.67 / 0.00 | 1.00 / 1.00 |

- **排名整体翻转**："plan_execute 唯一 3×3 全过"这个旧结论在干净环境下完全不成立——
  3 次重复的 scaffold 排名不可信，正对照已知局限 #1（CI 宽度 ±0.4）。
  下结论前必须加大重复次数（`$env:DAH_REPEATS="10"` 后重跑）。
- **任务真实变难了**：泄漏让模型可以"参考答案"；隔离后 react 的 steps 从 2.0 涨到 6.3、
  token 涨到 34.6k——模型必须自己试错出"先剔除再精确去重"的规则顺序。
- **性价比画像**（本次样本内）：react 全对但最贵（34.6k）；reflect_retry 用 41% 的
  token 达成同样全对；plan_execute 花 16.3k 却没买到可靠性——与 Mock 消融的方向一致。

一句话面试版：**"我在评测自己的 harness 时发现真模型读到了金标准文件——评测污染。
我把它隔离出沙箱、堵住 read_file 路径、重跑全部实验，发现 scaffold 排名整体翻转。
这件事让我对'小样本评测结论'和'评测环境隔离'都有了第一手敬畏。"**

### 终版实验：n=10 大样本（4 任务 × 3 scaffold × 10 重复 = 120 跑，deepseek-chat）

```
task           scaffold       pass@1  pass^10  steps  tokens
region_sql     plan_execute   1.00    1.00     7.2    6199
region_sql     react          1.00    1.00     5.7    6405
region_sql     reflect_retry  1.00    1.00     5.9    6784
sales_clean    plan_execute   1.00    1.00    11.1   25894
sales_clean    react          1.00    1.00     6.0   15271
sales_clean    reflect_retry  1.00    1.00     6.5   18178
taxi_clean     plan_execute   1.00    1.00    10.8   16728
taxi_clean     react          1.00    1.00     8.2   13980
taxi_clean     reflect_retry  1.00    1.00     8.4   14387
weekly_report  plan_execute   1.00    1.00    11.7   15483
weekly_report  react          1.00    1.00     8.4   13514
weekly_report  reflect_retry  1.00    1.00     7.6   14094
```

> **这批数字的采集条件**：跑于 2026-10-26，当时 `task.json` 里的数据路径还写着 `data/xxx`
> （与沙箱实际布局不符），且提示词未告知"环境只有标准库"。因此表中的 **steps / tokens
> 含约 1 轮无效探索**，属"偏悲观"的成本估计；pass 率不受影响（120/120 全过）。
> 两个问题已在 2026-10-27 修复（见下文"环境告知 A/B"），修复后口径可用 `DAH_ENV_PROMPT=0` 重跑复现。

**结论 1：可靠性饱和**。120/120 全过——对 deepseek-chat 这个强度的模型，4 个任务的
通过率已无区分度。这不是实验失败，是基准建设的真实困境：**模型变强的速度远快于任务**，
继续出圈必须加难任务（见扩展方向的任务模板化生成器）。

**结论 2：区分度转移到成本维度**。全可靠的前提下，比的是 token 和步数：

| scaffold | 相对成本 | 生产解读 |
|---|---|---|
| react | 基准（最省） | 强模型 + 事后评测兜底时，朴素循环性价比最高 |
| reflect_retry | +0~20% | 廉价保险：多花的钱买"失败自动重试"的心理安全垫 |
| plan_execute | **+20~70%** | 对强模型是纯开销：规划轮数（steps 普遍多 2-4 轮）没换来任何可靠性 |

**结论 3：scaffold 的价值取决于模型强度**。Mock 弱模型时 reflect_retry 是"唯一 3×3
全过的救命稻草"；换成 deepseek-chat 后 react 反而最划算。**同一个 harness，换模型
就翻转 scaffold 排名**——这正是"harness 本身是研究对象"的直接证据。

一句话终版面试话术：**"我用 120 次评测发现：对强模型，pass 率会饱和，此时 scaffold
选型的决策变量从可靠性变成成本——plan_execute 比 react 贵 70% 却买不到任何东西。
这个结论如果只跑 3 次是得不出来的，我中途就被小样本翻转过一次排名。"**

### 环境告知 A/B：一句提示词的降本实验（`DAH_ENV_PROMPT`）

轨迹分析里最明显的浪费是**环境摸索**：模型先 `import pandas` 撞墙，再猜数据在哪个目录，
3 轮之后才开始干活。这两件事都属于"环境事实"，harness 完全可以告诉它：

```
# 运行环境（臂 B 多出的两行）
环境里只有 Python 标准库（没有 pandas / numpy），请用 csv、sqlite3 等标准库处理。
当前目录下已有文件：trips_raw.csv。
```

- **默认关闭**：保持与上面 120 跑的口径可比，也让这个开关本身成为一组消融实验。
- **环境事实由环境自己回答**：`SandboxEnv.describe()` / `DockerEnv.describe()` 各说真话
  （本地后端是宿主机 Python，Docker 后端是容器里的 `python3` 且装有 pandas），
  提示词里不硬写任何路径。
- **只给环境元信息，不给任务内容**：文件清单可以给，行列数和脏数据分布不给——
  否则测的就不是"会不会探索"，而是"会不会照着做"。

一键跑两臂并打印差值：

```bash
python ab_env_prompt.py api 3     # 4 任务 × 3 scaffold × 3 重复 × 2 臂 = 72 跑
```

顺带修掉两个会让提示词"说假话"的 bug：四个 `task.json` 里写的 `data/xxx` 路径与沙箱
实际布局不符（文件在 workspace 根目录）；以及 `agents.py` 用 `sys.executable` 硬编码解释器，
在 Docker 后端下必然错误。

## 已知局限（写在前面，别等被问）

1. **只有 4 个任务**（默认 `repeats=3`，终版实验用 `DAH_REPEATS=10`）。任务数太少，
   scaffold 排名在 n=3 下曾整体翻转（见上文），即使 n=10 全 1.00 也只能定性。
   下一步：模板化生成 400 个任务（表结构 × 口径 × 脏数据类型 × 问法）。
2. **`plan_execute` 的计划是硬编码字符串**（`agents.py`），所以它测的是"多一轮规划的开销"，不是"模型自主规划能力"。
3. **`reflect_retry` 未做预算对齐**：它允许 2 次尝试而 react 只 1 次，所以"提升"里混着"多跑一次"的收益。严格对比应固定总 token 或总步数。
4. **`csv_equals` 要求列序行序完全一致**，agent 换个合理排序会被误判。
5. **同步串行执行**，`timeout=60` 对长任务不够。

## 扩展方向

- 任务模板化生成器（`task_gen.py`）→ 400 个任务 + 自动金标准
- 部分分评分（行级 F1）+ 失败归因自动分类
- 并行跑批（每任务一容器）+ 结果入库 + Web 看板
- 接 LangGraph / 官方 scaffold 做第三方对照
- GitHub Actions CI：每次 push 跑 smoke
- 把消融实验写成 tech report 发博客，积累影响力

生产落地与企业数据扩展路径（四层递进：合成 → 模板化 → 真实工单 → 影子流量）见
**`../../项目二_生产落地与企业数据扩展.md`**。
