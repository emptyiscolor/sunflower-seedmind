#!/usr/bin/env bash

# Base directory
BASE_DIR=".tmp"

# Loop through all subdirectories except 'cache'
for project_dir in "$BASE_DIR"/*/; do
    project_name=$(basename "$project_dir")

    # Skip 'cache'
    if [[ "$project_name" == "cache" ]]; then
        continue
    fi

    # Find 'seeds' directories inside the project
    seeds_dirs=$(find "$project_dir" -type d -name "seeds" 2>/dev/null)

    total_count=0
    # If seeds directory exists, count files starting with 'seed_'
    if [[ -n "$seeds_dirs" ]]; then
        for dir in $seeds_dirs; do
            count=$(find "$dir" -type f -name "seed_*" | wc -l)
            total_count=$((total_count + count))
        done
    fi

    # Print result for this project
    echo "$project_name: $total_count"
done