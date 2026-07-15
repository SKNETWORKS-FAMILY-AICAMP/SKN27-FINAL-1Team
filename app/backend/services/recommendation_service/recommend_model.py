"""LightFM 모델 로드 + 추론. pkl 파일이 없으면 fallback(전부 0.0)."""

from __future__ import annotations

import logging
import pickle
from pathlib import Path

_DIR = Path(__file__).resolve().parent
CATALOG_USER_ID = "__catalog__"

_cache: dict = {}
_log = logging.getLogger(__name__)


def _load():
    if "model" not in _cache:
        model_path = _DIR / "lightfm_model.pkl"
        if not model_path.exists():
            _log.warning("pkl 파일 없음 — 모델 점수 비활성 (%s)", _DIR)
            _cache["model"] = None
            return None, None, None
        try:
            with open(model_path, "rb") as f:
                _cache["model"] = pickle.load(f)
            with open(_DIR / "item_features.pkl", "rb") as f:
                _cache["item_features"] = pickle.load(f)
            with open(_DIR / "id_maps.pkl", "rb") as f:
                _cache["id_maps"] = pickle.load(f)
        except (ModuleNotFoundError, Exception) as e:
            # ponytail: lightfm 미설치(Windows 등) 시 fallback — Linux 배포 환경에서 정상 동작
            _log.warning("모델 로드 실패 — fallback 0.0 (%s)", e)
            _cache["model"] = None
            return None, None, None
    if _cache["model"] is None:
        return None, None, None
    return _cache["model"], _cache["item_features"], _cache["id_maps"]


def score_recipes(recipe_ids: list[int], user_id: str = CATALOG_USER_ID) -> dict[int, float]:
    """recipe_ids 각각에 대한 LightFM 점수를 반환한다."""
    if not recipe_ids:
        return {}

    model, item_features, id_maps = _load()
    if model is None:
        # ponytail: pkl 미배치 시 전부 0.0 — 배포 후 pkl 복사하면 자동 활성화
        return {rid: 0.0 for rid in recipe_ids}

    item_id_map: dict = id_maps["item_id_map"]
    user_id_map: dict = id_maps["user_id_map"]
    user_idx = user_id_map.get(user_id, user_id_map.get(CATALOG_USER_ID))
    if user_idx is None:
        return {rid: 0.0 for rid in recipe_ids}

    valid = [(rid, item_id_map[str(rid)]) for rid in recipe_ids if str(rid) in item_id_map]
    if not valid:
        return {rid: 0.0 for rid in recipe_ids}

    rids, indices = zip(*valid)

    import numpy as np  # ponytail: lazy — pkl 없는 환경(CI 등)에서 모듈 로드 실패 방지
    item_arr = np.array(indices, dtype=np.int32)
    user_arr = np.full(len(item_arr), user_idx, dtype=np.int32)
    
    scores = model.predict(user_arr, item_arr, item_features=item_features, num_threads=1)

    result = dict(zip(rids, scores.astype(float)))
    for rid in recipe_ids:
        if rid not in result:
            result[rid] = 0.0
    return result
