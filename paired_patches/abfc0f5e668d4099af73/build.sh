#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/bluetooth/l2cap_sock.o
