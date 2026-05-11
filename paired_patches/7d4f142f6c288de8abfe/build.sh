#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/wireless/purelifi/plfxlc/mac.o
