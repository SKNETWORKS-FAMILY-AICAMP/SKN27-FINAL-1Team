import pathlib

import pandas as pd


########################### 함수 정의 ################################
def load_recipe_data(file_path: pathlib.Path | str) -> pd.DataFrame:
    """레시피 csv 파일을 로드해서 데이터 프레임으로 반환""" 
    df = pd.read_csv(file_path)
    print("--------------------------------")
    print(f"레시피 데이터 로드 완료: {file_path}")
    print(f"레시피 데이터 행 수: {len(df)}")
    return df

def save_recipe_data(df: pd.DataFrame, file_path: pathlib.Path | str) -> None:
    """데이터 프레임을 csv로 변환해 지정 경로에 저장"""
    path = pathlib.Path(file_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, encoding="utf-8-sig")
    print("--------------------------------")
    print(f"레시피 데이터 저장 완료: {file_path}")
    
def drop_cols(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    """데이터 프레임에서 불필요한 컬럼을 제거해서 반환"""
    df = df.drop(columns=cols)
    print("--------------------------------")
    print(f"레시피 데이터 컬럼 제거 완료: {cols}")
    return df

def process_recipe_name(df: pd.DataFrame) -> pd.DataFrame:
    """레시피 이름 정규화 (앞뒤 공백 제거, 소문자로)"""
    df["CKG_NM"] = df["CKG_NM"].str.strip().str.lower()
    return df

def sort_by_view_count(df: pd.DataFrame) -> pd.DataFrame:
    """조회수 내림차순으로 정렬"""
    df = df.sort_values(by="INQ_CNT", ascending=False)
    return df

def rm_duplicate_recipe_name(df: pd.DataFrame) -> pd.DataFrame:
    """
    레시피 이름 중복 제거
    현재는 따로 기준이 없는 상태라 조회수 가장 많은 레시피 1개만 남기고 있음
    나중에는 특정 기준 하에 n개 정도를 남기는 방향 검토할 예정
    """
    df = df.drop_duplicates(subset=["CKG_NM"], keep="first") 
    print("--------------------------------")
    print(f"레시피 이름 중복 제거 완료: {len(df)}")
    return df

def process_ingredient(df: pd.DataFrame) -> pd.DataFrame:
    """재료 정규화 
    1. 소문자로 변경
    2. [재료] 표시 부분 제거 
    3. 분량 구분자(\x07) _ 로 변경 
    3. 공백제거
    4. | 부분 기준으로 split 해서 리스트로 반환
    """
    # 소문자화 
    df["CKG_MTRL_CN"] = df["CKG_MTRL_CN"].str.lower()
    # [재료] 표시 부분 제거 
    df["CKG_MTRL_CN"] = df["CKG_MTRL_CN"].str.replace(r"\[[^\]]*\]\s*", "", regex=True)
    # 분량 구분자 _ 로 변경 
    df["CKG_MTRL_CN"] = df["CKG_MTRL_CN"].str.replace(r"\x07\s*", "_", regex=True)
    # 공백제거
    df["CKG_MTRL_CN"] = df["CKG_MTRL_CN"].str.strip()
    # | 부분 기준으로 split 해서 리스트로 반환
    df["CKG_MTRL_CN"] = df["CKG_MTRL_CN"].str.split("|")

    print("--------------------------------")
    print(f"재료 정규화 완료: {len(df)}")
    print(f"재료 샘플: {df['CKG_MTRL_CN'].head()}")

    return df

def process_individual_ingredient(df: pd.DataFrame) -> pd.DataFrame:
    """
    개별 재료 데이터 정규화
    df["CKG_MTRL_CN"] 컬럼의 리스트의 요소 각각을 str에서 list로 변경해서 처리해야 함 
    재료 각각은 _ 기준으로 연결되어 있음 
    "재료_개수_단위_나머지"로 연결되어 있으니 이 기준으로 split 해서 리스트로 반환
    개별 재료에서 이름, 개수, 단위 까지만 사용하고 나머지는 버림 
    """
    df["CKG_MTRL_CN"] = df["CKG_MTRL_CN"].apply(lambda x: [item.split("_")[:3] for item in x])
    print("--------------------------------")
    print(f"개별 재료 데이터 정규화 완료: {len(df)}")
    print(f"개별 재료 샘플: {df['CKG_MTRL_CN'].head()}")
    return df

def add_col_view_rate(df: pd.DataFrame) -> pd.DataFrame:
    """최고 조회수 대비 상대 비율값"""
    df["INQ_CNT_RATE"] = df["INQ_CNT"] / df["INQ_CNT"].max()
    return df

def rm_low_view_rate_recipe(df: pd.DataFrame) -> pd.DataFrame:
    """조회수 비율 1.5% 미만 데이터 제거"""
    df = df[df["INQ_CNT_RATE"] > 0.015]
    print("--------------------------------")
    print(f"조회수 비율 기준 미만 데이터 제거 완료: {len(df)}")
    return df

def fill_nan_values(df: pd.DataFrame) -> pd.DataFrame:
    """
    컬럼 별 결측치 처리
    CKG_MTH_ACTO_NM(조리법)에서 결측치 발생 1껀 -> "기타"로 통합
    CKG_STA_ACTO_NM(상황) 결측치 55껀 -> "기타"로 통합
    CKG_INBUN_NM(요리 분량) 확인 -> 데이터 보고 결정 필요 (당장은 "확인필요"로 처리 약 707껀)
    CKG_TIME_NM(조리시간) -> "확인필요" 추가해야 할 듯
    """
    df["CKG_MTH_ACTO_NM"] = df["CKG_MTH_ACTO_NM"].fillna("기타")
    df["CKG_STA_ACTO_NM"] = df["CKG_STA_ACTO_NM"].fillna("기타")
    df["CKG_INBUN_NM"] = df["CKG_INBUN_NM"].fillna("확인필요")
    df["CKG_TIME_NM"] = df["CKG_TIME_NM"].fillna("확인필요")
    return df



########################### 실행 함수 ################################
def main():
    ######################################################
    # 파일 경로 지정 
    root = pathlib.Path(__file__).resolve().parent.parent.parent.parent
    file_path       = root / "storage" / "raw" / "recipe" / "recipe.csv"
    new_file_path   = root / "storage" / "processed" / "recipe" / "recipe_fix.csv"
    
    # 파일 로드 
    df = load_recipe_data(file_path)
    ######################################################


    # 사용 안하는 컬럼 제거 
    cols = ["RCP_TTL", "RGTR_ID", "RGTR_NM", "RCMM_CNT", "CKG_IPDC", "FIRST_REG_DT"]
    df_recipe = drop_cols(df, cols)

    # 레시피 이름 정규화 
    df_recipe = process_recipe_name(df_recipe)

    # 조회수 내림차순으로 정렬
    df_recipe = sort_by_view_count(df_recipe)

    # 조회수 기준 상대 비율 값 추가 
    df_recipe = add_col_view_rate(df_recipe)

    # 조회수 비율 기준 미만 데이터 제거
    df_recipe = rm_low_view_rate_recipe(df_recipe)

    # 레시피 이름 중복 제거
    df_recipe = rm_duplicate_recipe_name(df_recipe)

    # 재료 정규화 
    df_recipe = process_ingredient(df_recipe)

    # 개별 재료 데이터 정규화 
    df_recipe = process_individual_ingredient(df_recipe)

    # 결측치 처리
    df_recipe = fill_nan_values(df_recipe)



    ######################################################
    # 처리 완료된 데이터 저장 
    ######################################################
    save_recipe_data(df_recipe, new_file_path)

if __name__ == "__main__":
    main()