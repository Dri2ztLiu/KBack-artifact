#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/ocfs2/file.o fs/ocfs2/
