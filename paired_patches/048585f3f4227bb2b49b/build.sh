#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/nilfs2/btree.o fs/nilfs2/direct.o
