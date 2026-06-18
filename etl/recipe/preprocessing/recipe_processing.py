import pathlib

import pandas as pd


########################### 함수 정의 ################################
def _load_recipe_data(file_path: pathlib.Path | str) -> pd.DataFrame:
    """레시피 csv 파일을 로드해서 데이터 프레임으로 반환""" 
    df = pd.read_csv(file_path)
    print("--------------------------------")
    print(f"레시피 데이터 로드 완료: {file_path}")
    print(f"레시피 데이터 행 수: {len(df)}")
    return df

def _save_recipe_data(df: pd.DataFrame, file_path: pathlib.Path | str) -> None:
    """데이터 프레임을 csv로 변환해 지정 경로에 저장"""
    path = pathlib.Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8")
    print("--------------------------------")
    print(f"레시피 데이터 저장 완료: {file_path}")
    
def _drop_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """데이터 프레임에서 불필요한 컬럼을 제거해서 반환"""
    df = df.drop(columns=cols)
    print("--------------------------------")
    print(f"레시피 데이터 컬럼 제거 완료: {cols}")
    return df

def _process_recipe_name(df: pd.DataFrame) -> pd.DataFrame:
    """레시피 이름 정규화 (앞뒤 공백 제거, 소문자로)"""
    df["recipe_name"] = df["recipe_name"].str.strip().str.lower()
    return df




########################### 실행 함수 ################################
def main():
    # 파일 경로 지정 
    root = pathlib.Path(__file__).resolve().parent.parent.parent.parent
    file_path       = root / "storage" / "raw" / "recipe" / "recipe.csv"
    new_file_path   = root / "storage" / "processed" / "recipe" / "recipe_fix.csv"
    
    # 파일 로드 
    df = _load_recipe_data(file_path)

    # 사용 안하는 컬럼 제거 
    cols = ["recipe_title", "recommend_count", "description", ]
    df_recipe = _drop_cols(df, cols)

    # 레시피 이름 정규화 
    df_recipe = _process_recipe_name(df_recipe)



    # 처리 완료된 데이터 저장 
    _save_recipe_data(df_recipe, new_file_path)

if __name__ == "__main__":
    main()