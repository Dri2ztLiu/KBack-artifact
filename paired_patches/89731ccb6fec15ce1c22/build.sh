#!/bin/sh
set -e
make allyesconfig
make -j `nproc` security/smack/smackfs.o
