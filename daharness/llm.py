"""LLM 后端：OpenAI 兼容 API + Mock 脚本模型。

Agent 与模型的约定（Provider 无关，这是 harness 设计的关键决策）：
模型每轮输出一个 JSON 动作：
    {"think": "推理过程", "tool": "shell|sql|write_file|read_file|plan|finish",
     "args": {...}}
不用 OpenAI 原生 function calling，是为了任何模型（含无工具调用能力的）
都能跑同一套 harness —— 也让你能做公平的跨模型对比。
"""

from __future__ import annotations

import json
import sys
import urllib.request

SYSTEM_PROMPT = """你是数据分析 Agent。每轮只输出一个 JSON 对象：
{"think": "简短推理", "tool": "shell|sql|write_file|read_file|plan|finish", "args": {...}}
工具说明：
- shell: {"cmd": "..."}  在工作目录执行命令（可用 python）
- sql:   {"query": "..."} 只读查询 SQLite
- write_file: {"path": "...", "content": "..."}
- read_file:  {"path": "..."}
- plan: {"plan": "..."}  记录计划（Plan-and-Execute scaffold 用）
- finish: {}  完成任务（产物文件必须已写好）
"""


def build_llm(cfg: dict):
    if cfg["backend"] == "mock":
        return MockLLM(cfg)
    if cfg["backend"] == "api":
        return OpenAICompatLLM(cfg)
    raise ValueError(f"unknown backend {cfg['backend']}")


class OpenAICompatLLM:
    """任何 OpenAI 兼容端点：DeepSeek / Qwen / GLM / vLLM 本地服务。"""

    def __init__(self, cfg: dict):
        self.name = cfg.get("name", cfg["model"])
        self.base_url = cfg["base_url"].rstrip("/")
        self.api_key = cfg["api_key"]
        self.model = cfg["model"]
        self.total_tokens = 0

    def chat(self, messages: list[dict]) -> str:
        payload = json.dumps({"model": self.model, "messages": messages,
                              "temperature": 0.2}).encode()
        req = urllib.request.Request(
            self.base_url + "/chat/completions", data=payload,
            headers={"Content-Type": "application/json",
                     "Authorization": f"Bearer {self.api_key}"})
        with urllib.request.urlopen(req, timeout=180) as resp:
            data = json.loads(resp.read())
        self.total_tokens += data.get("usage", {}).get("total_tokens", 0)
        return data["choices"][0]["message"]["content"]


# ==========================================================================
# Mock 剧本：模拟真实 Agent 的行为轨迹（写脚本 → 执行 → 完成）
# 每个任务两版剧本：
#   good —— 正确完成
#   bad  —— 注入一个"典型人类/LLM错误"，用于演示 pass^k 与 Reflect 的价值
# ==========================================================================

def _steps(code: str) -> list[dict]:
    # 注意：用绝对路径调 python，而不是 `python work.py`。
    # 真实机器的 PATH 里可能没有 python（只有 python3），Ubuntu 24.04 默认就没有。
    # Mock 用 sys.executable 保证和 harness 同一个解释器；API 模型则必须自己写对。
    return [
        {"think": "写处理脚本", "tool": "write_file",
         "args": {"path": "work.py", "content": code}},
        {"think": "执行脚本", "tool": "shell",
         "args": {"cmd": f'"{sys.executable}" work.py'}},
        {"think": "完成", "tool": "finish", "args": {}},
    ]


PLAN_TURN = {"think": "制定计划：①理解数据 ②写脚本 ③执行 ④产出指定文件",
             "tool": "plan",
             "args": {"plan": "理解数据 → 写脚本 → 执行 → 产出指定文件"}}

