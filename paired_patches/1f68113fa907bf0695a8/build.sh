#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/ieee802154/socket.o
