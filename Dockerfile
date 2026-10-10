# Nudge API container - works on Azure App Service / Container Apps, AWS App Runner, Render, Railway, Fly
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY engine ./engine
COPY data ./data
COPY static ./static
COPY api.py .
# Clouds pass the port in $PORT; default 8000 for local runs
ENV PORT=8000
EXPOSE 8000
CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port ${PORT}"]
