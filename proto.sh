#!/bin/bash

# SeedGen <-> SeedGenInj
protoc -I=proto --go_out=. seedgeninj.proto
protoc -I=proto --go-grpc_out=. seedgeninj.proto
python3 -m grpc_tools.protoc -I=proto --python_out=seedgen --grpc_python_out=seedgen seedgeninj.proto
