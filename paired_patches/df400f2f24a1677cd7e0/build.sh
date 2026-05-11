#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/afs/main.o net/rxrpc/af_rxrpc.o
