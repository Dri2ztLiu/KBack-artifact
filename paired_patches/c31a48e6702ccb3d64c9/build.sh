#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/reiserfs/stree.o
