#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/nilfs2/btree.o
