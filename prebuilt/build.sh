# BUILD PREBUILT ARTIFACTS

# Use oss-fuzz docker image (gcr.io/oss-fuzz-base/base-builder)
# This script is meant to be run in oss-fuzz docker container

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# NOTICE: THIS PASS MUST BE BUILT IN OSS-FUZZ ENVIRONMENT
# FineIWillDoItMyself Pass
cd $SCRIPT_DIR/../FineIWillDoItMyselfPass
LLVM_CXXFLAGS=`llvm-config --cxxflags`
clang++ -fno-rtti -O3 -g $LLVM_CXXFLAGS -fno-exceptions -Wno-deprecated-declarations FineIWillDoItMyselfPass.cpp -fPIC -shared -Wl,-soname,FineIWillDoItMyselfPass.so -o FineIWillDoItMyselfPass.so
cp FineIWillDoItMyselfPass.so $SCRIPT_DIR/../prebuilt/FineIWillDoItMyselfPass.so

# Argus
cd $SCRIPT_DIR/../argus
cargo build --release
cp target/release/argus $SCRIPT_DIR/../prebuilt/argus

# getcov
cd $SCRIPT_DIR/../getcov
cargo build --release
cp target/release/getcov $SCRIPT_DIR/../prebuilt/getcov

# callgraph_rt
cd $SCRIPT_DIR/../callgraph_rt
cargo build --release
cp target/release/libcallgraph_rt.a $SCRIPT_DIR/../prebuilt/libcallgraph_rt.a

# seedgen-injected
cd $SCRIPT_DIR/../seedgen-injected
make
cp bin/seedgen-injected $SCRIPT_DIR/../prebuilt/seedgen-injected

echo "Prebuilt artifacts are in prebuilt/ directory"