_SCRIPTS: dict[str, dict] = {
    # ---------------- 任务1：销售数据清洗 ----------------
    # bad 版：漏掉"精确去重"规则 → clean.csv 比标准答案多行 → 检查器判负
    "sales_clean": {
        "good": _steps(
            "import csv\n"
            "rows = list(csv.DictReader(open('sales_raw.csv', encoding='utf-8')))\n"
            "out, seen = [], set()\n"
            "for r in rows:\n"
            "    if int(r['qty']) <= 0:\n"
            "        continue\n"
            "    key = tuple(sorted(r.items()))\n"
            "    if key in seen:\n"
            "        continue\n"
            "    seen.add(key)\n"
            "    d = r['date']\n"
            "    if '/' in d:\n"
            "        y, m, day = d.split('/')\n"
            "        r['date'] = f'{y}-{int(m):02d}-{int(day):02d}'\n"
            "    out.append(r)\n"
            "with open('clean.csv', 'w', newline='', encoding='utf-8') as f:\n"
            "    w = csv.DictWriter(f, fieldnames=rows[0].keys())\n"
            "    w.writeheader()\n"
            "    w.writerows(out)\n"
            "print('rows:', len(out))\n"),
        "bad": _steps(
            "import csv\n"
            "rows = list(csv.DictReader(open('sales_raw.csv', encoding='utf-8')))\n"
            "out = []\n"
            "for r in rows:\n"
            "    if int(r['qty']) <= 0:\n"
            "        continue\n"  # ← 坏剧本：忘记精确去重
            "    d = r['date']\n"
            "    if '/' in d:\n"
            "        y, m, day = d.split('/')\n"
            "        r['date'] = f'{y}-{int(m):02d}-{int(day):02d}'\n"
            "    out.append(r)\n"
            "with open('clean.csv', 'w', newline='', encoding='utf-8') as f:\n"
            "    w = csv.DictWriter(f, fieldnames=rows[0].keys())\n"
            "    w.writeheader()\n"
            "    w.writerows(out)\n"
            "print('rows:', len(out))\n"),
    },

    # ---------------- 任务2：区域净销售额聚合 ----------------
    # 数据里 orders.amount 含退款(负数)，指令要求统计"净销售额"= 剔除退款
    # bad 版：SUM 忘了剔除负数 → result.json 金额错误 → 检查器判负
    "region_sql": {
        "good": _steps(
            "import sqlite3, json\n"
            "con = sqlite3.connect('shop.db')\n"
            "rows = con.execute(\n"
            "    \"SELECT r.name, SUM(o.amount) FROM orders o \"\n"
            "    \"JOIN regions r ON o.region_id = r.id \"\n"
            "    \"WHERE o.amount > 0 \"\n"
            "    \"GROUP BY r.name ORDER BY r.name\").fetchall()\n"
            "json.dump({'results': {k: round(v, 2) for k, v in rows}},\n"
            "          open('result.json', 'w'))\n"
            "print('done')\n"),
        "bad": _steps(
            "import sqlite3, json\n"
            "con = sqlite3.connect('shop.db')\n"
            "rows = con.execute(\n"
            "    \"SELECT r.name, SUM(o.amount) FROM orders o \"\n"
            "    \"JOIN regions r ON o.region_id = r.id \"\n"
            "    \"GROUP BY r.name ORDER BY r.name\").fetchall()\n"  # ← 忘了剔除退款
            "json.dump({'results': {k: round(v, 2) for k, v in rows}},\n"
            "          open('result.json', 'w'))\n"
            "print('done')\n"),
    },

    # ---------------- 任务4：真实出租车运营数据清洗 ----------------
    # 底表是 NYC 出租车 2019-03 真实公开数据（6433 行）+ 受控注入 40 条重复
    # 规则：剔除 passengers==0 或 distance<=0；剔除 pickup_zone 缺失；精确去重
    # bad 版：漏掉"剔除 pickup_zone 缺失"规则 → 多 26 行 → 检查器判负
    "taxi_clean": {
        "good": _steps(
            "import csv\n"
            "rows = list(csv.DictReader(open('trips_raw.csv', encoding='utf-8')))\n"
            "out, seen = [], set()\n"
            "for r in rows:\n"
            "    if int(r['passengers']) == 0 or float(r['distance']) <= 0:\n"
            "        continue\n"
            "    if not r['pickup_zone'].strip():\n"
            "        continue\n"
            "    key = tuple(sorted(r.items()))\n"
            "    if key in seen:\n"
            "        continue\n"
            "    seen.add(key)\n"
            "    out.append(r)\n"
            "with open('trips_clean.csv', 'w', newline='', encoding='utf-8') as f:\n"
            "    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))\n"
            "    w.writeheader()\n"
            "    w.writerows(out)\n"
            "print('rows:', len(out))\n"),
        "bad": _steps(
            "import csv\n"
            "rows = list(csv.DictReader(open('trips_raw.csv', encoding='utf-8')))\n"
            "out, seen = [], set()\n"
            "for r in rows:\n"
            "    if int(r['passengers']) == 0 or float(r['distance']) <= 0:\n"
            "        continue\n"  # ← 坏剧本：漏掉 pickup_zone 缺失规则
            "    key = tuple(sorted(r.items()))\n"
            "    if key in seen:\n"
            "        continue\n"
            "    seen.add(key)\n"
            "    out.append(r)\n"
            "with open('trips_clean.csv', 'w', newline='', encoding='utf-8') as f:\n"
            "    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))\n"
            "    w.writeheader()\n"
            "    w.writerows(out)\n"
            "print('rows:', len(out))\n"),
    },

    # ---------------- 任务3：周报生成 ----------------
    # bad 版：算总销售额忘了剔除无效订单(qty<=0) → 报告数字错误 → 判负
    "weekly_report": {
        "good": _steps(
            "import csv\n"
            "rows = list(csv.DictReader(open('sales_raw.csv', encoding='utf-8')))\n"
            "valid = [r for r in rows if int(r['qty']) > 0]\n"
            "total = sum(int(r['qty']) * float(r['price']) for r in valid)\n"
            "cnt = {}\n"
            "for r in valid:\n"
            "    cnt[r['product']] = cnt.get(r['product'], 0) + int(r['qty'])\n"
            "top = max(cnt, key=cnt.get)\n"
            "md = (f'# \\u5468\\u62a5\\n\\n- \\u603b\\u9500\\u552e\\u989d: "
            "{round(total, 2)} \\u5143\\n'\n"
            "      f'- \\u9500\\u91cf\\u6700\\u9ad8\\u4ea7\\u54c1: {top}\\n'\n"
            "      f'- \\u6709\\u6548\\u8ba2\\u5355\\u6570: {len(valid)}\\n')\n"
            "open('report.md', 'w', encoding='utf-8').write(md)\n"
            "print(md)\n"),
        "bad": _steps(
            "import csv\n"
            "rows = list(csv.DictReader(open('sales_raw.csv', encoding='utf-8')))\n"
            "total = sum(int(r['qty']) * float(r['price']) for r in rows)\n"  # ← 没剔除无效订单
            "cnt = {}\n"
            "for r in rows:\n"
            "    cnt[r['product']] = cnt.get(r['product'], 0) + int(r['qty'])\n"
            "top = max(cnt, key=cnt.get)\n"
            "md = (f'# \\u5468\\u62a5\\n\\n- \\u603b\\u9500\\u552e\\u989d: "
            "{round(total, 2)} \\u5143\\n'\n"
            "      f'- \\u9500\\u91cf\\u6700\\u9ad8\\u4ea7\\u54c1: {top}\\n'\n"
            "      f'- \\u6709\\u6548\\u8ba2\\u5355\\u6570: {len(rows)}\\n')\n"
            "open('report.md', 'w', encoding='utf-8').write(md)\n"
            "print(md)\n"),
    },
}


