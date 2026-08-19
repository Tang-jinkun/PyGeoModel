#!/usr/bin/env bash
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
DELIVERY_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
if [ "${1:-}" = "--dry-run" ]; then
  DRY_RUN=1
else
  DRY_RUN=0
fi

case "$(uname -m)" in
  x86_64|amd64) ARCHITECTURE=amd64 ;;
  aarch64|arm64) ARCHITECTURE=arm64 ;;
  *) echo "Unsupported host architecture: $(uname -m)" >&2; exit 1 ;;
esac

COMPOSE_FILE="$DELIVERY_ROOT/deploy/offline/docker-compose.yml"
IMAGE_DIR="$DELIVERY_ROOT/images"
BACKEND_ARCHIVE="$IMAGE_DIR/pygeomodel-backend-linux-$ARCHITECTURE.tar"
FRONTEND_ARCHIVE="$IMAGE_DIR/pygeomodel-frontend-linux-$ARCHITECTURE.tar"

[ -f "$COMPOSE_FILE" ] || { echo "Offline Compose file not found: $COMPOSE_FILE" >&2; exit 1; }
[ -f "$BACKEND_ARCHIVE" ] || { echo "Required image archive not found: $BACKEND_ARCHIVE" >&2; exit 1; }
[ -f "$FRONTEND_ARCHIVE" ] || { echo "Required image archive not found: $FRONTEND_ARCHIVE" >&2; exit 1; }

if [ "$DRY_RUN" -eq 0 ]; then
  OSTYPE=$(docker info --format '{{.OSType}}' 2>/dev/null) || {
    echo "Docker daemon is unavailable." >&2
    exit 1
  }
  [ "$OSTYPE" = "linux" ] || { echo "Docker must use Linux containers; detected OSTYPE='$OSTYPE'." >&2; exit 1; }
fi

for archive in "$BACKEND_ARCHIVE" "$FRONTEND_ARCHIVE"; do
  if [ "$DRY_RUN" -eq 1 ]; then
    echo "docker load --input $archive"
  else
    docker load --input "$archive"
  fi
done

export PYGEOMODEL_IMAGE_TAG="offline-$ARCHITECTURE"
export PYGEOMODEL_OFFLINE=1
if [ "$DRY_RUN" -eq 1 ]; then
  echo "docker compose -f $COMPOSE_FILE up -d --no-build"
else
  cd "$DELIVERY_ROOT"
  docker compose -f "$COMPOSE_FILE" up -d --no-build
fi

echo "Offline PyGeoModel selected linux/$ARCHITECTURE images."
