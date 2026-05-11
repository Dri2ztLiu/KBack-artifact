#!/bin/sh
set -e
make allyesconfig
make -j `nproc` mm/hugetlb.o
