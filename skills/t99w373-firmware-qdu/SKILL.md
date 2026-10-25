---
name: t99w373-firmware-qdu
description: >-
  Upgrade Foxconn/Dell T99W373 (DW5932e, PCI 17cb:0308 / subsystem 105b:e0f5)
  modem firmware via Fedora Live + MBIM QDU (LVFS CU.001.050→.063). Use when
  T99W373, DW5932e, fwupd, MBIM QDU, CU.001, FDE.F0.3.0.1.1, LVFS cab, or
  OpenWrt cannot run fwupd for this modem.
---

# T99W373 固件升级（Fedora Live + MBIM QDU）

OpenWrt **没有**可用的 fwupd/MBIM-QDU 路径。在路由器上用 **Fedora Live USB** 升固件，升完再退回 OpenWrt。

目标示例：`FDE.F0.3.0.1.1.CU.001` **050 → 063**（中国联通 CU）。

## 免责与注意

- QDU 刷机有变砖风险，操作前自行备份认知、后果自负
- **不要**把 `.cab` / `ota.bin` 提交进 git，只保留 LVFS 链接
- 不要用错运营商分支的认知去选错包（本机 carrier 是 CU 就按 CU 验证）
- OpenWrt 上通常装不了/用不了 fwupd，不要在路由里硬上

## 前置（OpenWrt）

1. qmodem/模组侧已 `soft_reboot=0`（避免 MHI `SYS_ERR` 循环）
2. 准备可启动的 **Fedora Workstation Live** U 盘（GPT）
3. Live grub 追加内核参数，并放入 bringup 脚本（见下方）

## Live 启动参数（必加）

```text
pcie_aspm=off pcie_port_pm=off modprobe.blacklist=mhi_pci_generic,mhi_wwan_mbim,mhi_wwan_ctrl
```

原因：默认会进 D3cold，MHI 起不来。黑名单后由 `bringup-mhi.sh` **手动**按顺序加载，并强制：

```sh
echo on > /sys/bus/pci/devices/0000:04:00.0/power/control
```

（BDF 以现场 `lspci` 为准。）

## 为何 fwupd 经常「看不见」模组

| 事实 | 后果 |
|------|------|
| PCI `vendor:device` = `17cb:0308`，`subsystem` = `105b:e0f5` | fwupd quirk 多匹配 `105B:E0F5`，MM 报的 device-ids 却是 `PCI\VID_17CB&PID_0308&…&CARRIER_CU` |
| MM `UpdateSettings` 方法位 = **0（NONE）** | 即使设备上有 QDU 服务，`fwupdmgr` / `fwupdtool --plugins modem_manager` 仍 **No detected devices** |
| 无 SIM / 未识别 | MM `failed reason: sim-missing`，更别提升级 |

**结论：不要死磕 fwupd UI。** 用 **mbim-proxy + libmbim QDU** 直刷（本 skill 的脚本）。

`mbimcli -p -d /dev/wwan0mbim0 --query-device-services` 应能看到 `Service: 'qdu'`。

## 流程清单

```
Task Progress:
- [ ] 1. Fedora Live 启动 + bringup MHI + power/control=on
- [ ] 2. SSH（示例 liveuser）；确认 /dev/wwan0mbim0 / wwan0at0
- [ ] 3. 插 SIM；必要时 AT+CFUN=0→1 后 CPIN=READY
- [ ] 4. 下载 LVFS cab（lvfs-testing），解出 ota.bin
- [ ] 5. 停 ModemManager，起 mbim-proxy，跑 QDU 脚本
- [ ] 6. 验证版本行出现 063（或目标版本）；再退回 OpenWrt
```

### 1–2. Bringup 与确认

```sh
bash /run/initramfs/live/bringup-mhi.sh   # 或现场路径
echo on > /sys/bus/pci/devices/0000:04:00.0/power/control
# 升级全程后台循环写 on，防止 D3cold
lspci -nnk -s 04:00.0
ls -l /dev/wwan0*
```

期望：`ATI` → `Model: T99W373`，`AT+GMR` → `FDE.F0.3.0.1.1.CU.001`。

### 3. SIM

若 `AT+CPIN?` → `CME ERROR: 10` 或 MM `sim-missing`：

```text
AT+CFUN=0
AT+CFUN=1
AT+CPIN?    # READY
```

双卡槽显示 none 时，先物理重插再 CFUN 循环。

### 4. 固件包（CU.063 示例）

包在 **lvfs-testing**（稳定 lvfs 元数据里可能没有）：

```text
https://fwupd.org/downloads/567500d81dad5d804d78b1f3aa38af2b425ae9534a1115cdae6f964fb44af616-20240617-dell-T99W373.FDE.F0.3.0.1.1.063.cab
```

```sh
fwupdmgr enable-remote -y lvfs-testing   # 可选，仅查元数据
mkdir -p /tmp/t99fw && cd /tmp/t99fw
curl -fL -o fw.cab '<上述 URL>'
cabextract fw.cab
unzip -o Firmware_GC.zip -d fwout
# 得到 fwout/ota.bin（约 149MB）
```

`T99W373.CU.metainfo.xml` / protocol `com.qualcomm.mbim_qdu` 对应联通分支。

### 5. QDU 直刷（推荐）

```sh
systemctl stop ModemManager
killall mbim-proxy 2>/dev/null || true
/usr/libexec/mbim-proxy &
# 保持 PCI power on
python3 scripts/qdu_flash.py /tmp/t99fw/fwout/ota.bin
```

脚本要点（踩过的坑）：

- 必须 **`DeviceOpenFlags.PROXY`**；无 proxy 时 QDU 常超时
- `qdu_file_open_response_parse` 返回值 **`[0]` 是成功 bool**，不是 max size；用 `out_max_transfer_size`（常见 ~130896），写入分片取 `min(device_max, 65536)`
- 分片若变成 **1 字节**，会刷到天荒地老——立刻停掉重来
- `WRITE DONE` 后 `session STOP` 可能因模组复位报错，可忽略；以版本为准
- 全程 `power/control=on`

完整脚本：[scripts/qdu_flash.py](scripts/qdu_flash.py)

### 6. 验证

```sh
systemctl restart ModemManager
# 等模组回来
mmcli -m any | grep -A2 'firmware revision'
# 期望第二行：063
```

或 AT：`AT+GMR` / `ATI`（注意 MM 占用 AT 口时先停 MM）。

## 与 OpenWrt FCC skill 的关系

- 拨号 / `CUSTOMER` / `SYS_ERR` / qmodem：用 [`t99w373-fcc-openwrt`](../t99w373-fcc-openwrt/SKILL.md)
- **只升模组固件**：用本 skill

（本仓库两个 skill 并列在 `skills/` 下。）

## Live U 盘定制备份

不必整盘镜像。本机已升到 063 后，U 盘可格式化复用。若要重做 Live，用原版 Fedora ISO + 下列文件：

- [live-usb/bringup-mhi.sh](live-usb/bringup-mhi.sh)
- [live-usb/grub.cfg](live-usb/grub.cfg)（已含 `pcie_aspm=off` + mhi 黑名单）

## 参考

- 坑与命令细节：[reference.md](reference.md)
