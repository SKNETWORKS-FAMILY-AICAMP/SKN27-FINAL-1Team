# Bobbeori CI/CD

## Branch flow

- `feature_deploy`: CI only.
- `main`: production CD.

## GitHub variables

Set these in repository or environment variables:

- `AWS_REGION`: `ap-northeast-2`
- `AWS_ROLE_ARN`: GitHub OIDC deploy role ARN
- `ROOT_DOMAIN`: `bobbeori.com`
- `FRONTEND_HOST`: `www.bobbeori.com`
- `HOSTED_ZONE_ID`: Route 53 hosted zone id
- `COGNITO_DOMAIN_PREFIX`: Cognito hosted UI prefix
- `CHATGPT_CALLBACK_URLS`: comma-separated ChatGPT OAuth callbacks
- `CODEX_CALLBACK_URLS`: comma-separated Codex OAuth callbacks
- `EXTERNAL_SECRET_NAME`: `bobbeori/prod/external`

## GitHub secrets

- `OPENAI_APPS_CHALLENGE_TOKEN`: optional domain verification token

## Workflows

- `feature_deploy CI`: frontend production build and CDK synth.
- `pytest`: backend tests.
- `deploy production`: runs automatically on `main` push and smoke-tests the public URLs.
- `migrate production`: manual ECS one-off migration task.
