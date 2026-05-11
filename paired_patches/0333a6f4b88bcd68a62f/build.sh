#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/udf/file.o fs/udf/inode.o
