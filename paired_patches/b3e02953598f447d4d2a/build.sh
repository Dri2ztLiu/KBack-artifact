#!/bin/sh
set -e
make allyesconfig
make -j `nproc` crypto/crypto_null.o
