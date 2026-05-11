#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/mac80211/debugfs_netdev.o