class MockLLM:
    """脚本化模型。flaky=True 时先按 bad 剧本执行（模拟真实 LLM 常犯的错），
    收到 harness 的失败反馈后"反思"改用 good 剧本 —— 这正是 Reflect scaffold
    能提升 pass@1 的机理演示。"""

    def __init__(self, cfg: dict):
        self.name = cfg.get("name", "mock")
        self.task_id = cfg["task_id"]
        self.scaffold = cfg.get("scaffold", "react")
        self.flaky = cfg.get("flaky", False)
        self.total_tokens = 0
        self._turn = 0
        # flaky 模式：每次运行按确定性随机决定是否"犯病"（≈50% 概率用坏剧本），
        # run_seed 保证整个实验完全可复现 —— 这是 harness 的基本功
        import random
        self._use_bad = (self.flaky and
                         random.Random(cfg.get("run_seed", "x")).random() < 0.5)

    def chat(self, messages: list[dict]) -> str:
        last_user = next((m["content"] for m in reversed(messages)
                          if m["role"] == "user"), "")
        if "未通过" in last_user:
            self._use_bad = False  # 反思后切换到正确剧本
            self._turn = 0        # 重新执行

        entry = _SCRIPTS[self.task_id]
        seq = [PLAN_TURN] if self.scaffold == "plan_execute" else []
        seq += entry["bad" if self._use_bad else "good"]

        action = seq[self._turn] if self._turn < len(seq) else \
            {"think": "结束", "tool": "finish", "args": {}}
        self._turn += 1

        text = json.dumps(action, ensure_ascii=False)
        self.total_tokens += len(text) // 2  # Mock 的伪 token 计数
        return text
