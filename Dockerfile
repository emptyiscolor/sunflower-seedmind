# Use oss-fuzz docker image (gcr.io/oss-fuzz-base/base-builder)
FROM gcr.io/oss-fuzz-base/base-builder
RUN curl https://sh.rustup.rs -sSf | bash -s -- -y
COPY --from=golang:1.22 /usr/local/go /usr/local/go
ENV PATH="/usr/local/go/bin:/root/.cargo/bin:${PATH}"
WORKDIR /app
COPY FineIWillDoItMyselfPass/ /app/FineIWillDoItMyselfPass/
COPY argus/ /app/argus/
COPY getcov/ /app/getcov/
COPY callgraph_rt/ /app/callgraph_rt/
COPY seedgen-injected/ /app/seedgen-injected/
CMD ["bash", "-c", "/app/prebuilt/build.sh"]