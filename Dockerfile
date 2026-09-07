FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY bench ./bench
RUN pip install --no-cache-dir -e ".[bench]"

EXPOSE 8081 8082
