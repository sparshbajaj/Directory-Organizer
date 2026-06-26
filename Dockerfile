# ============================================================
# VaultSort Docker Image — Multi-Stage Build
# Produces a minimal Alpine image (~25MB) with:
#   - VaultSort daemon binary
# ============================================================

# ---- Stage 1: Build VaultSort ----
FROM golang:1.24-alpine AS builder

# modernc.org/sqlite is pure Go (no CGO needed)
ENV CGO_ENABLED=0

RUN apk add --no-cache git

WORKDIR /src
COPY go.mod go.sum ./
RUN go mod download

COPY . .

ARG VERSION=dev
ARG BUILD_TIME=unknown

RUN go build \
    -ldflags="-s -w -X github.com/sparshbajaj/directory-organizer/cmd.Version=${VERSION} -X github.com/sparshbajaj/directory-organizer/cmd.BuildTime=${BUILD_TIME}" \
    -o /vaultsort \
    ./main.go

# ---- Stage 2: Final Runtime Image ----
FROM alpine:3.21

LABEL maintainer="Sparsh Bajaj"
LABEL description="VaultSort — AI-powered directory organizer daemon"
LABEL org.opencontainers.image.source="http://192.168.0.247:3002/sparsh/Directory-Organizer"

# Runtime dependencies — including curl/npm for AI CLI auto-install
RUN apk add --no-cache ca-certificates tzdata curl npm

# Copy binaries
COPY --from=builder /vaultsort /usr/local/bin/vaultsort

# Create data directories
RUN mkdir -p /data/watch /data/vault

# Default environment variables
ENV VAULTSORT_DIRS="/data/watch"
ENV VAULTSORT_MODE="server"
ENV VAULTSORT_INTERVAL="5m"
ENV VAULTSORT_PORT="2345"
ENV VAULTSORT_DB_PATH="/data/vaultsort.db"
ENV VAULTSORT_VAULT_PATH="/data/vault"
ENV VAULTSORT_LOG_LEVEL="info"
ENV VAULTSORT_GITHUB_CHECK="true"
ENV VAULTSORT_GITHUB_INTERVAL="6h"
ENV VAULTSORT_AI_CLI=""
ENV VAULTSORT_RULES_PATH="/data/rules.json"
ENV VAULTSORT_KB_PATH="/data/knowledge.db"
ENV VAULTSORT_DATA_DIR="/data"

# Expose dashboard port
EXPOSE 2345

# Persistent data volume
VOLUME ["/data"]

# ponytail: healthcheck uses env var so it works when port is overridden
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD sh -c "wget -qO- http://localhost:\${VAULTSORT_PORT:-2345}/api/status" || exit 1

# Run the daemon
ENTRYPOINT ["vaultsort", "daemon"]
