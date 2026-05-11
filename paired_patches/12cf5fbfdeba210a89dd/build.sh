#!/bin/sh
set -e
make allyesconfig
make -j `nproc` crypto/api.o include/crypto/
