# WorldHello

WorldHello is an early prototype for worldwide, nickname-based stranger text chat and language practice.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
uvicorn main:app --reload
```

Open http://127.0.0.1:8000. Health check: /health.

## Deploy

The included `render.yaml` defines a Render Python web service. In Render, connect this repository and create the Blueprint/service. Free services may sleep when idle; public hosting is not yet configured by this repository alone.

## Important limitations

- Matching is held in process memory and does not work reliably across multiple service instances; waiting users and reports are lost on restart.
- No persistent reports/blocks, moderator dashboard, age verification, or production abuse-prevention system.
- Text chat only. Audio is not implemented in this Python version.
- Do not launch publicly as a production service until persistent moderation, privacy/legal notices, safety workflows, and multi-user deployment tests are completed.
