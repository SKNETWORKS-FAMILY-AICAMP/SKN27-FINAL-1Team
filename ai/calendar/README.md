# Bobbeori Calendar MCP Server

Run this inside the Runpod pod:

```bash
cd /workspace
git clone <repo-url>
cd SKN27-FINAL-1Team
pip install -r ai/requirements.txt
export RUNPOD_INTERNAL_TOKEN="<same-token-as-backend>"
uvicorn ai.calendar.runpod_server:app --host 0.0.0.0 --port 8000
```

Health check:

```bash
curl http://127.0.0.1:8000/health
```

Backend `.env`:

```env
RUNPOD_CALENDAR_MCP_URL=https://<pod-id>-8000.proxy.runpod.net/mcp
RUNPOD_INTERNAL_TOKEN=<same-token-as-runpod>
RUNPOD_TIMEOUT_SECONDS=20
```

MCP tool:

- `create_calendar_event`: creates or updates one Google Calendar event using `bobbeoriKey`.
- `delete_calendar_event`: deletes one Google Calendar event using `bobbeoriKey`.
