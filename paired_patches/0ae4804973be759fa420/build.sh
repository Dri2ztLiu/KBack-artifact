#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/wireless/ath/carl9170/usb.o
