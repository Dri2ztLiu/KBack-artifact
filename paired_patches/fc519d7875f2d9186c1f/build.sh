#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/orangefs/orangefs-debugfs.o
