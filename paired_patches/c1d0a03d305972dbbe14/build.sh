#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/nfc/llcp_core.o
