-- 동일 이메일의 소셜 계정을 독립적으로 저장하고 제공자 계정 식별자는 중복되지 않게 합니다.
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_email_key;
DROP INDEX IF EXISTS ix_users_email;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conname = 'uq_users_provider_id'
          AND conrelid = 'users'::regclass
    ) THEN
        ALTER TABLE users
            ADD CONSTRAINT uq_users_provider_id UNIQUE (auth_provider, provider_user_id);
    END IF;
END
$$;