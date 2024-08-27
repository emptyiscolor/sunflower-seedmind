#!/bin/bash

CSV_HARNESS_FILE="/workspaces/SeedGen/filtered_harness.csv"
OSSFUZZ_DIR="/workspaces/SeedGen/oss-fuzz"
COV_CSV_FILE="/tmp/oss-fuzz_seedgen_cov.csv"

function pre_build_project() {
    pushd $OSSFUZZ_DIR
    for project in $(cat $CSV_HARNESS_FILE | cut -d, -f1 | sort -u); do
        python infra/helper.py build_image --no-pull $project
        python infra/helper.py build_fuzzers --sanitizer=coverage $project
    done
    popd
}

function count_seedgen_cov() {
  pushd $OSSFUZZ_DIR
  find build/cov_report/seedgen -name summary.json | grep report_target | while read -r summary_path; do
      binary_name=$(basename "$(dirname "$(dirname "$summary_path")")")
      project=$(basename "$(dirname "$(dirname "$(dirname "$(dirname "$summary_path")")")")")
      cov=$(jq .data[].totals.lines.percent < "$summary_path")
      printf "$project\t$binary_name\t$cov\n" | tee -a $COV_CSV_FILE
  done

  popd
}

function generate_cov() {
  # python infra/helper.py coverage --fuzz-target=$binary_name --corpus-dir=$corpus_dir $project --no-serve
  while IFS= read -r line; do
    # Split the line into fields using ':' as the delimiter
    IFS=',' read -r -a fields <<< "$line"

    # Extract project_name and source_code_file
    project_name="${fields[0]}"
    binary_name="${fields[1]}"
    source_code_file_with_info="${fields[2]}"

    # Remove the line number and column number from source_code_file
    source_code_file="${source_code_file_with_info%:*:*}"

    echo "Project Name: $project_name, Binary Name: $binary_name, Source Code File: $source_code_file"

    if [ -d "$OSSFUZZ_DIR/build/corpus/seedgen/$project_name" ] ; then
      echo "Generating code coverage: $project_name"
    #   python infra/helper.py build_fuzzers --sanitizer=coverage $project_name
      timeout 20m python infra/helper.py coverage --fuzz-target=$binary_name --corpus-dir="$OSSFUZZ_DIR/build/corpus/seedgen/$project_name" --no-serve $project_name 
      if [ $? -eq 124 ]; then
        echo "Timeout reached. Running another command..."
        docker stop $(docker ps -q)
      fi
      mkdir -p $OSSFUZZ_DIR/build/cov_report/seedgen/$project_name
      cp -rf $OSSFUZZ_DIR/build/out/$project_name/report_target $OSSFUZZ_DIR/build/cov_report/seedgen/$project_name/
    fi

  done < "$CSV_HARNESS_FILE"
}

# 1. build targets
pre_build_project
# 2. collect coverage
generate_cov
# 3. save the output to a csv
count_seedgen_cov
