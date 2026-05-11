#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/wireless/ath/ath9k/hif_usb.o
