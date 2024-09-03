#!/bin/bash

TO_GENERATED_FILE="./data/input_sample_4.csv"
TIMEOUT=30

function clean_old_containers() {
    # Stop Docker containers running for more than 4 hours
    echo "Stopping Docker containers running for more than 4 hours..."
    containers=$(docker ps --format '{{.ID}} {{.RunningFor}}' | grep -E '([0-9]+) (hours|days|weeks|months|years)' | while read -r id time; do
        hours=$(echo $time | grep -oE '^[0-9]+')
        unit=$(echo $time | grep -oE '(hours|days|weeks|months|years)')
        if [ "$unit" == "hours" ] && [ "$hours" -gt 3 ]; then
            echo $id
        elif [ "$unit" != "hours" ]; then
            echo $id
        fi
    done)

    for container in $containers; do
        docker stop $container
    done

    # Delete folders under ./tmp older than 4 hours (depth 1)
    echo "Deleting folders under ./tmp older than 4 hours..."
    find ./.tmp -mindepth 1 -maxdepth 1 -type d -mmin +240 -exec rm -rf {} \;

    echo "Cleanup completed."
}


while IFS= read -r harness; do
    IFS=',' read -r -a fields <<< "$harness"
    # IFS=$'\t' read -r -a fields <<< "$harness"
    project_name="${fields[0]}"
    lang="${fields[1]}"
    binary_name="${fields[2]}"
    echo $fields
    mkdir -p /tmp/logs/$project_name
    # timeout $TIMEOUT echo python oss-fuzz.py $project_name $binary_name 2>&1 
    time_needed=$(echo $(( $TIMEOUT * $(echo $binary_name | wc -w))))
    echo "Recaculate the timeout: $time_needed"
    echo "RUN: python oss-fuzz.py --level 5 --budget 0.5 $project_name $binary_name"
    # for binary in ${binary_name}; do
    # timeout "${TIMEOUT}m"  python oss-fuzz.py --level 5 --budget 0.5 $project_name $binary >/tmp/logs/$project_name/batch_run.log 2>&1 &
    python oss-fuzz.py --level 5 --budget 0.5 $project_name $binary_name >/tmp/logs/$project_name/batch_run.log 2>&1 &
    # done
    # Capture the exit code of the `timeout` command
    exit_code=$?

    # if [ $? -eq 124 ]; then
    #     echo "Timeout reached. Running another command..."
    #     docker stop $(docker ps -q)
    # elif [ $exit_code -eq 137 ]; then
    #     echo "Process was killed. exiting..."
    #     docker stop $(docker ps -q)
    if [ $exit_code -ne 0 ]; then
        echo "Python script exited unexpectedly with code $exit_code."
        echo "$project_name $binary_name" >> /tmp/seed_genexceptions.txt
        docker stop $(docker ps -q)
        exit 1
    else
        echo "Seedgen for $project_name , $binary_name started."
    fi

    sleep 300

    # sudo rm -rf .tmp/*

    # remove large seeds
    find  oss-fuzz/build/corpus/seedgen -type f -size +2M -delete

done < "$TO_GENERATED_FILE"

wait < <(jobs -p)