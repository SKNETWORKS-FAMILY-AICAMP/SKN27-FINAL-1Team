# Bobbeori public MCP

This service is an authenticated MCP adapter over the existing Bobbeori domain services. It does not replace the FastAPI REST backend.

## Local run

```powershell
docker compose up -d --build mcp
```

The Streamable HTTP endpoint is `http://localhost:8001/mcp`. In local development, `MCP_DEV_TOKEN_AUTH=true` accepts an existing Bobbeori access token. Do not enable this mode in production.

## Tools and scopes

| Tool | Scope | Effect |
|---|---|---|
| `inventory.list` | `bobbeori-mcp/inventory.read` | Read active refrigerator items |
| `inventory.expiring` | `bobbeori-mcp/inventory.read` | Read items near or past expiry |
| `recipe.recommend` | `bobbeori-mcp/recipe.read` | Recommend recipes from inventory |
| `recipe.get` | `bobbeori-mcp/recipe.read` | Read recipe details and ingredient ownership |
| `ingredient.guide` | `bobbeori-mcp/guide.read` | Read storage, preparation, freshness, and nutrition guidance |
| `receipt.preview` / `receipt.commit` | `bobbeori-mcp/receipt.write` | Review, then stock confirmed receipt items |
| `shopping.preview` / `shopping.save` | `bobbeori-mcp/shopping.write` | Review, then add or merge shopping-list items |
| `calendar.preview` / `calendar.create` | `bobbeori-mcp/calendar.write` | Review, then create or update a Google Calendar event |
| `reminder.preview` / `reminder.create` | `bobbeori-mcp/calendar.write` | Review, then create a food-use or shopping reminder |

Every response uses the same `success`, `data`, `warnings`, `requires_confirmation`, `next_actions`, and `trace_id` envelope. The tools never accept `user_id`; the server derives it from the validated token subject.

Write tools accept only a short-lived, signed token returned by their matching preview tool and `confirmed=true`. A DB idempotency record returns the original result when the same confirmed action is retried. Apply the migration before enabling writes:

```powershell
Get-Content -Raw app/backend/schemas/migrations/20260720_add_mcp_mutations.sql | docker compose exec -T postgres sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
```

## Production authentication

Set the following values and serve the MCP endpoint through public HTTPS:

```dotenv
MCP_DEV_TOKEN_AUTH=false
MCP_ISSUER_URL=https://auth.example.com
MCP_RESOURCE_URL=https://api.example.com/mcp
MCP_JWKS_URL=https://auth.example.com/.well-known/jwks.json
MCP_JWT_AUDIENCE=https://api.example.com/mcp
MCP_JWT_ALGORITHMS=RS256
MCP_SCOPE_PREFIX=bobbeori-mcp
MCP_SUPPORTED_SCOPES=bobbeori-mcp/inventory.read,bobbeori-mcp/recipe.read,bobbeori-mcp/guide.read,bobbeori-mcp/receipt.write,bobbeori-mcp/shopping.write,bobbeori-mcp/calendar.write
MCP_REQUIRED_SCOPES=bobbeori-mcp/inventory.read,bobbeori-mcp/recipe.read,bobbeori-mcp/guide.read,bobbeori-mcp/receipt.write,bobbeori-mcp/shopping.write,bobbeori-mcp/calendar.write
MCP_PREVIEW_TOKEN_SECRET=replace-with-a-separate-random-secret-at-least-32-chars
MCP_PREVIEW_TTL_SECONDS=600
# Only needed if the reverse proxy forwards a Host/Origin unlike MCP_RESOURCE_URL.
MCP_ALLOWED_HOSTS=api.example.com
MCP_ALLOWED_ORIGINS=https://api.example.com
```

The authorization server must support OAuth 2.1 authorization code flow with PKCE and expose authorization-server metadata. Its access token `sub` is the external OAuth subject, and the Bobbeori user maps to it through `POST /api/v1/auth/mcp/link` after the user is signed in to Bobbeori. The MCP server validates signature, issuer, audience, expiry, and scopes and exposes protected-resource metadata at `/.well-known/oauth-protected-resource/mcp`.

The initial MCP account link requests all six scopes so ChatGPT and Codex can use every advertised tool without a second OAuth flow. Each tool still declares and enforces only its own scope, and write execution additionally requires the signed preview token plus explicit confirmation.

## Receipt storage

Local development stores uploaded receipt images in `OCR_UPLOAD_DIR`. In AWS, set:

```dotenv
RECEIPT_STORAGE_BACKEND=s3
AWS_REGION=ap-northeast-2
S3_RECEIPT_BUCKET=<receipt-bucket-name>
S3_RECEIPT_PREFIX=receipts
```

The API stores `s3://...` object URIs in the existing receipt row and serves receipt image downloads through short-lived S3 presigned redirects.

## Connect a client

After deploying to public HTTPS, Codex can register the server with:

```powershell
codex mcp add bobbeori --url https://api.example.com/mcp
codex mcp login bobbeori --scopes bobbeori-mcp/inventory.read,bobbeori-mcp/recipe.read,bobbeori-mcp/guide.read,bobbeori-mcp/receipt.write,bobbeori-mcp/shopping.write,bobbeori-mcp/calendar.write
```

For ChatGPT, enable developer mode, create a connector using the same public `/mcp` URL, and complete the OAuth account-linking flow.

## Optional workflow skill

The portable skill lives at `.agents/skills/bobbeori-workflows`. It has implicit invocation disabled so users opt in per task. Use `@bobbeori-workflows` in ChatGPT or `$bobbeori-workflows` in Codex. The same skill enforces preview, exact-token confirmation, and commit ordering on both hosts.
