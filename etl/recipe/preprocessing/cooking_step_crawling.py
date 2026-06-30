import pathlib
import sys
import pandas as pd
import random
import time
import json
from tqdm import tqdm

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent.parent
if __package__ is None:
    sys.path.insert(0, str(ROOT))

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from bs4 import BeautifulSoup

# 크롤링 상수 
CRAWL_INTERVAL_SEC = 0.5          # 주석 0.03은 너무 짧음 → 0.3~1.0 권장
CRAWL_INTERVAL_JITTER_SEC = 0.2   # ± 랜덤
REQUEST_TIMEOUT = (5, 15)           # (connect, read) 초
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ko-KR,ko;q=0.9,en-US;q=0.8,en;q=0.8",
    "Referer": "https://www.10000recipe.com/",
}


# 작업 사항 정리 
# 0. 읽어올 파일과 저장할 파일들의 경로 지정하고 파일 위치들을 확보한다. 
# 1. 전처리가 끝난 레시피 데이터를 기준으로 레시피 아이디를 얻어 온다. 
# 2. 조리법 데이터에 레시피 ID를 갱신하는데 이미 있는 경우는 스킵한다. 
# 3. 조리법 데이터의 아이디를 지정 주소에 대입해서 크롤링할 페이지 주소를 만든다. 
# 4. 0.03초 간격으로 읽어온 (네트워크 공격 기준에 걸리지 않을 시간 기준으로) 페이지에서 요리법 데이터만 가져와 컬럼에 저장한다. (전처리 빼고 그냥 저장)

## 크롤링 이후 읽어온 데이터의 처리는 다른 파일에서 진행한다. 
## 해당 파일에서는 요리법 데이터만 빠짐없이 읽어 오는 것으로만 진행한다. 
## 만약 읽어오지 못하거나 이미 내용이 채워져 있는 경우는 pass


# 각각의 동작을 실행할 서브 함수들을 만든
# 메인 함수에 각각을 연결해서 순서대로 실행


########################### 파일 로드 및 셋업 관련 함수 ################################
def load_csv_data(file_path: pathlib.Path | str) -> pd.DataFrame:
    """csv 파일을 로드해서 데이터 프레임으로 반환""" 
    df = pd.read_csv(file_path)
    print("--------------------------------")
    print(f"csv 데이터 로드 완료: {file_path}")
    print(f"csv 데이터 행 수: {len(df)}")
    return df

def save_csv_data(df: pd.DataFrame, file_path: pathlib.Path | str) -> None:
    """데이터 프레임을 csv로 변환해 지정 경로에 저장"""
    path = pathlib.Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print("--------------------------------")
    print(f"레시피 데이터 저장 완료: {file_path}")


def add_cooking_step(df_recipe: pd.DataFrame, df_cooking_step: pd.DataFrame) -> pd.DataFrame:
    """recipe에는 있지만 cooking_step에는 없는 RCP_SNO를 cooking_step에 추가"""
    existing_ids = set(df_cooking_step["RCP_SNO"])
    missing = df_recipe.loc[~df_recipe["RCP_SNO"].isin(existing_ids), ["RCP_SNO"]]

    if missing.empty:
        print("추가할 RCP_SNO 없음")
        return df_cooking_step

    print(f"추가할 RCP_SNO: {len(missing)}건")
    return pd.concat([df_cooking_step, missing], ignore_index=True)

############################ 레시피 id 로 주소 만들어 변환 ####################################

# 레시피 ID를 가지고 데이터로 반환 
def _create_recipe_url(recipe_id: int) -> str:
    """레시피 아이디를 받아서 레시피 주소를 생성해서 반환"""
    return f"https://www.10000recipe.com/recipe/{recipe_id}"

# 반환된 주소를 컬럼에 저장 
def make_recipe_url(df_cooking_step: pd.DataFrame) -> pd.DataFrame:
    """원본 데이터에서 id 기준으로 URL을 생성해서 컬럼에 저장 """ 
    df_cooking_step["RECIPE_URL"] = df_cooking_step["RCP_SNO"].apply(_create_recipe_url)

    return df_cooking_step

