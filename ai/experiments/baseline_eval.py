"""Fixed item-score baselines aligned with LightFM precision@k / recall@k."""

from __future__ import annotations

import numpy as np
from scipy.sparse import spmatrix


def train_popularity_scores(train: spmatrix) -> np.ndarray:
    return np.asarray(train.sum(axis=0)).ravel().astype(np.float64)


def random_scores(n_items: int, rng: np.random.Generator) -> np.ndarray:
    return rng.random(n_items, dtype=np.float64)


def _user_test_items(test: spmatrix) -> dict[int, set[int]]:
    coo = test.tocoo()
    users: dict[int, set[int]] = {}
    for u, i in zip(coo.row, coo.col):
        users.setdefault(int(u), set()).add(int(i))
    return users


def precision_recall_at_k(
    test: spmatrix, item_scores: np.ndarray, k: int
) -> tuple[float, float]:
    scores = np.asarray(item_scores, dtype=np.float64).ravel()
    n_items = test.shape[1]
    if scores.shape[0] != n_items:
        raise ValueError(f"item_scores length {scores.shape[0]} != n_items {n_items}")

    top_k = np.argsort(-scores, kind="stable")[:k]
    top_k_set = set(top_k.tolist())

    user_items = _user_test_items(test)
    if not user_items:
        return 0.0, 0.0

    precisions: list[float] = []
    recalls: list[float] = []
    for relevant in user_items.values():
        hits = len(relevant & top_k_set)
        precisions.append(hits / k)
        recalls.append(hits / len(relevant))

    return float(np.mean(precisions)), float(np.mean(recalls))


def evaluate_baseline(test: spmatrix, item_scores: np.ndarray) -> dict[str, float]:
    p5, r5 = precision_recall_at_k(test, item_scores, 5)
    p10, r10 = precision_recall_at_k(test, item_scores, 10)
    return {
        "precision@5": p5,
        "precision@10": p10,
        "recall@5": r5,
        "recall@10": r10,
    }


if __name__ == "__main__":
    from scipy.sparse import csr_matrix

    rng = np.random.default_rng(0)
    n_users, n_items = 4, 6
    rows = np.array([0, 0, 1, 2, 3])
    cols = np.array([1, 3, 2, 4, 0])
    data = np.ones(len(rows))
    train = csr_matrix((data, (rows, cols)), shape=(n_users, n_items))
    test = csr_matrix(([1.0], ([1], [2])), shape=(n_users, n_items))

    pop = train_popularity_scores(train)
    metrics = evaluate_baseline(test, pop)
    assert 0.0 <= metrics["precision@5"] <= 1.0
    assert 0.0 <= evaluate_baseline(test, random_scores(n_items, rng))["precision@5"] <= 1.0
    print("baseline_eval ok")
