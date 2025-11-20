#!/usr/bin/env bash

# Base directory
BASE_DIR=".tmp"
# seeds directory to store target seeds (not used in counting)
PACKED_SEEDS_DIR="./packed_seeds"
mkdir -p "$PACKED_SEEDS_DIR"

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
    if [[ -n "$seeds_dirs" ]]; then
        project_packed_dir="$PACKED_SEEDS_DIR/$project_name"
        for dir in $seeds_dirs; do
            seed_files=("$dir"/seed_*)
            count=${#seed_files[@]}
            if (( count > 0 )); then
                mkdir -p "$project_packed_dir"
                cp "${seed_files[@]}" "$project_packed_dir/"
            fi
            total_count=$((total_count + count))
        done
    fi

    # Print result for this project
    echo "$project_name: $total_count"
done

shopt -u nullglob