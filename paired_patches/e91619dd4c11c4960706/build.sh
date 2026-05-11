#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/nilfs2/the_nilfs.o
