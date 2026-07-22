## 작업 요약

- 
- 

## 변경 범위

- [ ] Backend
- [ ] Frontend
- [ ] MCP
- [ ] Calendar
- [ ] DB Migration
- [ ] Infra / AWS CDK
- [ ] Env / Secrets Manager
- [ ] 기타:

## 수정 이유

문제가 무엇이었고, 왜 이 수정이 필요한지 간단히 작성합니다.

## 주요 변경 내용

- 
- 
- 

## 테스트 결과

실행한 테스트:

- 예: py -m pytest
- 예: npm run build

결과:

- 예: 12 passed
- 예: build success

## 운영 반영 필요 사항

- [ ] CDK deploy 필요
- [ ] ECS 서비스 재배포 필요
- [ ] DB migration 실행 필요
- [ ] Seed import 필요
- [ ] CloudFront invalidation 필요
- [ ] Secrets Manager 값 추가/수정 필요
- [ ] AWS 콘솔 수동 설정 필요
- [ ] 필요 없음

상세 내용:

- 예: migration 실행 필요
  - migrations/20260721_drop_email_unique.sql
  - migrations/20260721_add_provider_unique.sql

- 예: Secrets Manager 수정 필요
  - bobbeori/prod/external
  - LANGFUSE_PUBLIC_KEY
  - LANGFUSE_SECRET_KEY

## 배포 위험도

- [ ] 낮음: 단순 버그 수정
- [ ] 중간: API / DB / 인증 영향 있음
- [ ] 높음: 운영 데이터 / 인프라 영향 있음

주의할 점:

- 

## 롤백 방법

문제 발생 시 되돌리는 방법:

- 

## 체크리스트

- [ ] feature_deploy 최신 pull 후 브랜치 생성함
- [ ] 운영 배포와 관련된 코드만 포함함
- [ ] 불필요한 파일 / 로그 / 캐시 / 로컬 설정 파일 제외함
- [ ] 테스트 또는 수동 검증 완료함
- [ ] migration / env / AWS 변경사항을 본문에 명시함
- [ ] 리뷰어가 재현 / 확인할 수 있게 설명 작성함
