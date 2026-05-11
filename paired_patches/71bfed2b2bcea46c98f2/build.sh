#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/nfc/virtual_ncidev.o
