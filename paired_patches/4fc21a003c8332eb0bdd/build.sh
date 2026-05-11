#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/gpu/drm/vkms/vkms_crtc.o
