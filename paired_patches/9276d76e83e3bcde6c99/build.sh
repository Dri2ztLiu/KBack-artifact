#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/sctp/diag.o net/sctp/endpointola.o net/sctp/socket.o include/net/sctp/
