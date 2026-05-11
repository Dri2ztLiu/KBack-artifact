#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/jfs/jfs_txnmgr.o
