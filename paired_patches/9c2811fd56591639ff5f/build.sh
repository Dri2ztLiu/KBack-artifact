#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/ntfs3/fslog.o fs/ntfs3/index.o fs/ntfs3/
