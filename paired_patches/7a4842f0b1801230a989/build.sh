#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/udf/directory.o fs/udf/inode.o fs/udf/partition.o fs/udf/truncate.o fs/udf/
