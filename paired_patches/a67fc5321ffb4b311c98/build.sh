#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/ecryptfs/inode.o fs/overlayfs/inode.o fs/stat.o fs/overlayfs/ include/uapi/linux/
