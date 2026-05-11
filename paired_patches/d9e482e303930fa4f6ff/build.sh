#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/ext4/mmp.o fs/ext4/super.o fs/ext4/
