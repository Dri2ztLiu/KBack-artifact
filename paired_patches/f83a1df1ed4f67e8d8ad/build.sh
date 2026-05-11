#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/wireless/ath/ath9k/htc_hst.o
