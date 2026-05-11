#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/wireless/ath/ath6kl/htc_pipe.o
