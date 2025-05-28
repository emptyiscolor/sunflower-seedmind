#!/bin/bash
docker run --rm -p 4317:4317 -p 16686:16686 jaegertracing/all-in-one:latest
