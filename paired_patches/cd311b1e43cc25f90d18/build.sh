#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/udf/unicode.o
