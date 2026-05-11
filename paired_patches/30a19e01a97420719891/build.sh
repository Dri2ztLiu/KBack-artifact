#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/core/sock.o net/mptcp/subflow.o net/netlink/af_netlink.o net/rds/tcp.o net/smc/af_smc.o net/sunrpc/svcsock.o net/sunrpc/xprtsock.o include/net/
