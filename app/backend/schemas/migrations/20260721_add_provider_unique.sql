-- 이메일 중복이 허용되면서 발생할 수 있는 동일 소셜 계정의 다중 가입(Race condition)을 방지하기 위해, 소셜 제공자와 소셜 ID의 조합을 고유하게(Unique) 설정합니다.
ALTER TABLE users ADD CONSTRAINT uq_users_provider_id UNIQUE (auth_provider, provider_user_id);
