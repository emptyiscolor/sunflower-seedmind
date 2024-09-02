#!/bin/bash

# Base directory to start the search
base_dir="oss-fuzz/build/corpus/seedgen"
log_file="/tmp/failed.log"

printf "" > "$log_file"

# Function to count the number of files in a directory recursively
count_files() {
    find "$1" -type f | wc -l
}

# Iterate over all directories under the base directory
for folder in "$base_dir"/*; do
    if [[ -d "$folder" ]]; then
        # Check if there are any *.json* files in the current folder
        json_files=$(find "$folder" -name "*.json*" -print -quit)
        if [[ -n "$json_files" ]]; then
            # Count the total number of files in the folder and its subfolders
            total_files=$(count_files "$folder")
            if (( total_files > 50 )); then
                # Print the folder name if conditions are met
                echo "$folder"
            else
                # Save the folder basename to the log file if conditions are not met
                basename "$folder" >> "$log_file"
            fi
        else
            # Save the folder basename to the log file if no JSON files are found
            basename "$folder" >> "$log_file"
        fi
    fi
done
