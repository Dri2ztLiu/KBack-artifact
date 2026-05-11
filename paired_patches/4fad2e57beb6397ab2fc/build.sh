#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/gpu/drm/drm_crtc.o
