# ──────────────────────────────────────────────────────────────────────────────
# Stage 1 – Builder
# Compiles bitcoind and bitcoin-cli from source.
# ──────────────────────────────────────────────────────────────────────────────
FROM ubuntu:24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libtool \
    autotools-dev \
    automake \
    pkg-config \
    bsdmainutils \
    python3 \
    libevent-dev \
    libboost-dev \
    libboost-system-dev \
    libboost-filesystem-dev \
    libsqlite3-dev \
    libminiupnpc-dev \
    libnatpmp-dev \
    libzmq3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /qbtc
COPY . .

RUN ./autogen.sh && \
    ./configure \
        --with-incompatible-bdb \
        --with-gui=no \
        --disable-tests \
        --disable-bench && \
    make -j$(nproc) && \
    strip src/bitcoind src/bitcoin-cli

# ──────────────────────────────────────────────────────────────────────────────
# Stage 2 – Runtime
# Minimal image that only carries the compiled binaries and runtime libs.
# ──────────────────────────────────────────────────────────────────────────────
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    libevent-2.1-7t64 \
    libboost-filesystem1.83.0 \
    libboost-system1.83.0 \
    libsqlite3-0 \
    libminiupnpc17 \
    libnatpmp1t64 \
    libzmq5 \
    python3 \
    && rm -rf /var/lib/apt/lists/*

# Copy binaries from builder
COPY --from=builder /qbtc/src/bitcoind  /usr/local/bin/bitcoind
COPY --from=builder /qbtc/src/bitcoin-cli /usr/local/bin/bitcoin-cli

# Copy config template and helper script
COPY --from=builder /qbtc/contrib/qbtc-testnet/qbtc-testnet.conf /etc/qbtc/bitcoin.conf
COPY --from=builder /qbtc/contrib/qbtc-testnet/qbtc-testnet.sh   /usr/local/bin/qbtc.sh

# Copy the Docker entrypoint
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/qbtc.sh /usr/local/bin/docker-entrypoint.sh

# P2P port and RPC port
EXPOSE 28333 28332

# Persistent blockchain data
VOLUME /data

ENTRYPOINT ["/usr/local/bin/docker-entrypoint.sh"]
