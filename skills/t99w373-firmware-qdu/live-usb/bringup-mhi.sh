#!/bin/bash
set -e
DEV=0000:04:00.0
echo on > /sys/bus/pci/devices/$DEV/power/control
echo -1 > /sys/bus/pci/devices/$DEV/power/autosuspend_delay_ms 2>/dev/null || true
# parent bridge
for p in /sys/bus/pci/devices/$DEV/..; do
  [ -f "$p/power/control" ] && echo on > "$p/power/control"
done
modprobe mhi_pci_generic
sleep 1
echo on > /sys/bus/pci/devices/$DEV/power/control
modprobe mhi_wwan_ctrl || true
modprobe mhi_wwan_mbim || true
sleep 2
echo on > /sys/bus/pci/devices/$DEV/power/control
ls -la /dev/wwan* || true
mmcli -L || true
dmesg | grep -iE 'mhi|wwan' | tail -n 30
