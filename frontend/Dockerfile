FROM node:22-alpine

ARG NPM_REGISTRY=https://mirrors.cloud.tencent.com/npm/
ARG VITE_PROXY_TARGET=http://backend:8000
ARG VITE_MAP_ENGINE=maplibre
ARG VITE_MAPBOX_ACCESS_TOKEN

ENV VITE_PROXY_TARGET=${VITE_PROXY_TARGET}
ENV VITE_MAP_ENGINE=${VITE_MAP_ENGINE}
ENV VITE_MAPBOX_ACCESS_TOKEN=${VITE_MAPBOX_ACCESS_TOKEN}

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json /app/
RUN npm ci --registry="${NPM_REGISTRY}"

COPY frontend /app
RUN case "${VITE_MAP_ENGINE}" in \
      maplibre) ;; \
      mapbox) test -n "${VITE_MAPBOX_ACCESS_TOKEN}" || \
        { echo "VITE_MAPBOX_ACCESS_TOKEN is required when VITE_MAP_ENGINE=mapbox" >&2; exit 1; } ;; \
      *) echo 'VITE_MAP_ENGINE must be "maplibre" or "mapbox"' >&2; exit 1 ;; \
    esac \
    && npm run build

EXPOSE 5173

CMD ["sh", "-c", "node /app/docker/write-runtime-config.mjs && exec node /app/docker/server.mjs"]
