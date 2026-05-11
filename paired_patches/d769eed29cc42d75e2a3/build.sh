#!/bin/sh
set -e
make allyesconfig
make -j `nproc` crypto/algapi.o include/crypto/
