# BUILD PREBUILT ARTIFACTS

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Argus
cd $SCRIPT_DIR/../argus
cargo build --release --target x86_64-unknown-linux-musl
cp target/x86_64-unknown-linux-musl/release/argus $SCRIPT_DIR/../prebuilt/argus

# callgraph_rt
cd $SCRIPT_DIR/../callgraph_rt
cargo build --release --target x86_64-unknown-linux-musl
cp target/x86_64-unknown-linux-musl/release/libcallgraph_rt.a $SCRIPT_DIR/../prebuilt/libcallgraph_rt.a

echo "Prebuilt artifacts are in prebuilt/ directory"