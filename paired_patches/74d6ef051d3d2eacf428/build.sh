#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/usb/usbip/vhci_hcd.o
