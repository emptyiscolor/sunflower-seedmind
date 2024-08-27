#!/bin/bash

TO_GENERATED_FILE="./input.csv"
TIMEOUT=30m

for harness in $(cat $TO_GENERATED_FILE); do
    IFS=',' read -r -a fields <<< "$harness"
    # IFS=$'\t' read -r -a fields <<< "$harness"
    project_name="${fields[0]}"
    lang="${fields[1]}"
    binary_name="${fields[2]}"
    mkdir -p /tmp/logs/$project_name
    timeout $TIMEOUT python oss-fuzz.py $project_name $binary_name 2>&1 | tee /tmp/logs/$project_name/batch_run.log
    if [ $? -eq 124 ]; then
        echo "Timeout reached. Running another command..."
        docker stop $(docker ps -q)
    fi
    token_used=$(cat /tmp/logs/$project_name/batch_run.log | grep 'Tokens Used' | cut -d':' -f2)
    prompt_tokens=$(cat /tmp/logs/$project_name/batch_run.log | grep 'Prompt Tokens' | cut -d':' -f2)
    complete_tokens=$(cat /tmp/logs/$project_name/batch_run.log | grep 'Completion Tokens' | cut -d':' -f2)
    total_cost=$(cat /tmp/logs/$project_name/batch_run.log | grep 'Total Cost' | cut -d':' -f2 | tr -d '$')
    find /tmp -depth -maxdepth 1 -type d | grep -E '[a-fA-F0-9]{8}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{4}-[a-fA-F0-9]{12}' | grep -v devcontain | xargs -I {} sudo rm -rf {} 
    echo "$project_name,$binary_name,$token_used,$prompt_tokens,$complete_tokens,$total_cost" >> /tmp/seedgen_metrics.csv
done
