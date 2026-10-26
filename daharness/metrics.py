"""指标：与项目一共享的统计工具（bootstrap CI / 均值）。保持零依赖。"""

from __future__ import annotations

import random


def mean(xs):
    xs = list(xs)
    return sum(xs) / len(xs) if xs else 0.0


def bootstrap_ci(flags, n_boot: int = 1000, alpha: float = 0.05, seed: int = 0):
    """准确率的 Bootstrap 95% 置信区间 —— harness 报告里所有 pass@1 都带 CI。"""
    flags = list(flags)
    n = len(flags)
    if n == 0:
        return 0.0, 0.0, 0.0
    rng = random.Random(seed)
    stats = sorted(
        mean(flags[rng.randrange(n)] for _ in range(n)) for _ in range(n_boot))
    lo = stats[int((alpha / 2) * n_boot)]
    hi = stats[min(n_boot - 1, int((1 - alpha / 2) * n_boot))]
    return mean(flags), lo, hi
