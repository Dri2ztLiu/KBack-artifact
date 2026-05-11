#!/bin/sh
set -e
make allyesconfig
make -j `nproc` security/landlock/fs.o
