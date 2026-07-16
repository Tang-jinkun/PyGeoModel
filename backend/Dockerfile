FROM python:3.12-slim

ARG DEBIAN_MIRROR=https://mirrors.cloud.tencent.com/debian
ARG DEBIAN_SECURITY_MIRROR=https://mirrors.cloud.tencent.com/debian-security
ARG PIP_INDEX_URL=https://pypi.org/simple

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN sed -i \
        -e "s|http://deb.debian.org/debian-security|${DEBIAN_SECURITY_MIRROR}|g" \
        -e "s|http://deb.debian.org/debian|${DEBIAN_MIRROR}|g" \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends gdal-bin \
    && rm -rf /var/lib/apt/lists/*

COPY backend/requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir --timeout 120 --retries 5 \
    --index-url "${PIP_INDEX_URL}" \
    -r /app/requirements.txt

COPY backend/app /app/app
COPY scripts /app/scripts

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
