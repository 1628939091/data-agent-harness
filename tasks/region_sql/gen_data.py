"""任务2数据生成：门店销售 SQLite 库（含退款负数记录）。"""

import os
import random
import sqlite3


def generate(data_dir: str) -> None:
    rng = random.Random(2027)
    db = os.path.join(data_dir, "shop.db")
    if os.path.exists(db):
        os.remove(db)
    con = sqlite3.connect(db)
    con.executescript(
        "CREATE TABLE regions (id INTEGER PRIMARY KEY, name TEXT);\n"
        "CREATE TABLE orders  (id INTEGER PRIMARY KEY, region_id INTEGER,"
        " amount REAL);\n")
    regions = ["华东", "华南", "华北", "西南", "东北"]
    con.executemany("INSERT INTO regions VALUES (?,?)",
                    [(i + 1, n) for i, n in enumerate(regions)])
    orders = []
    for i in range(1200):
        amount = round(rng.uniform(50, 5000), 2)
        if rng.random() < 0.12:          # 12% 是退款（负数）
            amount = -round(rng.uniform(50, 800), 2)
        orders.append((i + 1, rng.randint(1, 5), amount))
    con.executemany("INSERT INTO orders VALUES (?,?,?)", orders)
    con.commit()
    con.close()
