#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/ext4/super.o fs/jbd2/journal.o include/linux/
