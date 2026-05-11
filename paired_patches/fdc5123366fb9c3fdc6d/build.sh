#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/mac80211/rate.o net/mac80211/scan.o net/mac80211/tx.o include/net/
