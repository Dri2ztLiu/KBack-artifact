#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/staging/rtl8712/rtl871x_xmit.o drivers/staging/rtl8712/xmit_linux.o
