#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/nfc/nci/data.o
