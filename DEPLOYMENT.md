# Axon Nudge API deployment

The Dockerfile is the canonical deployment artifact. It builds the FastAPI nudge API from `api.py`, `engine/`, `data/`, and `static/`.

## Quick demo: Render

1. In Render, choose **New > Blueprint** and select the `backend_4pm` branch.
2. Render reads `render.yaml` and builds the root `Dockerfile`.
3. When the service is live, open `https://YOUR-SERVICE.onrender.com/health`.
4. Set `window.AXON_NUDGE_API_BASE_URL` in `js/config.js` to that URL (no trailing slash), then publish the frontend.

## AWS target: App Runner with Docker

1. Build the root Dockerfile and publish it to Amazon ECR.
2. In AWS App Runner, create a service from that ECR image.
3. Set `PORT=8000` if App Runner does not supply it automatically; the image binds to `0.0.0.0` and respects `PORT`.
4. Use the App Runner service URL as `AXON_NUDGE_API_BASE_URL`.

The API must be publicly reachable for this public demo. Do not put OpenAI keys in the frontend or this repository.
