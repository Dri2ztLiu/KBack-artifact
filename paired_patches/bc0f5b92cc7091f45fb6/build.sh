#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/wireless/nl80211.o
