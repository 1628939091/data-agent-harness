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

### 基线实验：n=10（4 任务 × 3 scaffold × 10 重复 = 120 跑，deepseek-chat）

```
task           scaffold       pass@1  pass^10  steps  tokens
region_sql     plan_execute   1.00    1.00     6.2    4591
region_sql     react          1.00    1.00     3.3    3371
region_sql     reflect_retry  1.00    1.00     4.4    4915
sales_clean    plan_execute   0.90    0.00     9.2    28901
sales_clean    react          0.80    0.00     4.7    8756
sales_clean    reflect_retry  1.00    1.00     6.7    12453
taxi_clean     plan_execute   1.00    1.00     8.1    11814
taxi_clean     react          1.00    1.00     5.7    9430
taxi_clean     reflect_retry  1.00    1.00     6.2    10005
weekly_report  plan_execute   0.90    0.00     7.4    14619
weekly_report  react          1.00    1.00     4.0    9316
weekly_report  reflect_retry  1.00    1.00     3.9    8934
```

> 本表为 **2026-10-27 修复后口径**（`DAH_ENV_PROMPT=0`）。2026-10-26 那版 n=10
> 是在"考题写假路径"的 bug 下采的：steps/tokens 偏悲观（平均 8.1 步 / 13910 token），
> 且 120/120 全过的"饱和"可能部分是假路径逼出的多余探索——修复后基线出现 3 个
> 零星失败格，接近但未完全饱和。是 bug 还是抽样波动，要等任务模板化才能定论。

**结论 1：修掉"错误信息"是最大的单笔降本**。对比修复前后两版 n=120 基线：
平均步数 8.1 → 5.8（**-28%**）、平均 token 13910 → 10592（**-24%**），改动只有
删除考题里的 4 处假路径。**错误信息比缺失信息贵得多**——这条结论效应量大，
比后面任何提示词实验都稳。

**结论 2：区分度主要在成本维度**。pass@1 总体 0.97，可靠性差距只在 sales_clean
偶发（n=10 下 0.80/0.90，单格 Fisher 检验均不显著）；成本上 plan_execute（14.9k）
比 react（7.7k）贵约 90%，多出的是规划与核对步数，不是探索。生产默认选 react，
要"计划可审计"才付 plan_execute 的溢价。

**结论 3：scaffold 的价值取决于模型与任务**。Mock 弱模型时 reflect_retry 是
"唯一全过"；deepseek-chat 上 react 最省。**同一个 harness，换模型就翻转排名**——
这正是"harness 本身是研究对象"的直接证据。

一句话面试话术：**"我用两轮 n=10 共 360 次真实评测发现：最大的降本来自修掉考题里
的错误信息（token -24%）；而'补上正确的环境信息'反而 +11%——提示词改动的效果是
scaffold × prompt 的交互效应，必须分层 A/B，总平均会骗人。"**

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

**实测结果（n=10，两臂各 120 跑，2026-10-27）**：试点 n=3 的"省 token"预期被推翻，
且总平均（+10.9% token）会掩盖全部机制——必须按 scaffold 分层看：

| scaffold | 步数 A→B | token A→B | pass@1 A→B | pass^10 A→B |
|---|---|---|---|---|
| react | 4.4 → 5.2 | 7718 → 10972（**+42%**） | 0.95 → 0.95 | 0.75 → **0.50** |
| plan_execute | 7.7 → 7.9 | 14982 → 13142（**-12%**） | 0.95 → 1.00 | 0.50 → **1.00** |
| reflect_retry | 5.3 → 5.2 | 9077 → 11117（**+22%**） | 1.00 → 1.00 | 1.00 → 1.00 |

三条结论：

1. **没有免费的降本**。同一句环境告知：对 react 是净伤害——模型拿"文件清单"当
   "已了解数据"，跳过读表头那轮（pass@1 总体不变但 pass^10 掉一半）；对
   reflect_retry 是纯浪费（首轮失败率上升 → 重试放大成本 +22%）；只有 plan_execute
   净受益（-12% token 且 40/40 全过——它的硬编码计划本来就会读结构，文件清单
   恰好补上了"该读哪个文件"这个信息缺口）。
2. **提示词效果是 scaffold × prompt 的交互效应，不是模型级属性**。不存在"全局
   有用的一句话"；本实验后开关默认保持关闭。
3. **与结论 1 互为印证**：让模型"少探索"的两种方式——考题假路径引发的绕路除外——
   错误信息让它多探索（旧基线更稳更贵），环境清单让它少探索（新臂 B 更省但
   react 上更不稳）。**探索轮里混着"真浪费"和"必要认知"，harness 无法先验区分，
   只能靠 A/B 量。**

统计口径：pass@1 总体 38/40 → 39/40（Fisher p≈1.0，无差异）；pass^10 在 k=10 时
每格只有 0/1 两个取值，作聚合指标噪声大，解读以 pass@1 + token 为主。
单格层级所有差异均未过显著性检验——本节结论是"方向与机制"，不是精确效应量。

一键复现：

```bash
python ab_env_prompt.py api 10    # 4 任务 × 3 scaffold × 10 重复 × 2 臂 = 240 跑
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
