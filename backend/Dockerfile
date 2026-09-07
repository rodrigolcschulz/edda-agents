FROM docker:28-cli AS docker-cli

FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY backend ./backend
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
