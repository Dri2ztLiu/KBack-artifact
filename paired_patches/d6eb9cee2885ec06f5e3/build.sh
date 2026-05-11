#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/wireless/virtual/virt_wifi.o
