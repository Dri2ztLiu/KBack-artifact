#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/wireless/virtual/mac80211_hwsim.o
