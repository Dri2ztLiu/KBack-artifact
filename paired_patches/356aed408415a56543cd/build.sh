#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/hfsplus/bnode.o fs/hfsplus/btree.o fs/hfsplus/
