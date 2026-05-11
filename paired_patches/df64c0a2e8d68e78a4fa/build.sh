#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/nfc/st-nci/se.o drivers/nfc/st21nfca/se.o net/nfc/netlink.o
