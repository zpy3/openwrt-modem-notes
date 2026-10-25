---
name: t99w373-fcc-openwrt
description: >-
  Diagnose and fix Foxconn/Dell T99W373 (PCI 105b:e0f5) FCC lock and qmodem
  dial issues on OpenWrt/ImmortalWrt. Use when T99W373, T99W640, CUSTOMER,
  CFUN=0, FCC lock, mhi_DUN, rmnet_mhi0, qmodem modem_info empty, or PCIe
  5G modem has no IP / host cannot opkg update after dial.
---

# T99W373 FCC 锁 + OpenWrt/qmodem 排查

针对 **Dell/Foxconn T99W373**（`lspci`：`105b:e0f5`，驱动常为 `mhi_q` / Quectel PCIe MHI）在 OpenWrt 系固件（含 ImmortalWrt + luci-app-qmodem）上的识别、解锁、拨号与掉线问题。

默认路由器示例：`192.168.10.1`，SSH `root`（密码可能为空）。以现场 UCI/设备节点为准。

## 何时使用

- LuCI qmodem 模组信息空白 / Connect=No / 假 SIM Error
- `lspci` 有模组但网页取不到信息
- `AT+CFUN?` → `0`，怀疑 FCC 锁
- 拨号短暂成功后 IP 消失、本机无法上网 / `opkg update` 失败
- 开机后模组不自动出现、需手动扫描

## 快速判定

| 现象 | 优先怀疑 |
|------|----------|
| `lspci` 有 e0f5，无 `/dev/mhi_DUN` | MHI 未起来 / 驱动未绑 |
| 有 `mhi_DUN`，`CFUN=0`，`AT^CUSTOMER?`≠0 | **FCC/OEM 锁** |
| `CUSTOMER:0` 且 `CFUN=1`，但仍无网 | 拨号/路由/mwan，非锁 |
| 曾拿到 IP，随后 `modem_hang` / `rmnet` 消失 | qmodem 被 stop/reload 挂断，或 **MHI SYS_ERR** |
| 重启后 qmodem 无模组段 | 未开 `enable_pcie_scan` / 配置未 commit |

详细 AT、UCI、日志关键字见 [reference.md](reference.md)。

## 排查流程

```
Task Progress:
- [ ] 1. SSH + 确认 PCIe/MHI/AT 口
- [ ] 2. 读 CFUN / CUSTOMER / ATI（单线程，先清理 tom_modem）
- [ ] 3. 若锁定：CUSTOMER=0 + CFUN=1，再验驻网
- [ ] 4. 确认 qmodem 配置已 commit + 开机扫描/拨号钩子
- [ ] 5. 查拨号日志与默认路由；排除 hang / MHI SYS_ERR
- [ ] 6. 清坏缓存后刷新 LuCI（勿多开页面狂刷 AT）
```

### 1. 硬件与驱动

```sh
lspci -nnk | grep -A5 -iE 'e0f5|Foxconn|0d40'
ls -l /dev/mhi_*
ls /sys/class/net | grep mhi
dmesg | grep -iE 'mhi|e0f5|SYS_ERR' | tail -50
```

期望：`Kernel driver in use: mhi_q`，存在 `/dev/mhi_DUN`、`/dev/mhi_MBIM`，网卡 `rmnet_mhi0` / `rmnet_mhi0.1`。

### 2. AT 口规则（重要）

- 只用 **`tom_modem -d /dev/mhi_DUN`**（或系统 `at` 封装），**串行**发送。
- 先：`tom_modem -d /dev/mhi_DUN -o C` 清信号量。
- 禁止多个 `modem_ctrl` / 本地脚本并行抢 AT；否则回显错位，LuCI 会显示空厂商、假 SIM Error。
- 锁态特征：

```text
ATI            → Manufacturer: DELL（常见）
AT+CFUN?       → +CFUN: 0
AT^CUSTOMER?   → +CUSTOMER :10   # Dell OEM，非 0 即未解锁档
```

解锁后常见：`Manufacturer: Qualcomm`，`CUSTOMER :0`，`CFUN: 1`。

