#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/nfsd/nfsctl.o
