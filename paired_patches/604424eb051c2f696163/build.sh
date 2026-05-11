#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/squashfs/file.o fs/squashfs/file_direct.o
