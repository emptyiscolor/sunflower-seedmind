#!/bin/bash

# Start docker
start-docker.sh


docker pull \
    gcr.io/oss-fuzz-base/base-builder@sha256:0241b5bf8a95a788807fd6632d544a0bae7289bd17f04b766dec79db7acab5f5

docker tag \
    gcr.io/oss-fuzz-base/base-builder@sha256:0241b5bf8a95a788807fd6632d544a0bae7289bd17f04b766dec79db7acab5f5 gcr.io/oss-fuzz-base/base-builder:latest

docker pull \
    gcr.io/oss-fuzz-base/base-runner@sha256:eb450aa403ead8e9c0145e63726bbeca85588fbf95105a1550c838f34cc481c5 

docker tag \
    gcr.io/oss-fuzz-base/base-runner@sha256:eb450aa403ead8e9c0145e63726bbeca85588fbf95105a1550c838f34cc481c5  gcr.io/oss-fuzz-base/base-runner:latest

# prepare output directory
seeds_agg_dir="/workspaces/corpus"
mkdir -p "$seeds_agg_dir"

# Commands go here
python infra/oss-fuzz.py --root $OSSFUZZ_PATH --model $SEEDGEN_GENERATIVE_MODEL $PROJECT $HARNESSNAME && \
    echo "Seeds generated successfully"

# find "/app/.tmp/$PROJECT" -type d -name "seeds"
# Find all seeds folders within the project directory
while IFS= read -r seeds_folder; do
    # Check if the seeds folder contains any regular files
    if find "$seeds_folder" -maxdepth 1 -type f | grep -q .; then
        # Create destination directory
        mkdir -p "$seeds_agg_dir/$PROJECT"
        
        # Copy all regular files from seeds folder to aggregated location
        find "$seeds_folder" -maxdepth 1 -type f -exec cp {} "$seeds_agg_dir/$PROJECT/" \;
        
        echo "Collected seeds from $seeds_folder to $seeds_agg_dir/$PROJECT"
    fi
done < <(find "/app/.tmp/$PROJECT" -type d -name "seeds")