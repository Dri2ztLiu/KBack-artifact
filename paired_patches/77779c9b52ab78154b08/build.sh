#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/quota/quota_v2.o
