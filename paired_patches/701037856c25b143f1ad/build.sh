#!/bin/sh
set -e
make allyesconfig
make -j `nproc` fs/notify/fsnotify.o fs/notify/inotify/inotify_user.o fs/notify/mark.o
