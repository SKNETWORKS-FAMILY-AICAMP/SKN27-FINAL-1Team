"""LightFM smoke test: warp fit + precision_at_k / recall_at_k on Linux."""
from __future__ import annotations

import sys

import numpy as np
from scipy.sparse import csr_matrix

from lightfm import LightFM
from lightfm.evaluation import precision_at_k, recall_at_k


def main() -> int:
    rng = np.random.default_rng(42)
    n_users, n_items = 20, 30
    rows, cols = rng.integers(0, n_users, 80), rng.integers(0, n_items, 80)
    data = np.ones(80, dtype=np.float32)
    interactions = csr_matrix((data, (rows, cols)), shape=(n_users, n_items))

    model = LightFM(loss="warp", random_state=42)
    model.fit(interactions, epochs=2, num_threads=2)

    p5 = float(precision_at_k(model, interactions, k=5).mean())
    r5 = float(recall_at_k(model, interactions, k=5).mean())
    if not (0.0 <= p5 <= 1.0 and 0.0 <= r5 <= 1.0):
        print(f"unexpected metrics: precision@5={p5}, recall@5={r5}", file=sys.stderr)
        return 1

    print(f"lightfm ok: precision@5={p5:.4f}, recall@5={r5:.4f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
