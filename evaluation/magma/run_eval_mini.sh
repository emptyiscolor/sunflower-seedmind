#!/bin/bash

export PYTHONPATH=/workspaces/sunflower

MODEL="${SEEDGEN_GENERATIVE_MODEL:-gpt-4.1}"

python infra/oss-fuzz.py --root oss-fuzz --model $MODEL --src_path /var/tmp/magma_targets/poppler --mini poppler pdf_fuzzer
python infra/oss-fuzz.py --root oss-fuzz --model $MODEL --src_path /var/tmp/magma_targets/libpng --mini libpng libpng_read_fuzzer
python infra/oss-fuzz.py --root oss-fuzz --model $MODEL --src_path /var/tmp/magma_targets/libsndfile --mini libsndfile sndfile_fuzzer
python infra/oss-fuzz.py --root oss-fuzz --model $MODEL --src_path /var/tmp/magma_targets/libtiff --mini libtiff tiff_read_rgba_fuzzer
python infra/oss-fuzz.py --root oss-fuzz --model $MODEL --src_path /var/tmp/magma_targets/libxml2 --mini libxml2 libxml2_xml_read_memory_fuzzer
python infra/oss-fuzz.py --root oss-fuzz --model $MODEL --src_path /var/tmp/magma_targets/openssl --mini openssl --all
python infra/oss-fuzz.py --root oss-fuzz --model $MODEL --src_path /var/tmp/magma_targets/sqlite --mini sqlite3 ossfuzz
