import os
import sys

# 프로젝트 루트를 경로에 추가 (test 폴더 기준 상위 디렉토리 1단계)
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.backend.services.inventory_service.expiration_ai_service import expiration_ai_service

def run_tests():
    print("=== AI 소비기한 예측 테스트 3회 검토 ===")
    
    test_cases = [
        {"name": "시금치", "storage": "냉장", "expected_range": (3, 10)},
        {"name": "우유", "storage": "냉장", "expected_range": (5, 9)},
        {"name": "감자", "storage": "실온", "expected_range": (10, 20)},
        {"name": "돼지고기", "storage": "냉동", "expected_range": (30, 180)}
    ]
    
    for idx, tc in enumerate(test_cases, 1):
        print(f"\n[검토 {idx}] {tc['name']} ({tc['storage']} 보관)")
        try:
            # AI 서비스 예측 호출
            result = expiration_ai_service.predict_expiration_days(tc['name'], tc['storage'])
            print(f"-> 결과: {result}일")
            
            # 예측 범위 내에 들어오는지 기본 점검
            if tc['expected_range'][0] <= result <= tc['expected_range'][1]:
                print("-> 상태: 정상 (예상 범위 내)")
            else:
                print(f"-> 상태: 주의 (예상 범위 {tc['expected_range']}를 벗어남)")
                
        except Exception as e:
            print(f"-> 상태: 에러 발생 ({str(e)})")

if __name__ == "__main__":
    # 환경변수 OPENAI_API_KEY가 있는지 확인
    if not os.getenv("OPENAI_API_KEY"):
        print("경고: OPENAI_API_KEY가 환경변수로 설정되어 있지 않습니다.")
        print("현재 코드에서는 Fallback으로 기본 7일이 반환되어야 정상입니다.")
        
    run_tests()
