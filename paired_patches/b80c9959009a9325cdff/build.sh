#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/net/ieee802154/mac802154_hwsim.o
