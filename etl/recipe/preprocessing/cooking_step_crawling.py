import pathlib
import pandas as pd
import requests
from bs4 import BeautifulSoup


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


########################### 함수 정의 ################################
def load_csv_data(file_path: pathlib.Path | str) -> pd.DataFrame:
    """csv 파일을 로드해서 데이터 프레임으로 반환""" 
    df = pd.read_csv(file_path)
    print("--------------------------------")
    print(f"csv 데이터 로드 완료: {file_path}")
    print(f"csv 데이터 행 수: {len(df)}")
    return df


















########################### 실행 함수 ############################
def main():
    ######################################################
    # 파일 경로 지정 
    root = pathlib.Path(__file__).resolve().parent.parent.parent.parent
    recipe_file_path            = root / "storage" / "processed" / "recipe" / "recipe_fix.csv"
    cooking_step_file_path      = root / "storage" / "raw" / "recipe" / "cooking_step.csv"
    
    # 파일 로드 
    df_recipe = load_csv_data(recipe_file_path)
    df_cooking_step = load_csv_data(cooking_step_file_path)
    ######################################################

if __name__ == "__main__":
    main()