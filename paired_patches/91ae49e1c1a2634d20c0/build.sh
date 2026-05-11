#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/exfat/file.o
