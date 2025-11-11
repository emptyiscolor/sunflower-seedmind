#!/bin/bash

# Fetch the source code for Magma targets.
set -e

TARGET_SRC_DIR="/var/tmp/magma_targets"

function fetch_libpng() {
    echo "[*] Fetching libpng source code..."
    git clone --no-checkout https://github.com/glennrp/libpng.git $TARGET_SRC_DIR/libpng
    git -C $TARGET_SRC_DIR/libpng checkout a37d4836519517bdce6cb9d956092321eca3e73b
}

function fetch_libsndfile() {
    echo "[*] Fetching libsndfile source code..."
    git clone --no-checkout https://github.com/libsndfile/libsndfile.git $TARGET_SRC_DIR/libsndfile
    git -C $TARGET_SRC_DIR/libsndfile checkout 86c9f9eb7022d186ad4d0689487e7d4f04ce2b29
}

function fetch_libtiff() {
    echo "[*] Fetching libtiff source code..."
    git clone --no-checkout https://gitlab.com/libtiff/libtiff.git $TARGET_SRC_DIR/libtiff
    git -C $TARGET_SRC_DIR/libtiff checkout c145a6c14978f73bb484c955eb9f84203efcb12e
    echo "// harness code" > $TARGET_SRC_DIR/libtiff/contrib/oss-fuzz/tiff_read_rgba_fuzzer.cc
    cat <<EOF >> $TARGET_SRC_DIR/libtiff/contrib/oss-fuzz/tiff_read_rgba_fuzzer.cc
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <sstream>
#include <tiffio.h>
#include <tiffio.hxx>


/* stolen from tiffiop.h, which is a private header so we can't just include it */
/* safe multiply returns either the multiplied value or 0 if it overflowed */
#define __TIFFSafeMultiply(t,v,m) ((((t)(m) != (t)0) && (((t)(((v)*(m))/(m))) == (t)(v))) ? (t)((v)*(m)) : (t)0)

const uint64 MAX_SIZE = 500000000;

extern "C" void handle_error(const char *unused, const char *unused2, va_list unused3) {
    return;
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *Data, size_t Size) {
#ifndef STANDALONE
  TIFFSetErrorHandler(handle_error);
  TIFFSetWarningHandler(handle_error);
#endif
#if defined(__has_feature)
#  if __has_feature(memory_sanitizer)
  // libjpeg-turbo has issues with MSAN and SIMD code
  // See https://bugs.chromium.org/p/oss-fuzz/issues/detail?id=7547
  // and https://github.com/libjpeg-turbo/libjpeg-turbo/pull/365
  setenv("JSIMD_FORCENONE" ,"1", 1);
#  endif
#endif
  std::istringstream s(std::string(Data,Data+Size));
  TIFF* tif = TIFFStreamOpen("MemTIFF", &s);
  if (!tif) {
      return 0;
  }
  uint32 w, h;
  uint32* raster;

  TIFFGetField(tif, TIFFTAG_IMAGEWIDTH, &w);
  TIFFGetField(tif, TIFFTAG_IMAGELENGTH, &h);
  /* don't continue if file size is ludicrous */
  if (TIFFTileSize64(tif) > MAX_SIZE) {
      TIFFClose(tif);
      return 0;
  }
  uint64 bufsize = TIFFTileSize64(tif);
  /* don't continue if the buffer size greater than the max allowed by the fuzzer */
  if (bufsize > MAX_SIZE || bufsize == 0) {
      TIFFClose(tif);
      return 0;
  }
  /* another hack to work around an OOM in tif_fax3.c */
  uint32 tilewidth = 0, tilewidth2;
  uint32 imagewidth = 0;
  TIFFGetField(tif, TIFFTAG_TILEWIDTH, &tilewidth);
  TIFFGetField(tif, TIFFTAG_IMAGEWIDTH, &imagewidth);
  tilewidth2 = __TIFFSafeMultiply(uint32, tilewidth, 2);
  imagewidth = __TIFFSafeMultiply(uint32, imagewidth, 2);
  if (tilewidth2 * 2 > MAX_SIZE || imagewidth * 2 > MAX_SIZE || (tilewidth != 0 && tilewidth2 == 0) || imagewidth == 0) {
      TIFFClose(tif);
      return 0;
  }
  uint32 size = __TIFFSafeMultiply(uint32, w, h);
  if (size > MAX_SIZE || size == 0) {
      TIFFClose(tif);
      return 0;
  }
  raster = (uint32*) _TIFFmalloc(size * sizeof (uint32));
  if (raster != NULL) {
      TIFFReadRGBAImage(tif, w, h, raster, 0);
      _TIFFfree(raster);
  }
  TIFFClose(tif);

  return 0;
}
EOF
    echo "tiff_read_rgba_fuzzer.cc created."
}

