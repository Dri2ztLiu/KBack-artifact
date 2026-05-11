#!/bin/sh
set -e
make allyesconfig
make -j `nproc` security/integrity/iint.o
