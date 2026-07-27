# Bobbeori AWS CDK

This stack deploys the production React frontend on CloudFront with a private
S3 origin, the API and MCP resource server on ECS Fargate, a private RDS
PostgreSQL database, private Neo4j on EC2, private S3 receipt storage, Cognito
OAuth clients for ChatGPT and Codex, an HTTPS ALB, and the 07:00 Asia/Seoul
calendar synchronization task through EventBridge Scheduler.

## Prerequisites

- An existing Route 53 public hosted zone.
- CDK bootstrap completed in the target account and region.
- A frontend production build in `app/frontend/dist` if the deploy should also
  upload the React app to CloudFront's S3 origin.
- A Secrets Manager JSON secret (default: `bobbeori/<environment>/external`)
  with `OPENAI_API_KEY`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
  `KAKAO_CLIENT_ID`, `KAKAO_CLIENT_SECRET`, `KAKAO_REDIRECT_URI`,
  `NAVER_CLIENT_ID`, `NAVER_CLIENT_SECRET`, `NAVER_SHOPPING_CLIENT_ID`,
  `NAVER_SHOPPING_CLIENT_SECRET`, `LANGFUSE_PUBLIC_KEY`,
  `LANGFUSE_SECRET_KEY`, and `LANGFUSE_BASE_URL` keys.
- Exact predefined OAuth callback URLs copied from the ChatGPT and Codex setup
  screens. The clients are public PKCE clients and have no client secret.
- A Google OAuth web client that allows the Cognito callback URI printed as
  `CognitoGoogleRedirectUri`.

## Synthesize and deploy

Run from this directory. Replace all example values, especially callback URLs.

```powershell
py -m pip install -r requirements.txt
cd ../app/frontend
npm ci
$env:VITE_API_URL="https://api.bobbeori.com"
$env:VITE_KAKAO_CLIENT_ID="KAKAO_CLIENT_ID"
$env:VITE_NAVER_CLIENT_ID="NAVER_CLIENT_ID"
$env:VITE_GOOGLE_CLIENT_ID="GOOGLE_CLIENT_ID"
$env:VITE_GA_MEASUREMENT_ID="G-XXXXXXXXXX"
npm run build
cd ../../infra
npx aws-cdk bootstrap aws://ACCOUNT_ID/ap-northeast-2
npx aws-cdk synth `
  -c environment=prod `
  -c root_domain=bobbeori.com `
  -c hosted_zone_id=Z1234567890 `
  -c cognito_domain_prefix=bobbeori-mcp-prod-unique `
  -c chatgpt_callback_urls=https://CHATGPT_CALLBACK `
  -c codex_callback_urls=http://localhost:CODEX_CALLBACK_PORT/callback
npx aws-cdk deploy --require-approval broadening `
  -c environment=prod `
  -c root_domain=bobbeori.com `
  -c hosted_zone_id=Z1234567890 `
  -c cognito_domain_prefix=bobbeori-mcp-prod-unique `
  -c chatgpt_callback_urls=https://CHATGPT_CALLBACK `
  -c codex_callback_urls=http://localhost:CODEX_CALLBACK_PORT/callback
```

The Docker image is built from the repository by CDK and published as a CDK
asset. If `app/frontend/dist` exists, CDK also uploads it to the private
frontend bucket and invalidates CloudFront. By default, the frontend host is
`www.<root_domain>`; use `-c frontend_host=...` to override it. Use
`-c frontend_dist_path=...` to upload a different build directory. Production
uses two Fargate tasks, Multi-AZ RDS, and two NAT gateways; the `dev` context
uses one task, single-AZ RDS, and one NAT gateway.

## Public URLs

- Frontend: `https://www.<root_domain>` through CloudFront.
- API: `https://api.<root_domain>` through the public HTTPS ALB.
- MCP: `https://mcp.<root_domain>/mcp` through the public HTTPS ALB.

Register these frontend OAuth redirects in Google before production login:

- `https://www.<root_domain>/auth/callback/google`
- `https://www.<root_domain>/auth/callback/google-calendar`
- `https://<cognito_domain_prefix>.auth.ap-northeast-2.amazoncognito.com/oauth2/idpresponse`

The last redirect is required for Google login inside Cognito Hosted UI, which
is what ChatGPT and Codex use during MCP connection.

## Database bootstrap and migrations

The stack outputs `ClusterName`, `MigrationTaskDefinitionArn`,
`ApplicationSubnetIds`, and `ApplicationSecurityGroupId`. Run the migration
task once before directing traffic to a new release:

```powershell
aws ecs run-task --cluster CLUSTER --launch-type FARGATE `
  --task-definition MIGRATION_TASK_ARN `
  --network-configuration "awsvpcConfiguration={subnets=[SUBNET_A,SUBNET_B],securityGroups=[SECURITY_GROUP],assignPublicIp=DISABLED}"
```

The runner bootstraps `schema.sql` only for an empty database and records every
versioned migration in `schema_migrations`.

## Seed data import

Build and upload the initial seed bundle to the stack-managed seed bucket, then
run the one-off seed-import task. The task reads `manifest.json` from
`SeedDataPrefix`, imports PostgreSQL CSV/SQL files, and can also load the
food-guide split CSVs into Neo4j.

Build the bundle from the source data kept on the data branch/history:

```powershell
python scripts/build_seed_bundle.py --source-rev origin/dev --output seed-prod
```

Example S3 layout:

```text
s3://<SeedDataBucketName>/prod/manifest.json
s3://<SeedDataBucketName>/prod/postgres/recipes_seed.sql
s3://<SeedDataBucketName>/prod/postgres/food_nutrition_facts.csv
s3://<SeedDataBucketName>/prod/food_guide/nodes_ingredient.csv
s3://<SeedDataBucketName>/prod/food_guide/rel_ingredient_has_guide.csv
```

Example `manifest.json`:

```json
{
  "postgres_sql": [
    {"key": "postgres/recipes_seed.sql"}
  ],
  "postgres_csv": [
    {
      "table": "food_nutrition_facts",
      "key": "postgres/food_nutrition_facts.csv",
      "mode": "skip_if_not_empty"
    }
  ],
  "neo4j_food_guide": [
    {"prefix": "food_guide/"}
  ]
}
```

Upload it:

```powershell
$SeedBucket="<SeedDataBucketName>"
aws s3 sync .\seed-prod "s3://$SeedBucket/prod/" --delete --profile default
```

`postgres_csv` defaults to `mode: "skip_if_not_empty"` so reruns do not overwrite
live data. The recipe seed SQL is idempotent for recipe ids `1..175`.

## OAuth verification

Use Cognito's authorization-code flow with PKCE and include
`resource=https://mcp.bobbeori.com`. If the Cognito login uses Google and the
email is verified, the first MCP call auto-links the OAuth subject to the
Bobbeori account with the same email. Explicit linking through
`POST /api/v1/auth/mcp/link` is still supported. Then run:

```powershell
python ../scripts/test_mcp_oauth.py `
  --mcp-url https://mcp.bobbeori.com/mcp `
  --resource-url https://mcp.bobbeori.com `
  --access-token ACCESS_TOKEN
```

Cognito must receive the `resource` parameter so the access token contains the
MCP resource URL in its `aud` claim. The MCP server rejects tokens with a
different or missing audience.
