#!/bin/sh
set -e
make allyesconfig
make -j `nproc` net/xfrm/xfrm_user.o include/uapi/linux/
