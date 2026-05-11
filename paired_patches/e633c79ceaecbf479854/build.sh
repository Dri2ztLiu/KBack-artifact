#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/quota/dquot.o
