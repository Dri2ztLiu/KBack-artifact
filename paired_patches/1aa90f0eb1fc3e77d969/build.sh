#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/ntfs3/frecord.o fs/ntfs3/namei.o fs/ntfs3/
