#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/vhost/vhost.o kernel/vhost_task.o drivers/vhost/ include/linux/sched/
