FROM ubuntu:24.04 AS builder

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libtool autotools-dev automake pkg-config \
    bsdmainutils python3 libevent-dev libboost-dev \
    libboost-system-dev libboost-filesystem-dev \
    libsqlite3-dev libminiupnpc-dev libnatpmp-dev libzmq3-dev \
    ca-certificates git \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /build
COPY . .

RUN ./autogen.sh \
    && ./configure --with-incompatible-bdb --with-gui=no --disable-tests --disable-bench \
    && make -j"$(nproc)"

# ── Runtime image ────────────────────────────────────────────────────
FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && apt-get install -y --no-install-recommends \
    libevent-2.1-7t64 libevent-pthreads-2.1-7t64 \
    libboost-filesystem1.83.0 libboost-thread1.83.0 \
    libsqlite3-0 libminiupnpc17 libnatpmp1t64 libzmq5 \
    python3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /build/src/bitcoind /usr/local/bin/
COPY --from=builder /build/src/bitcoin-cli /usr/local/bin/

RUN useradd -m -s /bin/bash qbtc
USER qbtc
WORKDIR /home/qbtc

RUN mkdir -p /home/qbtc/.bitcoin && \
    printf '[qbtctestnet]\n\
chain=qbtctestnet\n\
server=1\n\
listen=1\n\
txindex=1\n\
fallbackfee=0.0001\n\
rpcuser=qbtcuser\n\
rpcpassword=qbtcpass\n\
rpcallowip=0.0.0.0/0\n\
rpcbind=0.0.0.0\n\
seednode=46.62.156.169:28333\n\
seednode=37.27.47.236:28333\n\
seednode=89.167.109.241:28333\n' > /home/qbtc/.bitcoin/bitcoin.conf

EXPOSE 28333 28332

VOLUME ["/home/qbtc/.bitcoin"]

ENTRYPOINT ["bitcoind", "-qbtctestnet", "-printtoconsole"]
