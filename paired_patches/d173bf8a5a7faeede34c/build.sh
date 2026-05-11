#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/ocfs2/quota_global.o fs/ocfs2/quota_local.o
