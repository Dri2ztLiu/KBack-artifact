#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/nilfs2/dir.o
