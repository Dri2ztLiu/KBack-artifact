#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/exfat/dir.o
