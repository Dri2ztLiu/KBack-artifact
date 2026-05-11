#!/bin/sh
set -e
make allyesconfig
make -j `nproc` drivers/media/usb/gspca/gspca.o drivers/media/usb/gspca/stv06xx/stv06xx.o drivers/media/usb/gspca/