### 3. 解锁与驻网验证

```sh
tom_modem -d /dev/mhi_DUN -o C
tom_modem -d /dev/mhi_DUN -c 'AT^CUSTOMER=0' -t 10
tom_modem -d /dev/mhi_DUN -c 'AT+CFUN=1' -t 10
tom_modem -d /dev/mhi_DUN -c 'AT^CUSTOMER?' -t 5
tom_modem -d /dev/mhi_DUN -c 'AT+CFUN?' -t 5
tom_modem -d /dev/mhi_DUN -c 'AT+C5GREG?' -t 5
tom_modem -d /dev/mhi_DUN -c 'AT+CEREG?' -t 5
```

驻网：`+C5GREG: *,1|5` 或 `+CEREG: *,1|5`。再查：

```sh
ip -4 addr show rmnet_mhi0.1
ip -4 route show default
ping -c 3 -W 3 223.5.5.5
```

`CUSTOMER=0` 多数会写进模组；**开机仍可能 `CFUN=0`**，需拨号前再拉射频。

### 4. qmodem 持久化（推荐最小集）

不要叠 `rc.local` 兜底，除非用户明确要求。用 qmodem 自带钩子即可：

```sh
# 开机扫 PCIe
uci set qmodem.main.enable_pcie_scan='1'
uci set qmodem.main.enable_dial='1'

# 拨号前只拉射频（CUSTOMER 已为 0 时）
while uci -q delete qmodem.0000_04_00_0.pre_dial_at_cmds; do :; done
uci add_list qmodem.0000_04_00_0.pre_dial_at_cmds='AT+CFUN=1'

# 降低失败时软重启模组导致 MHI SYS_ERR 的概率
uci set qmodem.0000_04_00_0.soft_reboot='0'

uci commit qmodem
```

首次若无 `modem-device` 段：LuCI 扫描一次，或：

```sh
ash /usr/share/qmodem/modem_scan.sh scan 0 pcie
uci commit qmodem
```

钩子实现：`/usr/share/qmodem/modem_hook.sh <section> pre_dial`（由 `modem_dial.sh` 调用）。

### 5. 「拨号成功但 IP 没了 / 主机上不了网」

1. 看是否被服务挂断：

```sh
logread | grep -iE 'Stop Dial and Hang|modem_hang|qmodem_network'
```

`qmodem_network` 在 `stop`/`reload`、或 `enable_dial=0` / `state=disabled` 时会 **hang** 并清地址。

2. 看 MHI 是否崩过：

```sh
dmesg | grep -i 'MHI system error'
```

3. 现状：

```sh
ifstatus 0000_04_00_0
ip -br addr; ip route
pgrep -a quectel-CM-M
tail -50 /var/run/qmodem/0000_04_00_0_dir/dial_log
```

恢复：避免拨号中途反复 restart；配置稳定后执行一次：

```sh
/etc/init.d/qmodem_network start
# 等待拿到 inet 与 default 路由后再测 ping
```

### 6. LuCI 显示异常

坏缓存示例：厂商空、Connect=No、SIM Error，但 AT 实际正常。

```sh
killall -9 tom_modem 2>/dev/null
# 杀掉卡住的 modem_ctrl.sh info（勿杀 quectel-CM-M）
rm -f /tmp/cache_info_0000_04_00_0 /tmp/cache_base_info_0000_04_00_0
tom_modem -d /dev/mhi_DUN -o C
/usr/share/qmodem/modem_ctrl.sh base_info 0000_04_00_0
/usr/share/qmodem/modem_ctrl.sh info 0000_04_00_0
```

然后强制刷新页面。ISP 显示 `????` 多为 UCS2 中文运营商名，可忽略。

## SSH 注意（Windows 侧）

- 空密码：`paramiko` 可能需 `auth_none` 失败后再 `auth_password("")`。
- PowerShell 会吞 `|`、引号；复杂远程命令写成 `.py` 再执行。
- 长等待脚本易被中断；诊断用短命令，拨号等待单独轮询。

## 相关文件

- [reference.md](reference.md) — AT 表、UCI 字段、日志对照、已知坑