######################### 크롤링 시 사용할 세션 설정 함수 #########################
def _build_session() -> requests.Session:
    """ 세션, 헤더, 재시도 설정 세팅해서 세션으로 묶음"""
    session = requests.Session()
    session.headers.update(DEFAULT_HEADERS)
    retry = Retry(
        total=3,
        backoff_factor=1.0,          # 1s, 2s, 4s ...
        status_forcelist=(429, 500, 502, 503, 504),
        allowed_methods=["GET"],
        respect_retry_after_header=True,
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    return session


######################### URL 주소로 크롤링 진행 #########################

# 레시피 주소로 크롤링 
def _get_recipe_page(recipe_url: str, session: requests.Session) -> BeautifulSoup | None:
    """레시피 주소를 받아서 레시피 페이지를 크롤링해서 반환"""
    try:
        response = session.get(recipe_url, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        response.encoding = response.apparent_encoding or "utf-8"
        return BeautifulSoup(response.text, "html.parser")
    except requests.RequestException as e:
        print(f"크롤링 실패: {recipe_url} ({e})")
        return None
    finally:
        delay = CRAWL_INTERVAL_SEC + random.uniform(0, CRAWL_INTERVAL_JITTER_SEC)
        time.sleep(delay)


# 크롤링 한 HTML 문서를 데이터로 추출 
def _get_recipe_data(recipe_page: BeautifulSoup) -> dict | None:
    """레시피 페이지를 받아서 레시피 데이터를 추출해서 반환"""
    recipe_data = {}
    # 레시피 메인 이미지 
    # <img id="main_thumbs" src="..." alt="main thumb">
    main_thumbs = recipe_page.find("img", id="main_thumbs")
    if main_thumbs and main_thumbs.get("src"):
        recipe_data["recipe_main_thumbs"] = main_thumbs["src"]

    # 레시피 스탭
    # <div id="stepdescr1" class="media-body">...</div>
    for i in range(1, 100):
        stepdescr = recipe_page.find("div", id=f"stepdescr{i}")
        if stepdescr:
            recipe_data[f"recipe_step_{i}"] = {"step": i, "description": stepdescr.text.strip()}
        else:
            break

    # 레시피 스탭 이미지
    # <div id="stepimg1" class="media-right"><img src="..."></div>
    for i in range(1, 100):
        stepimg = recipe_page.find("div", id=f"stepimg{i}")
        if not stepimg:
            break
        img = stepimg.find("img")
        if img and img.get("src"):
            recipe_data[f"recipe_step_img_{i}"] = {"step": i, "image": img["src"]}

    if not any(key.startswith("recipe_step_") for key in recipe_data):
        return None

    return recipe_data


def crawling_recipe(df_cooking_step: pd.DataFrame) -> pd.DataFrame:
    """레시피 URL 주소로 크롤링 해서 데이터를 추출해서 반환"""
    if "RECIPE_DATA" not in df_cooking_step.columns:
        df_cooking_step["RECIPE_DATA"] = pd.NA

    session = _build_session()
    for index, row in tqdm(df_cooking_step.iterrows(), total=len(df_cooking_step), desc="크롤링 진행"):
        if pd.notna(df_cooking_step.at[index, "RECIPE_DATA"]):
            continue

        recipe_page = _get_recipe_page(row["RECIPE_URL"], session)
        if not recipe_page:
            continue

        try:
            recipe_data = _get_recipe_data(recipe_page)
        except (AttributeError, KeyError, TypeError) as e:
            print(f"데이터 추출 실패: {row['RECIPE_URL']} ({e})")
            continue

        if recipe_data:
            df_cooking_step.at[index, "RECIPE_DATA"] = json.dumps(
                recipe_data, ensure_ascii=False
            )

    return df_cooking_step





########################### 실행 함수 ############################
def main():
    ######################################################
    # 파일 경로 지정 
    recipe_file_path            = ROOT / "storage" / "processed" / "recipe" / "recipe_fix.csv"
    cooking_step_file_path      = ROOT / "storage" / "raw" / "recipe" / "cooking_steps.csv"
    
    # 파일 로드 
    df_recipe = load_csv_data(recipe_file_path)
    df_cooking_step = load_csv_data(cooking_step_file_path)
    print(df_recipe.head(1))
    print(df_cooking_step.head(1))

    # 데이터 로드 후 비어 있는 id를 채움 
    df_cooking_step = add_cooking_step(df_recipe, df_cooking_step)
    ######################################################

    # id 기준으로 레시피 URL을 만들어 컬럼에 지정 
    df_cooking_step = make_recipe_url(df_cooking_step)

    # 레시피 URL 주소로 크롤링 해서 데이터를 추출해서 반환
    df_cooking_step = crawling_recipe(df_cooking_step)


    ######################################################
    # 처리 완료된 데이터 저장 
    ######################################################
    save_csv_data(df_cooking_step, cooking_step_file_path)


if __name__ == "__main__":
    main()