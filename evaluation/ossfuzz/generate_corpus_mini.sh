#!/bin/bash

export PYTHONPATH=/workspaces/sunflower

MODEL="${SEEDGEN_GENERATIVE_MODEL:-gpt-4.1}"

# read project list from file
PROJECTS_FILE="evaluation/ossfuzz/projects.txt"

# build projects
function build_projects() {
    while IFS= read -r project; do
        echo "Building project: $project"
        python infra/oss-fuzz.py --root oss-fuzz --model $MODEL "$project" --all
    done < "$PROJECTS_FILE"
}

function collect_all_seeds_tmp() {
    local tmp_dir=".tmp"
    local seeds_agg_dir="./seeds_agg"
    
    # Create seeds_agg directory if it doesn't exist
    mkdir -p "$seeds_agg_dir"
    
    # Iterate through project directories in .tmp/, excluding cache
    for project_dir in "$tmp_dir"/*; do
        # Skip if not a directory or if it's the cache directory
        if [[ ! -d "$project_dir" ]] || [[ "$(basename "$project_dir")" == "cache" ]]; then
            continue
        fi
        
        local project_name=$(basename "$project_dir")
        
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
        done < <(find "$project_dir" -type d -name "seeds")
    done
}

collect_all_seeds_tmp