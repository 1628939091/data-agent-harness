"""任务1数据生成：企业销售流水（含脏数据），确定性可复现。

脏数据设计（模拟真实企业数据的常见问题）：
  - 退货/录入错误: qty <= 0
  - 重复提交: 完全相同的行出现两次
  - 日期格式混杂: YYYY-MM-DD 与 YYYY/M/D 并存
"""

import csv
import os
import random


def generate(data_dir: str) -> None:
    rng = random.Random(2026)
    products = ["净水器", "空气炸锅", "按摩仪", "扫地机器人", "蓝牙耳机"]
    rows = []
    for i in range(500):
        m = rng.randint(1, 9)
        d = rng.randint(1, 28)
        date = f"2026-{m:02d}-{d:02d}" if rng.random() < 0.6 else f"2026/{m}/{d}"
        rows.append({
            "order_id": f"SO{i:05d}",
            "date": date,
            "product": rng.choice(products),
            "qty": rng.choice([1, 1, 2, 3, 5, 0, -1, -2]),
            "price": round(rng.uniform(99, 2999), 2),
        })
    # 注入 30 条精确重复行
    dup = rng.sample(rows, 30)
    rows_all = rows + dup
    rng.shuffle(rows_all)

    raw = os.path.join(data_dir, "sales_raw.csv")
    with open(raw, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_all[0].keys()))
        w.writeheader()
        w.writerows(rows_all)

    # 标准答案：与任务指令中的清洗规则完全一致的规范化结果
    out, seen = [], set()
    for r in rows_all:
        if int(r["qty"]) <= 0:
            continue
        key = tuple(sorted(r.items()))
        if key in seen:
            continue
        seen.add(key)
        r2 = dict(r)
        if "/" in r2["date"]:
            y, m2, d2 = r2["date"].split("/")
            r2["date"] = f"{y}-{int(m2):02d}-{int(d2):02d}"
        out.append(r2)
    with open(os.path.join(data_dir, "expected_clean.csv"), "w",
              newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_all[0].keys()))
        w.writeheader()
        w.writerows(out)
