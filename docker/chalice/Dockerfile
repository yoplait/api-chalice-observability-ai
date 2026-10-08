FROM python:3.12-slim AS base
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PIP_NO_CACHE_DIR=1

# ---------- runtime: serves `chalice local` ----------
FROM base AS runtime
RUN groupadd -g 1001 app && useradd -u 1001 -g app -m -d /srv/app app
WORKDIR /srv/app
COPY requirements.txt ./requirements.txt
RUN pip install -r requirements.txt
COPY .chalice/ .chalice/
COPY app.py ./app.py
COPY chalicelib/ ./chalicelib/
USER app
EXPOSE 8000
CMD ["sh", "-c", "chalice local --host 0.0.0.0 --port 8000 --stage dev"]

# ---------- tests: pytest + coverage + tooling ----------
FROM base AS tests
RUN groupadd -g 1002 dev && useradd -u 1002 -g dev -m dev
WORKDIR /srv/project
COPY requirements.txt requirements-dev.txt ./
RUN pip install -r requirements-dev.txt
COPY --chown=dev:dev . .
USER dev
