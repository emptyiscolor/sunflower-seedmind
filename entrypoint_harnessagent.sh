#!/bin/bash

# Start docker
start-docker.sh

# prepare output directory
seeds_agg_dir="/workspaces/corpus"
mkdir -p "$seeds_agg_dir"

# Commands go here
python infra/oss-fuzz.py --root $OSSFUZZ_PATH --model $SEEDGEN_GENERATIVE_MODEL $PROJECT $HARNESSNAME

echo "Seeds generated successfully"

# find "/app/.tmp/$PROJECT" -type d -name "seeds"
# Find all seeds folders within the project directory
while IFS= read -r seeds_folder; do
    # Check if the seeds folder contains any regular files
    if find "$seeds_folder" -maxdepth 1 -type f | grep -q .; then
        # Create destination directory
        mkdir -p "$seeds_agg_dir/$project_name"
        
        # Copy all regular files from seeds folder to aggregated location
        find "$seeds_folder" -maxdepth 1 -type f -exec cp {} "$seeds_agg_dir/$project_name/" \;
        
        echo "Collected seeds from $seeds_folder to $seeds_agg_dir/$project_name/"
    fi
done < <(find "/app/.tmp/$PROJECT" -type d -name "seeds")