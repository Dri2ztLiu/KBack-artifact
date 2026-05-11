#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/mac80211/main.o net/mac80211/util.o net/mac80211/
