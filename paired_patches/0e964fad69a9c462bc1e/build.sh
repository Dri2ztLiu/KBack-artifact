#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/wireless/mac80211_hwsim.o
