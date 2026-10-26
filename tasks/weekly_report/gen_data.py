"""任务3数据生成：门店周度流水（与任务1同源的另一批数据）。"""

import csv
import os
import random


def generate(data_dir: str) -> None:
    rng = random.Random(2028)
    products = ["电动牙刷", "电饭煲", "加湿器", "筋膜枪", "显示器"]
    rows = []
    for i in range(300):
        rows.append({
            "order_id": f"W{i:05d}",
            "date": f"2026-10-{rng.randint(1, 7):02d}",
            "product": rng.choice(products),
            "qty": rng.choice([1, 1, 2, 3, -1, 0]),
            "price": round(rng.uniform(79, 1999), 2),
        })
    with open(os.path.join(data_dir, "sales_raw.csv"), "w", newline="",
              encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
