-- email 중복 가입을 허용하기 위해 기존에 걸려있던 Unique 제약 조건을 삭제합니다.
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_key;
DROP INDEX IF EXISTS ix_users_email;
