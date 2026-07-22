# Bobbeori Calendar MCP

## RunPod Serverless

Worker entrypoint:

```bash
python -m ai.calendar.runpod_handler
```

Build image:

```bash
docker build -f ai/calendar/Dockerfile -t <dockerhub-id>/bobbeori-calendar-runpod:latest .
docker push <dockerhub-id>/bobbeori-calendar-runpod:latest
```

Backend `.env`:

```env
RUNPOD_CALENDAR_SERVERLESS_URL=https://api.runpod.ai/v2/<endpoint-id>
RUNPOD_API_KEY=<runpod-api-key>
RUNPOD_INTERNAL_TOKEN=<same-token-as-worker>
RUNPOD_TIMEOUT_SECONDS=60
```

## Optional MCP Pod Server

```bash
pip install -r ai/calendar/requirements.txt
export RUNPOD_INTERNAL_TOKEN="<same-token-as-backend>"
uvicorn ai.calendar.runpod_server:app --host 0.0.0.0 --port 8000
```

Tools:

- `create_calendar_event`
- `delete_calendar_event`