function fetch_libxml2() {
    echo "[*] Fetching libxml2 source code..."
    git clone --no-checkout https://gitlab.gnome.org/GNOME/libxml2.git $TARGET_SRC_DIR/libxml2
    git -C $TARGET_SRC_DIR/libxml2 checkout ec6e3efb06d7b15cf5a2328fabd3845acea4c815
    echo "// harness code" > $TARGET_SRC_DIR/libxml2/fuzz/libxml2_xml_read_memory_fuzzer.cc
    cat <<EOF >> $TARGET_SRC_DIR/libxml2/fuzz/libxml2_xml_read_memory_fuzzer.cc
// found in the LICENSE file.

#include <cassert>
#include <cstddef>
#include <cstdint>

#include <functional>
#include <limits>
#include <string>

#include "libxml/parser.h"
#include "libxml/xmlsave.h"

void ignore (void* ctx, const char* msg, ...) {
  // Error handler to avoid spam of error messages from libxml parser.
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  xmlSetGenericErrorFunc(NULL, &ignore);

  // Test default empty options value and some random combination.
  std::string data_string(reinterpret_cast<const char*>(data), size);
  const std::size_t data_hash = std::hash<std::string>()(data_string);
  const int max_option_value = std::numeric_limits<int>::max();
  int random_option_value = data_hash % max_option_value;

  // Disable XML_PARSE_HUGE to avoid stack overflow.
  random_option_value &= ~XML_PARSE_HUGE;
  const int options[] = {0, random_option_value};

  for (const auto option_value : options) {
    // Intentionally pass raw data as the API does not require trailing \0.
    if (auto doc = xmlReadMemory(reinterpret_cast<const char*>(data), size,
                                 "noname.xml", NULL, option_value)) {
      auto buf = xmlBufferCreate();
      assert(buf);
      auto ctxt = xmlSaveToBuffer(buf, NULL, 0);
      xmlSaveDoc(ctxt, doc);
      xmlSaveClose(ctxt);
      xmlFreeDoc(doc);
      xmlBufferFree(buf);
    }
  }

  return 0;
}
EOF
    echo "libxml2_xml_read_memory_fuzzer.cc created."
}

function fetch_openssl() {
    echo "[*] Fetching OpenSSL source code..."
    git clone --no-checkout https://github.com/openssl/openssl.git $TARGET_SRC_DIR/openssl
    git -C $TARGET_SRC_DIR/openssl checkout 3bd5319b5d0df9ecf05c8baba2c401ad8e3ba130
}

function fetch_poppler() {
    echo "[*] Fetching Poppler source code..."
    git clone --no-checkout https://gitlab.freedesktop.org/poppler/poppler.git $TARGET_SRC_DIR/poppler
    git -C $TARGET_SRC_DIR/poppler checkout 1d23101ccebe14261c6afc024ea14f29d209e760

    echo "// harness code" > $TARGET_SRC_DIR/poppler/pdf_fuzzer.cc
    cat <<EOF >> $TARGET_SRC_DIR/poppler/pdf_fuzzer.cc
#include <cstdint>

#include <poppler-global.h>
#include <poppler-document.h>
#include <poppler-page.h>
#include <poppler-page-renderer.h>

static void nop_func(const std::string& msg, void*) {};

extern "C" int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size) {
  poppler::set_debug_error_function(nop_func, nullptr);

  poppler::document *doc = poppler::document::load_from_raw_data((const char *)data, size);
  if (!doc || doc->is_locked()) {
    delete doc;
    return 0;
  }

  poppler::page_renderer r;
  for (int i = 0; i < doc->pages(); i++) {
    poppler::page *p = doc->create_page(i);
    if (!p) {
      continue;
    }
    r.render_page(p);
    p->text_list();
    delete p;
  }

  delete doc;
  return 0;
}
EOF
    echo "pdf_fuzzer.cc created."

    # freetype2 is a dependency of poppler
    git clone --no-checkout https://gitlab.freedesktop.org/freetype/freetype.git $TARGET_SRC_DIR/freetype2
    git -C $TARGET_SRC_DIR/freetype2 checkout 50d0033f7ee600c5f5831b28877353769d1f7d48
}

function fetch_sqlite() {
    echo "[*] Fetching SQLite source code..."
    curl "https://www.sqlite.org/src/tarball/sqlite.tar.gz?r=8c432642572c8c4b" -o /tmp/sqlite.tar.gz && \
        mkdir -p $TARGET_SRC_DIR/sqlite && \
        tar -C $TARGET_SRC_DIR/sqlite --strip-components=1 -xzf /tmp/sqlite.tar.gz
    rm /tmp/sqlite.tar.gz
}

function fetch_all() {
    fetch_libpng
    fetch_libsndfile
    fetch_libtiff
    fetch_libxml2
    fetch_openssl
    fetch_poppler
    fetch_sqlite
    echo "[*] All source code fetched."
}

mkdir -p $TARGET_SRC_DIR
pushd $TARGET_SRC_DIR

fetch_all

popd