import os, time
from .upload import load_csv, upload

CSV_PATH = r"c:/dev/project/SKN27-FINAL-1Team/storage/processed/food_guide/food_guide_v1.csv"
CHECK_INTERVAL = 60  # seconds

def main():
    last_mtime = None
    while True:
        try:
            mtime = os.path.getmtime(CSV_PATH)
            if last_mtime is None or mtime > last_mtime:
                print(f"[cron_loader] 파일 변경 감지 (mtime={mtime}), Neo4j 적재 시작")
                df = load_csv(CSV_PATH)
                upload(df)
                last_mtime = mtime
            else:
                print("[cron_loader] 변경 없음")
        except Exception as e:
            print(f"[cron_loader] 오류: {e}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
