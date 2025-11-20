#!/bin/bash

export PYTHONPATH=/workspaces/sunflower

MODEL="${SEEDGEN_GENERATIVE_MODEL:-gpt-4.1}"

# read project list from file
PROJECTS_FILE="evaluation/ossfuzz/projects.txt"

# build projects
function build_projects() {
    while IFS= read -r project; do
        echo "Building project: $project"
        python infra/oss-fuzz.py --root oss-fuzz --model $MODEL "$project"
    done < "$PROJECTS_FILE"
}

function generate_mini_corpora() {
    project=$1
    src_path="/var/lib/docker/volumes/${project}_src_cache/_data/${project}/"
    if [ ! -d "$src_path" ]; then
        echo "Source path does not exist: $src_path"
        return
    fi

    echo "Generating mini corpus for project: $project"
    python infra/oss-fuzz.py --root oss-fuzz --model $MODEL --mini --src_path "$src_path" "$project" --all
}

function generate_full_corpora() {
    while IFS= read -r project; do
        echo "Generating full corpus for project: $project"
        python infra/oss-fuzz.py --root oss-fuzz --model $MODEL --all "$project"
    done < "$PROJECTS_FILE"
}

while IFS= read -r proj; do
    generate_mini_corpora "$proj"
done < "$PROJECTS_FILE"
