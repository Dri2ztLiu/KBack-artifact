#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/hugetlbfs/inode.o
