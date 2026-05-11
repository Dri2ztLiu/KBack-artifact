#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/wireless/ath/ar5523/ar5523.o
