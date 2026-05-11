#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/mptcp/protocol.o net/mptcp/subflow.o net/mptcp/
