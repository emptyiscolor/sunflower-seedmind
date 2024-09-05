#!/bin/bash

CSV_HARNESS_FILE="/workspaces/SeedGen/data/filtered_harness.csv"
CSV_INPUT_FILE="/workspaces/SeedGen/data/input_full_harnesses.csv"
OSSFUZZ_DIR="/workspaces/SeedGen/oss-fuzz"
COV_CSV_FILE="/tmp/oss-fuzz_seedgen_cov.csv"
TMP_SEEDS_PATH="/tmp/tmp_seeds/merged"
SIZE_LIMIT=$((80 * 1024 * 1024 * 1024))

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

  echo > "$COV_CSV_FILE"

  while IFS= read -r line; do
    # Split the line into fields using ':' as the delimiter
    IFS=',' read -r -a fields <<< "$line"

    # Extract project_name and source_code_file
    project_name="${fields[0]}"
    binary_name="${fields[1]}"
    source_code_file_with_info="${fields[2]}"

    # Remove the line number and column number from source_code_file
    source_code_file="${source_code_file_with_info%:*:*}"

    # echo "Project Name: $project_name, Binary Name: $binary_name, Source Code File: $source_code_file"
    summary_path="$OSSFUZZ_DIR/build/cov_report/seedgen/$project_name/report_target/$binary_name/linux/summary.json"

    if [ -d "$OSSFUZZ_DIR/build/corpus/seedgen/$project_name" ] && [ -f "$OSSFUZZ_DIR/build/corpus/seedgen/$project_name/$binary_name.json" ] && [ -f "$summary_path" ] ; then
      # echo "Geting code coverage: $project_name, $binary_name"
      cov=$(jq .data[].totals.lines.percent < "$summary_path")
    else
      # echo "No coverage report found for $project_name, $binary_name"
      cov="NA"
    fi

    echo "$project_name,$binary_name,$cov" | tee -a $COV_CSV_FILE

  done < "$CSV_HARNESS_FILE"

  popd
}

function generate_cov() {
  pushd $OSSFUZZ_DIR
  mkdir -p $TMP_SEEDS_PATH
  # python infra/helper.py coverage --fuzz-target=$binary_name --corpus-dir=$corpus_dir $project --no-serve
  while IFS= read -r line; do
    # Split the line into fields using ':' as the delimiter
    IFS=',' read -r -a fields <<< "$line"

    # Extract project_name and source_code_file
    project_name="${fields[0]}"
    lang="${fields[1]}"
    binary_name="${fields[2]}"

    # Check if the directory size exceeds the limit

    while true; do
      dir_size=$(du -sb "$TMP_SEEDS_PATH" | cut -f1)
      if (( dir_size > SIZE_LIMIT )); then
        echo "Warning: The size of $TMP_SEEDS_PATH has exceeded 80GB. Please wait until previous cov finished"
        sleep 10
      else
        echo "The size of $TMP_SEEDS_PATH is within the limit."
        break
      fi
    done

    echo "Project Name: $project_name, Binary Name: $binary_name, lang: $lang"

    if [ -d "$OSSFUZZ_DIR/build/corpus/seedgen/$project_name" ] ; then
      echo "Generating code coverage: $project_name: find $OSSFUZZ_DIR/build/corpus/seedgen/$project_name/ -depth -maxdepth 1 -name '*.json' "
      #   python infra/helper.py build_fuzzers --sanitizer=coverage $project_name
        # pushd $TMP_SEEDS_PATH && mkdir $binary_name && popd && \
      ls "$OSSFUZZ_DIR/build/corpus/seedgen/$project_name/"*.json 2>/dev/null && \
        mkdir -p $TMP_SEEDS_PATH/$project_name && \
        echo "bash -c for jsonfile in \`ls "$OSSFUZZ_DIR/build/corpus/seedgen/$project_name/"*.json\` ; do bin=\$(basename \$jsonfile | sed 's/\.json$//') ; cp -r "$OSSFUZZ_DIR/build/corpus/seedgen/$project_name" ${TMP_SEEDS_PATH}/${project_name}/\$bin; done" && \
        echo "sleeping for 12s and copy the seeds" && \
        sleep 12 && \
        bash -c "for jsonfile in \`ls "$OSSFUZZ_DIR/build/corpus/seedgen/$project_name/"*.json\` ; do bin=\$(basename \$jsonfile | sed 's/\.json$//') ; cp -r "$OSSFUZZ_DIR/build/corpus/seedgen/$project_name" ${TMP_SEEDS_PATH}/${project_name}/\$bin; done" && \
        echo "** collecting cov $project_name **" && \
        bash -c "timeout 30m docker run --privileged --shm-size=2g --platform linux/amd64 --rm -e FUZZING_ENGINE=libfuzzer -e HELPER=True -e FUZZING_LANGUAGE=$lang -e PROJECT=$project_name -e SANITIZER=coverage -e 'COVERAGE_EXTRA_ARGS= ' -e ARCHITECTURE=x86_64 -v "${TMP_SEEDS_PATH}/${project_name}":"/corpus" -v $OSSFUZZ_DIR/build/out/$project_name:/out -t gcr.io/oss-fuzz-base/base-runner coverage ${binary_name} ; rm -rf ${TMP_SEEDS_PATH}/${project_name} " & 

      sleep 1
      echo "==== NEXT. ====" 
      # mkdir -p $OSSFUZZ_DIR/build/cov_report/seedgen/$project_name
      # cp -rf $OSSFUZZ_DIR/build/out/$project_name/report_target $OSSFUZZ_DIR/build/cov_report/seedgen/$project_name/
    fi

# FIXME: use input_full.csv
  done < "$CSV_INPUT_FILE"
  popd
  wait < <(jobs -p)
}

# 1. build targets
pre_build_project
# 2. collect coverage
generate_cov
# 3. save the output to a csv
count_seedgen_cov
