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
  with `OPENAI_API_KEY`, `GOOGLE_CLIENT_ID`, and `GOOGLE_CLIENT_SECRET` keys.
- Exact predefined OAuth callback URLs copied from the ChatGPT and Codex setup
  screens. The clients are public PKCE clients and have no client secret.

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

## OAuth verification

Use Cognito's authorization-code flow with PKCE and include
`resource=https://mcp.example.com/mcp`. After linking the Cognito identity to a
signed-in Bobbeori account through `POST /api/v1/auth/mcp/link`, run:

```powershell
python ../scripts/test_mcp_oauth.py `
  --mcp-url https://mcp.example.com/mcp `
  --access-token ACCESS_TOKEN
```

Cognito must receive the `resource` parameter so the access token contains the
MCP URL in its `aud` claim. The MCP server rejects tokens with a different or
missing audience.
