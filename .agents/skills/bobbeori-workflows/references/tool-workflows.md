# Bobbeori MCP workflow reference

| Intent | Preview or read | Confirmed write | Scope |
|---|---|---|---|
| View refrigerator | `inventory.list` | - | `bobbeori-mcp/inventory.read` |
| Find expiring food | `inventory.expiring` | - | `bobbeori-mcp/inventory.read` |
| Recommend recipes | `recipe.recommend` | - | `bobbeori-mcp/recipe.read` |
| View recipe | `recipe.get` | - | `bobbeori-mcp/recipe.read` |
| View ingredient guide | `ingredient.guide` | - | `bobbeori-mcp/guide.read` |
| Stock receipt items | `receipt.preview` | `receipt.commit` | `bobbeori-mcp/receipt.write` |
| Add shopping items | `shopping.preview` | `shopping.save` | `bobbeori-mcp/shopping.write` |
| Create calendar event | `calendar.preview` | `calendar.create` | `bobbeori-mcp/calendar.write` |
| Create reminder | `reminder.preview` | `reminder.create` | `bobbeori-mcp/calendar.write` |

## Connect

- MCP URL: `https://mcp.bobbeori.com/mcp`
- OAuth resource: `https://mcp.bobbeori.com`
- Codex OAuth client id: `3nu2uqh1ir8d10ljocufuj2qv1`
- ChatGPT OAuth client id: `7m1dlb7hauge5vccvlm6llg3j6`

Codex CLI setup:

```powershell
codex mcp add bobbeori `
  --url https://mcp.bobbeori.com/mcp `
  --oauth-client-id 3nu2uqh1ir8d10ljocufuj2qv1 `
  --oauth-resource https://mcp.bobbeori.com

codex mcp login bobbeori --scopes bobbeori-mcp/inventory.read,bobbeori-mcp/recipe.read,bobbeori-mcp/guide.read,bobbeori-mcp/receipt.write,bobbeori-mcp/shopping.write,bobbeori-mcp/calendar.write
```

## Input rules

- Receipt preview requires a receipt ID already produced by the Bobbeori receipt upload flow and the final reviewed item list.
- Shopping preview accepts explicit ingredients or a recipe ID whose missing ingredients should be used.
- Calendar and reminder datetimes must contain an explicit timezone offset, such as `2026-07-21T09:00:00+09:00`.
- Reminder type must be `consume_reminder` or `shopping_reminder`.

## Confirmation failures

- Expired or invalid token: run preview again.
- Changed user intent: discard the old token and run preview with the new values.
- Action already running: wait briefly, then retry the same confirmed call.
- `idempotent_replay=true`: the write already completed; report the cached result and do not create another preview.
- Missing scope: request only the scope declared by the selected tool.
