#!/bin/bash

export PYTHONPATH=/workspaces/sunflower

MODEL="${SEEDGEN_GENERATIVE_MODEL:-gpt-4.1}"
PROJECTS=("poppler" "libpng" "libsndfile" "libtiff" "libxml2" "openssl" "sqlite3")
MAGMA_PATH="${MAGMA_PATH:-../magma}"

# generate mini fuzzing corpora for selected OSS-Fuzz targets
python infra/oss-fuzz.py --root oss-fuzz --model $MODEL --src_path /var/tmp/magma_targets/poppler --mini poppler pdf_fuzzer
python infra/oss-fuzz.py --root oss-fuzz --model $MODEL --src_path /var/tmp/magma_targets/libpng --mini libpng libpng_read_fuzzer
python infra/oss-fuzz.py --root oss-fuzz --model $MODEL --src_path /var/tmp/magma_targets/libsndfile --mini libsndfile sndfile_fuzzer
python infra/oss-fuzz.py --root oss-fuzz --model $MODEL --src_path /var/tmp/magma_targets/libtiff --mini libtiff tiff_read_rgba_fuzzer
python infra/oss-fuzz.py --root oss-fuzz --model $MODEL --src_path /var/tmp/magma_targets/libxml2 --mini libxml2 libxml2_xml_read_memory_fuzzer
python infra/oss-fuzz.py --root oss-fuzz --model $MODEL --src_path /var/tmp/magma_targets/openssl --mini openssl --all
python infra/oss-fuzz.py --root oss-fuzz --model $MODEL --src_path /var/tmp/magma_targets/sqlite --mini sqlite3 ossfuzz

echo "Mini fuzzing corpora generation completed."

# Exit if MAGMA_PATH does not exist
if [ ! -d "$MAGMA_PATH" ]; then
    echo "Error: MAGMA_PATH directory does not exist: $MAGMA_PATH"
    exit 1
fi
# clean magma corpus directory and copy mini corpora

function clean_corpus() {
    for project in "${PROJECTS[@]}"; do
        corpus_dir="$MAGMA_PATH/targets/$project/corpus"
        if [ -d "$corpus_dir" ]; then
            find "$corpus_dir" -type f -delete
            echo "Cleaned corpus directory: $corpus_dir"
        else
            echo "Corpus directory does not exist: $corpus_dir"
        fi
    done
}

clean_corpus

find .tmp/libpng -type f -name "seed_*" -exec cp {} $MAGMA_PATH/targets/libpng/corpus/libpng_read_fuzzer/ \;
find .tmp/libsndfile/*/sndfile_fuzzer/seeds -type f -name "*" -exec cp {} $MAGMA_PATH/targets/libsndfile/corpus/sndfile_fuzzer/ \;
find .tmp/libtiff/*/tiff_read_rgba_fuzzer/seeds -type f -name "seed_*" -exec cp {} $MAGMA_PATH/targets/libtiff/corpus/tiff_read_rgba_fuzzer/ \;
find .tmp/libxml2/*/libxml2_xml_read_memory_fuzzer/seeds -type f -name "seed_*" -exec cp {} $MAGMA_PATH/targets/libxml2/corpus/libxml2_xml_read_memory_fuzzer/ \;
find .tmp/openssl/*/driver/seeds -type f -name "seed_*" -exec cp {} $MAGMA_PATH/targets/openssl/corpus/asn1/ \;
find .tmp/openssl/*/driver/seeds -type f -name "seed_*" -exec cp {} $MAGMA_PATH/targets/openssl/corpus/asn1parse/ \;
find .tmp/openssl/*/driver/seeds -type f -name "seed_*" -exec cp {} $MAGMA_PATH/targets/openssl/corpus/bignum/ \;
find .tmp/openssl/*/driver/seeds -type f -name "seed_*" -exec cp {} $MAGMA_PATH/targets/openssl/corpus/bndiv/ \;
find .tmp/openssl/*/driver/seeds -type f -name "seed_*" -exec cp {} $MAGMA_PATH/targets/openssl/corpus/client/ \;
find .tmp/openssl/*/driver/seeds -type f -name "seed_*" -exec cp {} $MAGMA_PATH/targets/openssl/corpus/cms/ \;
find .tmp/openssl/*/driver/seeds -type f -name "seed_*" -exec cp {} $MAGMA_PATH/targets/openssl/corpus/conf/ \;
find .tmp/openssl/*/driver/seeds -type f -name "seed_*" -exec cp {} $MAGMA_PATH/targets/openssl/corpus/crl/ \;
find .tmp/openssl/*/driver/seeds -type f -name "seed_*" -exec cp {} $MAGMA_PATH/targets/openssl/corpus/ct/ \;
find .tmp/openssl/*/driver/seeds -type f -name "seed_*" -exec cp {} $MAGMA_PATH/targets/openssl/corpus/server/ \;
find .tmp/openssl/*/driver/seeds -type f -name "seed_*" -exec cp {} $MAGMA_PATH/targets/openssl/corpus/x509/ \;
find .tmp/poppler/*/pdf_fuzzer/seeds -type f -name "seed_*" -exec cp {} $MAGMA_PATH/targets/poppler/corpus/pdf_fuzzer/ \;
find .tmp/sqlite3/*/ossfuzz/seeds -type f -name "seed_*" -exec cp {} $MAGMA_PATH/targets/sqlite3/corpus/sqlite3_fuzz/ \;
echo "Mini fuzzing corpora copied to Magma corpus directories."