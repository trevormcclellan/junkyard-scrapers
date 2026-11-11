FROM python:3.14.10-slim-bookworm AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt requirements-build.txt pyproject.toml ./
RUN pip install --no-cache-dir -r requirements-build.txt -r requirements.txt
COPY junkyard ./junkyard
COPY frontend ./frontend
RUN pip install --no-cache-dir --no-deps --no-build-isolation . && pip check

FROM base AS web
EXPOSE 5000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "from urllib.request import urlopen; urlopen('http://127.0.0.1:5000/healthz', timeout=3)"
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--timeout", "180", "frontend.app:create_app()"]

# Default remains the worker image for existing root Dockerfile builds.
FROM base AS worker
COPY jacks ./jacks
COPY lkq ./lkq
COPY picknpull ./picknpull
COPY pullapart ./pullapart
COPY upullandsave ./upullandsave
COPY tearapart ./tearapart
COPY utpap ./utpap
COPY pullnsave ./pullnsave
COPY healthcheck.sh ./healthcheck.sh
HEALTHCHECK --interval=60s --timeout=10s --start-period=30m --retries=3 \
    CMD python -m junkyard.worker --healthcheck
CMD ["python", "-m", "junkyard.worker", "--loop"]
