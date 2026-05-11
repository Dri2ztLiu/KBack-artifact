#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/btrfs/ctree.o fs/btrfs/extent-tree.o fs/btrfs/free-space-tree.o fs/btrfs/ioctl.o fs/btrfs/qgroup.o fs/btrfs/
