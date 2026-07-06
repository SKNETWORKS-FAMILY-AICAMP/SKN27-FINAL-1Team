"""강의 auc_98.2/service/utils.py 패턴 — 재현성 시드 고정."""

from __future__ import annotations

import os
import random

import numpy as np
import torch

from .config import RANDOM_STATE


def reset_seeds(func, seed: int = RANDOM_STATE):
    random.seed(seed)
    os.environ["PYTHONHASHSEED"] = str(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.backends.cudnn.deterministic = True

    def wrapper_func(*args, **kwargs):
        return func(*args, **kwargs)

    return wrapper_func
