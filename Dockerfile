# CallGraph runtime builder
FROM gcr.io/oss-fuzz-base/base-builder AS builder_callgraph
RUN curl https://sh.rustup.rs -sSf | bash -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
WORKDIR /app
COPY callgraph/runtime runtime
RUN cd runtime && cargo build --release

# CallGraph LLVM Pass builder
FROM gcr.io/oss-fuzz-base/base-builder AS builder_llvm_pass
WORKDIR /app
COPY callgraph/llvm /app/llvm
RUN cd llvm && ./build.sh

# Argus builder
FROM gcr.io/oss-fuzz-base/base-builder AS builder_argus
RUN curl https://sh.rustup.rs -sSf | bash -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
WORKDIR /app
COPY argus/ /app/argus/
RUN cd argus && cargo build --release

# Bandld builder
FROM gcr.io/oss-fuzz-base/base-builder AS builder_bandld
RUN curl https://sh.rustup.rs -sSf | bash -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
WORKDIR /app
COPY bandld/ /app/bandld/
RUN cd bandld && cargo build --release

# GetCov builder
FROM gcr.io/oss-fuzz-base/base-builder AS builder_getcov
RUN curl https://sh.rustup.rs -sSf | bash -s -- -y
ENV PATH="/root/.cargo/bin:${PATH}"
WORKDIR /app
COPY getcov/ /app/getcov/
RUN cd getcov && cargo build --release

# SeedD builder
FROM gcr.io/oss-fuzz-base/base-builder AS builder_seedd
COPY --from=golang:1.22 /usr/local/go /usr/local/go
ENV PATH="/usr/local/go/bin:${PATH}"
WORKDIR /app
COPY seedd/ /app/seedd/
RUN cd seedd && make


# Collect artifacts
# Use a minimal image to hold the artifacts
FROM cruizba/ubuntu-dind:noble-latest AS seedgen_runner

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
    python-is-python3 \
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

WORKDIR /app
COPY ./seedgen2 ./seedgen2
COPY ./aixcc.py ./aixcc.py
COPY ./task_handler.py ./task_handler.py
COPY ./requirements.txt ./requirements.txt

RUN mkdir prebuilt
COPY --from=builder_callgraph /app/runtime/target/release/libcallgraph_rt.a ./prebuilt/libcallgraph_rt.a
COPY --from=builder_llvm_pass /app/llvm/SeedMindCFPass.so ./prebuilt/SeedMindCFPass.so
COPY --from=builder_argus /app/argus/target/release/argus ./prebuilt/argus
COPY --from=builder_bandld /app/bandld/target/release/bandld ./prebuilt/bandld
COPY --from=builder_getcov /app/getcov/target/release/getcov ./prebuilt/getcov
COPY --from=builder_seedd /app/seedd/bin/seedd ./prebuilt/seedd

RUN pip3 install -r requirements.txt --break-system-packages

ENV PYTHONUNBUFFERED=1

COPY ./entrypoint.sh ./entrypoint.sh

ENTRYPOINT ["./entrypoint.sh"]