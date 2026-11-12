FROM ghcr.io/home-assistant/base:3.24
ARG BUILD_ARCH
ARG TARGETARCH
ARG BUILD_VERSION=0.1.2
RUN apk add --no-cache nginx python3 libstdc++ libgcc \
    && addgroup -g 10001 timepro && adduser -D -H -u 10001 -G timepro timepro
RUN set -eu; \
    case "${BUILD_ARCH:-${TARGETARCH}}" in \
      aarch64|arm64) arch=aarch64; checksum=a94f9e4cbd1c43b7cbdb73bcf5526aed329acc26f85fc043fed68e4362b12632 ;; \
      amd64) arch=amd64; checksum=79bdacfe8f15c678bbe2d91afabeca0f985bec22dbf7daf8ced241120a2c8da7 ;; \
      *) echo "Unsupported CPU architecture" >&2; exit 1 ;; \
    esac; \
    curl --fail --location --proto '=https' --tlsv1.2 --retry 3 \
      "https://github.com/TKtheDEV/timepro-home-assistant/releases/download/v0.1.0/timepro-ha-${arch}.tar.gz" -o /tmp/runtime.tar.gz; \
    echo "${checksum}  /tmp/runtime.tar.gz" | sha256sum -c -; \
    tar -xzf /tmp/runtime.tar.gz -C /; rm /tmp/runtime.tar.gz; \
    if [ "${arch}" = amd64 ]; then \
      curl --fail --location --proto '=https' --tlsv1.2 --retry 3 \
        "https://github.com/TKtheDEV/timepro-home-assistant/releases/download/v0.1.1/llama-server-amd64-baseline.tar.gz" -o /tmp/baseline.tar.gz; \
      echo "cd09e026cea4f8b2aabe26d6db25b6d8df8887282084fae374341c64f2f959bb  /tmp/baseline.tar.gz" | sha256sum -c -; \
      tar -xzf /tmp/baseline.tar.gz -C /; rm /tmp/baseline.tar.gz; \
    fi
COPY rootfs /
RUN chmod +x /etc/s6-overlay/s6-rc.d/*/run /etc/s6-overlay/s6-rc.d/*/finish
LABEL io.hass.version="${BUILD_VERSION}" io.hass.type="app" io.hass.arch="${BUILD_ARCH}" \
      org.opencontainers.image.title="TimePRO" \
      org.opencontainers.image.source="https://github.com/TKtheDEV/timepro-home-assistant"
