#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/dvb-frontends/dib3000mb.o
