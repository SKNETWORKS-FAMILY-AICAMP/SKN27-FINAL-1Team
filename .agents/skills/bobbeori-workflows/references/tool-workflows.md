# Bobbeori MCP workflow reference

| Intent | Preview or read | Confirmed write | Scope |
|---|---|---|---|
| View refrigerator | `inventory.list` | — | `inventory:read` |
| Find expiring food | `inventory.expiring` | — | `inventory:read` |
| Recommend recipes | `recipe.recommend` | — | `recipe:read` |
| View recipe | `recipe.get` | — | `recipe:read` |
| View ingredient guide | `ingredient.guide` | — | `guide:read` |
| Stock receipt items | `receipt.preview` | `receipt.commit` | `receipt:write` |
| Add shopping items | `shopping.preview` | `shopping.save` | `shopping:write` |
| Create calendar event | `calendar.preview` | `calendar.create` | `calendar:write` |
| Create reminder | `reminder.preview` | `reminder.create` | `calendar:write` |

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
