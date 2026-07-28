import os
import subprocess
import sys


def test_settings_accept_local_receipt_s3_environment_names():
    env = os.environ.copy()
    env.update(
        {
            "RECEIPT_STORAGE_BACKEND": "s3",
            "RECEIPT_S3_BUCKET": "local-private-receipts",
            "RECEIPT_S3_PREFIX": "local-receipts",
            "RECEIPT_S3_TEMP_PREFIX": "temporary",
            "S3_RECEIPT_BUCKET": "legacy-private-receipts",
            "S3_RECEIPT_PREFIX": "legacy-receipts",
        }
    )
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "from app.backend.core.config import settings; "
                "print('|'.join([settings.RECEIPT_STORAGE_BACKEND, "
                "settings.S3_RECEIPT_BUCKET, settings.S3_RECEIPT_PREFIX, "
                "settings.S3_RECEIPT_TEMP_PREFIX]))"
            ),
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.stdout.strip() == "s3|local-private-receipts|local-receipts|temporary"


def test_database_migrations_default_to_local_development_only():
    env = os.environ.copy()
    env.pop("AUTO_RUN_DB_MIGRATIONS", None)
    env["DEV_MODE"] = "false"
    production = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.backend.core.config import settings; print(settings.AUTO_RUN_DB_MIGRATIONS)",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    env["DEV_MODE"] = "true"
    development = subprocess.run(
        [
            sys.executable,
            "-c",
            "from app.backend.core.config import settings; print(settings.AUTO_RUN_DB_MIGRATIONS)",
        ],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert production.stdout.strip() == "False"
    assert development.stdout.strip() == "True"
