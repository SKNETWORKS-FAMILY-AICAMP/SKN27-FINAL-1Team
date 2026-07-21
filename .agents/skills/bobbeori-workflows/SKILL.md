---
name: bobbeori-workflows
description: Safely use the Bobbeori MCP for refrigerator inventory, expiring ingredients, recipe recommendations, receipt stocking, shopping lists, Google Calendar events, and food or shopping reminders. Use when a user asks ChatGPT or Codex to work with their connected Bobbeori account; always preview writes and obtain explicit confirmation before commit, save, or create.
---

# Bobbeori workflows

Use the connected `bobbeori` MCP. Never request or invent `user_id`; authentication supplies the account.

## Read

Call the narrowest matching read tool. Summarize returned data without claiming a mutation occurred.

- Inventory or expiry: `inventory.list`, `inventory.expiring`
- Recipe ideas or details: `recipe.recommend`, `recipe.get`
- Ingredient handling: `ingredient.guide`

## Write

Follow this sequence without exception:

1. Call the matching `*.preview` tool.
2. Show the preview and every warning to the user.
3. Ask for explicit confirmation of that exact preview.
4. Only after confirmation, pass the returned `confirmation_token` unchanged to the matching write tool with `confirmed=true`.
5. Report identifiers and whether the result was an `idempotent_replay`.

If the user changes any field, run preview again. Never decode, edit, manufacture, or reuse a token for another action or account. Never treat vague assent given before preview as confirmation.

Use these pairs:

- Receipt stocking: `receipt.preview` → `receipt.commit`
- Shopping list: `shopping.preview` → `shopping.save`
- Calendar event: `calendar.preview` → `calendar.create`
- Food or shopping reminder: `reminder.preview` → `reminder.create`

Read [references/tool-workflows.md](references/tool-workflows.md) when choosing inputs, scopes, or handling failures.

## Host usage

In ChatGPT, select this skill with `@bobbeori-workflows`. In Codex, invoke `$bobbeori-workflows`. The workflow and MCP tools are otherwise identical.
