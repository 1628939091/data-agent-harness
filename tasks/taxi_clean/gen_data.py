"""任务4数据生成：真实出租车运营流水（真实分布 + 受控污染）。

与任务 1-3 的本质区别：底表不是合成的，是 NYC 出租车 2019-03 的真实公开
记录（seaborn taxis 数据集，6433 行）。真实数据自带天然脏：
  - passengers == 0   96 行（代驾 / 系统记录）
  - distance  <= 0    51 行（里程异常）
  - pickup_zone 缺失  26 行
唯一需要受控注入的是"精确重复行"（真实数据没有重复）——
注入 40 条模拟采集端重复上报，种子固定，保证可复现。

方法论：真实分布 + 受控污染（企业评测的标准做法，比纯合成更可信，
比纯真实更可控——每一条脏数据都有明确定义的金标准）。
"""

import csv
import os
import random

# 注意：gen_data 由 harness 用 exec 动态执行（无 __file__ 变量），
# 但调用方保证 data_dir = <任务目录>/data，底表在任务目录下
def _base_path(data_dir: str) -> str:
    return os.path.join(os.path.dirname(os.path.abspath(data_dir)), "taxis_base.csv")


def generate(data_dir: str) -> None:
    rng = random.Random(20260326)
    with open(_base_path(data_dir), encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    # 受控注入：40 条精确重复（模拟采集端重复上报）
    dup = rng.sample(rows, 40)
    rows_all = rows + dup
    rng.shuffle(rows_all)

    raw = os.path.join(data_dir, "trips_raw.csv")
    with open(raw, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_all[0].keys()))
        w.writeheader()
        w.writerows(rows_all)

    # 标准答案：与 task.json 指令逐条对应的参考实现
    # 规则顺序：先剔除无效行程与缺失区域，再精确去重（保留首次出现）
    out, seen = [], set()
    for r in rows_all:
        if int(r["passengers"]) == 0 or float(r["distance"]) <= 0:
            continue
        if not r["pickup_zone"].strip():
            continue
        key = tuple(sorted(r.items()))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    with open(os.path.join(data_dir, "expected_trips_clean.csv"), "w",
              newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(rows_all[0].keys()))
        w.writeheader()
        w.writerows(out)
