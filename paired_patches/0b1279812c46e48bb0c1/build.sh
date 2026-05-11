#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/erofs/data.o fs/erofs/
