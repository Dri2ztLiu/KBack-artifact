#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/rxrpc/sendmsg.o
