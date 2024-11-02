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

# SeedGen Injected builder
FROM gcr.io/oss-fuzz-base/base-builder AS builder_seedgen_injected
COPY --from=golang:1.22 /usr/local/go /usr/local/go
ENV PATH="/usr/local/go/bin:${PATH}"
WORKDIR /app
COPY seedgen-injected/ /app/seedgen-injected/
RUN cd seedgen-injected && make


# Collect artifacts
# Use a minimal image to hold the artifacts
FROM alpine AS artifact_collector
WORKDIR /prebuilt
COPY --from=builder_callgraph /app/runtime/target/release/libcallgraph_rt.a libcallgraph_rt.a
COPY --from=builder_llvm_pass /app/llvm/SeedMindCFPass.so SeedMindCFPass.so
COPY --from=builder_argus /app/argus/target/release/argus argus
COPY --from=builder_bandld /app/bandld/target/release/bandld bandld
COPY --from=builder_getcov /app/getcov/target/release/getcov getcov
COPY --from=builder_seedgen_injected /app/seedgen-injected/bin/seedgen-injected seedgen-injected
