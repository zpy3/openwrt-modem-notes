# T99W373 QDU 升级参考

## 硬件 ID

| 项 | 值 |
|----|-----|
| 型号 | Foxconn T99W373 / Dell DW5932e |
| PCI vendor:device | `17cb:0308`（Qualcomm SDX62） |
| PCI subsystem | `105b:e0f5` |
| MBIM 口 | `/dev/wwan0mbim0` |
| AT 口 | `/dev/wwan0at0` |
| 驱动（Fedora Live） | `mhi-pci-generic`（需手动 bringup） |

MM 上报的 fwupd device-ids 形如：

```text
PCI\VID_17CB&PID_0308&REV_0000&CARRIER_CU
```

内置 quirk 大量是 `PCI\VID_105B&PID_E0F5`，与 MM 字符串对不上；再叠加 `UpdateMethod=0`，fwupd 直接跳过。

## LVFS

- 组件示例：`com.dell.t99w373.cu.firmware`
- 版本示例：`FDE.F0.3.0.1.1.CU.001.063`
- 协议：`com.qualcomm.mbim_qdu`
- cab 内：`Firmware_GC.zip` → `ota.bin` + `flashfile.xml`
- 同一 cab 含多运营商 metainfo（AT/CC/CU/DF/…），**刷的是同一份 ota**；运营商配置由模组/SIM 侧选择

启用测试源查元数据：

```sh
fwupdmgr enable-remote -y lvfs-testing
fwupdmgr refresh --force
```

## ModemManager 现象

```text
UpdateSettings = (uint32 0, { device-ids: [...], version: "FDE...\n050  - ..." })
```

`0` = `MM_MODEM_FIRMWARE_UPDATE_METHOD_NONE`。  
`mbimcli -p … --query-device-services` 仍可能列出 `qdu` UUID `6427015f-579d-48f5-8c54-f43ed1e76f83`。

插件常为 `generic` 而非 `foxconn`（因为 PCI VID 是 17cb）。`ID_MM_PLUGIN=foxconn` udev 实测无效。

## SIM

- `CME ERROR: 10` = 未插卡
- 插卡后仍 missing：`AT+CFUN=0` → `AT+CFUN=1` 再查 `CPIN`
- 升级前建议 `CPIN: READY`；本机实测无卡时 MM 进 `sim-missing` 失败态

## bringup-mhi.sh 最小逻辑

```sh
#!/bin/bash
DEV=0000:04:00.0   # 按 lspci 改
echo on > /sys/bus/pci/devices/$DEV/power/control
modprobe mhi
modprobe mhi_pci_generic
modprobe wwan
modprobe mhi_wwan_ctrl
modprobe mhi_wwan_mbim
sleep 2
echo on > /sys/bus/pci/devices/$DEV/power/control
ls -l /dev/wwan0*
```

## QDU 会话

1. `qdu_update_session_set_new(START, LE)`
2. `qdu_file_open_set_new(PACKAGE, size)` → 读 `out_max_transfer_size`
3. 循环 `qdu_file_write_set_new(chunk)`
4. `STOP`（可能因模组复位失败，以版本验证为准）

打开设备：`Mbim.DeviceOpenFlags.PROXY`，并先启动 `/usr/libexec/mbim-proxy`。

## 验证

成功后 `mmcli -m any`：

```text
firmware revision: FDE.F0.3.0.1.1.CU.001
                   063
carrier config: CU
```

## 升完回 OpenWrt

1. 关机，拔 Live U 盘，从内置盘进 OpenWrt
2. 确认 `soft_reboot=0` 仍在
3. 按 `t99w373-fcc-openwrt` 检查 MHI / CUSTOMER / 拨号
