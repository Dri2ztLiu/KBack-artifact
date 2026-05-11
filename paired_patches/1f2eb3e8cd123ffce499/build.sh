#!/bin/sh
set -e
make allyesconfig
make -j `nproc` lib/zstd/common/fse_decompress.o
