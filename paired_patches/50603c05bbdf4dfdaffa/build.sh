#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/core/sock.o net/mptcp/protocol.o net/netlink/diag.o include/net/
