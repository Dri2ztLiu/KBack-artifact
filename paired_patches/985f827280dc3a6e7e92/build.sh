#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/mac802154/iface.o
