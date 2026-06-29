FROM node:22-alpine

ARG NPM_REGISTRY=https://mirrors.cloud.tencent.com/npm/
ARG VITE_API_BASE=/PyGeoModel
ARG VITE_BASE_PATH=/PyGeoModel/
ARG VITE_PROXY_TARGET=http://backend:8000

ENV VITE_API_BASE=${VITE_API_BASE}
ENV VITE_BASE_PATH=${VITE_BASE_PATH}
ENV VITE_PROXY_TARGET=${VITE_PROXY_TARGET}

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json /app/
RUN npm ci --registry="${NPM_REGISTRY}"

COPY frontend /app
RUN npm run build

EXPOSE 5173

CMD ["npm", "run", "preview", "--", "--host", "0.0.0.0", "--port", "5173"]
