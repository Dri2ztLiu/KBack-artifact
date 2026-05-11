#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/nfc/port100.o
