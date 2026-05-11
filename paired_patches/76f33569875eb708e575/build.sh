#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/afs/addr_prefs.o
