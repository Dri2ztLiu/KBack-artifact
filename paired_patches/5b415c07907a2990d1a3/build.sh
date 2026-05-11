#!/bin/sh
set -e
make allyesconfig
make -j `nproc` security/keys/keyring.o
