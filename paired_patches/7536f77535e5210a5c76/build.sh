#!/bin/sh
set -e
make allyesconfig
make -j `nproc` security/tomoyo/common.o
