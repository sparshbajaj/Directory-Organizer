# ============================================================
# VaultSort Docker Image — Multi-Stage Build
# Produces a minimal Alpine image (~25MB) with:
#   - VaultSort daemon binary
#   - Antigravity CLI (agy)
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

# ---- Stage 2: Install Antigravity CLI ----
FROM alpine:3.21 AS agy-installer

RUN apk add --no-cache curl ca-certificates bash
RUN curl -fsSL https://antigravity.google/cli/install.sh | bash \
    || { echo "AGY CLI install skipped"; mkdir -p /root/.local/bin; touch /root/.local/bin/agy; }

# ---- Stage 3: Final Runtime Image ----
FROM alpine:3.21

LABEL maintainer="Sparsh Bajaj"
LABEL description="VaultSort — AI-powered directory organizer daemon"
LABEL org.opencontainers.image.source="https://github.com/sparshbajaj/Directory-Organizer"

# Runtime dependencies
RUN apk add --no-cache ca-certificates tzdata

# Copy binaries
COPY --from=builder /vaultsort /usr/local/bin/vaultsort

COPY --from=agy-installer /root/.local/bin/agy /usr/local/bin/agy
# Pre-configure AGY for headless non-interactive mode
RUN mkdir -p /root/.gemini/antigravity-cli && \
    echo '{"toolPermission":"always-proceed","enableTelemetry":false}' \
    > /root/.gemini/antigravity-cli/settings.json

# Create data directories
RUN mkdir -p /data/watch /data/vault

# Default environment variables
ENV VAULTSORT_DIRS="/data/watch"
ENV VAULTSORT_MODE="both"
ENV VAULTSORT_INTERVAL="5m"
ENV VAULTSORT_PORT="8080"
ENV VAULTSORT_DB_PATH="/data/vaultsort.db"
ENV VAULTSORT_VAULT_PATH="/data/vault"
ENV VAULTSORT_LOG_LEVEL="info"
ENV VAULTSORT_GITHUB_CHECK="true"
ENV VAULTSORT_GITHUB_INTERVAL="6h"

# Expose dashboard port
EXPOSE 8080

# Persistent data volume
VOLUME ["/data"]

# Health check via dashboard API
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD wget -qO- http://localhost:8080/api/status || exit 1

# Run the daemon
ENTRYPOINT ["vaultsort", "daemon"]
