#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/fs-writeback.o
