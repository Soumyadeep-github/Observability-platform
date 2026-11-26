FROM python:3.12-slim AS app
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 OBS_HOST=0.0.0.0 OBS_PORT=8000
WORKDIR /srv
COPY backend/requirements-live.txt .
RUN pip install --no-cache-dir -r requirements-live.txt && mkdir /data && chown 65532 /data
COPY backend/app app
USER 65532:65532
ENV DATABASE_URL=/data/platform.sqlite3
EXPOSE 8000
CMD ["sh","-c","exec uvicorn app.main:create_app --factory --host \"$OBS_HOST\" --port \"$OBS_PORT\""]
FROM app AS collector
USER root
RUN pip install --no-cache-dir boto3
USER 65532:65532
ENTRYPOINT ["python","-m","app.collect"]
FROM app AS runtime
