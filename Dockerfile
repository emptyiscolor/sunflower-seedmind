## Build Image (for Argus)
FROM ubuntu:22.04 as wrapper-builder
RUN export DEBIAN_FRONTEND=noninteractive && \
    apt-get update && apt-get install -y curl build-essential musl-tools && \
    apt-get clean && rm -rf /var/lib/apt/lists/*
RUN curl https://sh.rustup.rs -sSf | bash -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
RUN rustup target add x86_64-unknown-linux-musl
COPY argus /argus
RUN cd /argus && cargo build --release --target x86_64-unknown-linux-musl

## Build Image (for SeedGenInj)
FROM golang:1.22 as seedgeninj-builder
WORKDIR /app
COPY seedgen-injected .
RUN make

## Runtime Image
FROM ubuntu:22.04 as runtime

WORKDIR /app

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update && apt-get -y install \
    7zip \
    autoconf \
    automake \
    autotools-dev \
    bash \
    binutils \
    bsdextrautils \
    build-essential \
    ca-certificates \
    curl \
    file \
    git \
    git-lfs \
    gnupg2 \
    gzip \
    jq \
    libcap2 \
    ltrace \
    make \
    openssl \
    patch \
    perl-base \
    python3 \
    python3-dev \
    python3-pip \
    python3-setuptools \
    python3-venv \
    python3-wheel \
    rsync \
    software-properties-common \
    strace \
    tar \
    tzdata \
    unzip \
    vim \
    wget \
    xz-utils \
    zip \
    && apt-get clean \
    && rm -rf /var/lib/{apt,dpkg,cache,log}

ARG YQ_VERSION=4.43.1
ARG YQ_BINARY=yq_linux_amd64
RUN wget -q https://github.com/mikefarah/yq/releases/download/v${YQ_VERSION}/${YQ_BINARY} -O /usr/bin/yq && \
    chmod +x /usr/bin/yq

# Enable Docker-from-Docker support
RUN set -eux; \
    install -m 0755 -d /etc/apt/keyrings; \
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc; \
    chmod a+r /etc/apt/keyrings/docker.asc; \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu \
    $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
    containerd.io \
    docker-ce \
    docker-ce-cli \
    docker-buildx-plugin; \
    apt-get autoremove -y; \
    rm -rf /var/lib/apt/lists/*

RUN GRPC_HEALTH_PROBE_VERSION=v0.4.27 && \
    wget -qO/bin/grpc_health_probe https://github.com/grpc-ecosystem/grpc-health-probe/releases/download/${GRPC_HEALTH_PROBE_VERSION}/grpc_health_probe-linux-amd64 && \
    chmod +x /bin/grpc_health_probe

# Pre-download seed pool
RUN echo "Jul 14 Update" && cd / && wget https://bandfuzz.s3.amazonaws.com/seeds-global-shrink.tar.gz -O /seeds-global.tar.gz && \
    tar -xvf /seeds-global.tar.gz && \
    rm /seeds-global.tar.gz

# Install GRPC Dependencies (server)
COPY seedgen-server/requirements.txt ./requirements.txt
RUN pip3 install --no-cache-dir -r ./requirements.txt

COPY --from=wrapper-builder /argus/target/x86_64-unknown-linux-musl/release/argus /argus
COPY --from=seedgeninj-builder /app/bin/seedgen-injected /seedgen-injected

# Copy Python code
COPY seedgen-server .

CMD ["python3", "app.py"]