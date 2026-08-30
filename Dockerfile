# Pentool — container image
#
# Multi-stage: install pentool into a slim Python image, add the Lightpanda
# binary for JS crawling, and run as a non-root user with the CLI entrypoint.
# The container is meant for CI/CD automation (headless scans); the interactive
# TUI works too when attached with a TTY.

# ---- build stage: install pentool + deps ----
FROM python:3.12-slim AS build

ENV UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    PATH="/root/.local/bin:${PATH}"

# uv for a fast, deterministic install
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /build

# Install pentool from source (the repo mounted/built). Use the local tree so
# the image matches the commit being deployed.
COPY . /build
RUN uv venv /opt/pentool-venv \
 && uv pip install --python /opt/pentool-venv/bin/python /build \
    --no-cache

# ---- runtime stage ----
FROM python:3.12-slim

# Non-root user
RUN useradd --create-home --uid 1000 pentool
WORKDIR /home/pentool

COPY --from=build /opt/pentool-venv /opt/pentool-venv
ENV PATH="/opt/pentool-venv/bin:${PATH}" \
    UV_SYSTEM_PYTHON=1

# Lightpanda binary for JS crawling (fast, light headless JS engine).
# python:slim has no curl — install it (and clean the apt cache) in one layer.
ARG LIGHTPANDA_VERSION=0.3.7
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl ca-certificates; \
    rm -rf /var/lib/apt/lists/*; \
    ARCH="$(uname -m)"; case "$ARCH" in \
      x86_64) LP_ARCH="x86_64" ;; \
      aarch64|arm64) LP_ARCH="aarch64" ;; \
      *) echo "unsupported arch: $ARCH"; exit 1 ;; \
    esac; \
    curl -fsSL -o /usr/local/bin/lightpanda \
      "https://github.com/lightpanda-io/browser/releases/download/${LIGHTPANDA_VERSION}/lightpanda-${LP_ARCH}-linux"; \
    chmod +x /usr/local/bin/lightpanda

# Playwright Chromium is NOT included by default (heavy). If you need `--real`
# mode inside the container, install it explicitly:
#   RUN pip install playwright && python -m playwright install --with-deps chromium

USER pentool

# Data/config persistence across runs
ENV PENTOOL_CONFIG_DIR=/home/pentool/.config/pentool
VOLUME ["/home/pentool/.config/pentool"]

# Default: CLI headless scan (CI-friendly). Interactive TUI: attach a TTY and
# run `pentool` (no args) / override the entrypoint command.
ENTRYPOINT ["pentool"]
CMD ["--help"]
