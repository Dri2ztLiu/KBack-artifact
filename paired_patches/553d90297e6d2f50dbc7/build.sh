#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/jfs/jfs_imap.o
