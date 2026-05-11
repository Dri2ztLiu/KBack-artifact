#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/rxrpc/call_object.o net/rxrpc/sendmsg.o
