# Bobbeori AWS CDK

This stack deploys the production API and MCP resource server on ECS Fargate, a
private RDS PostgreSQL database, private Neo4j on EC2, private S3 receipt
storage, Cognito OAuth clients for ChatGPT and Codex, an HTTPS ALB, and the
07:00 Asia/Seoul calendar synchronization task through EventBridge Scheduler.

## Prerequisites

- An existing Route 53 public hosted zone.
- CDK bootstrap completed in the target account and region.
- A Secrets Manager JSON secret (default: `bobbeori/<environment>/external`)
  with `OPENAI_API_KEY`, `GOOGLE_CLIENT_ID`, and `GOOGLE_CLIENT_SECRET` keys.
- Exact predefined OAuth callback URLs copied from the ChatGPT and Codex setup
  screens. The clients are public PKCE clients and have no client secret.

## Synthesize and deploy

Run from this directory. Replace all example values, especially callback URLs.

```powershell
py -m pip install -r requirements.txt
npx aws-cdk bootstrap aws://ACCOUNT_ID/ap-northeast-2
npx aws-cdk synth `
  -c environment=dev `
  -c root_domain=example.com `
  -c hosted_zone_id=Z1234567890 `
  -c cognito_domain_prefix=bobbeori-mcp-dev-unique `
  -c chatgpt_callback_urls=https://CHATGPT_CALLBACK `
  -c codex_callback_urls=http://localhost:CODEX_CALLBACK_PORT/callback
npx aws-cdk deploy --require-approval broadening `
  -c environment=dev `
  -c root_domain=example.com `
  -c hosted_zone_id=Z1234567890 `
  -c cognito_domain_prefix=bobbeori-mcp-dev-unique `
  -c chatgpt_callback_urls=https://CHATGPT_CALLBACK `
  -c codex_callback_urls=http://localhost:CODEX_CALLBACK_PORT/callback
```

The Docker image is built from the repository by CDK and published as a CDK
asset. Production uses two Fargate tasks, Multi-AZ RDS, and two NAT gateways;
the `dev` context uses one task, single-AZ RDS, and one NAT gateway.

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
