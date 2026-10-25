# T99W373 / OpenWrt 参考

## 硬件标识

| 项 | 值 |
|----|-----|
| 模组 | Foxconn / Dell T99W373（同系还有 T99W640） |
| PCI | `105b:e0f5`，Class `0d40` Wireless controller |
| 主机驱动 | 常见 `mhi_q`（Quectel_Linux_PCIE_MHI） |
| AT | `/dev/mhi_DUN` |
| MBIM | `/dev/mhi_MBIM` |
| 数据网卡 | `rmnet_mhi0`，QMAP 子接口 `rmnet_mhi0.1` |
| 拨号器 | `quectel-CM-M`（qmodem 封装） |

链路降速（如 x1 @ 2.5GT/s 而 LnkCap 为 x2 @ 8GT/s）可能影响稳定性，但 MHI 仍可能起来；优先仍查 FCC/拨号。

## AT 命令速查

| 命令 | 用途 |
|------|------|
| `ATI` / `AT+CGMI` / `AT+CGMM` | 厂商型号；锁态常显示 DELL |
| `AT+CFUN?` / `AT+CFUN=1` | 射频；`0`=关（锁或关机） |
| `AT^CUSTOMER?` / `AT^CUSTOMER=0` | OEM 客户码；Dell 常见 `10`，解锁目标 `0` |
| `AT+CPIN?` | SIM；锁态下也可能 READY |
| `AT+CSQ` | 信号；未驻网常 `99,99` |
| `AT+COPS?` | 运营商；中文可能乱码/`????` |
| `AT+CEREG?` / `AT+C5GREG?` | LTE/NR 注册；第 2 字段 `1` 或 `5` 为已注册 |
| `AT+CGDCONT?` | PDP 上下文 |

发送示例：

```sh
tom_modem -d /dev/mhi_DUN -o C
tom_modem -d /dev/mhi_DUN -c 'AT+CFUN?' -t 5
```

## FCC / OEM 行为（本机实测归纳）

1. 出厂 Dell：`CUSTOMER:10`，开机常 `CFUN:0`。
2. `AT^CUSTOMER=0` 后厂商名可变 Qualcomm，射频可开。
3. `CUSTOMER=0` 多数重启后仍保留；**`CFUN=0` 仍可能每次开机出现**。
4. 因此开机策略：保留 `CUSTOMER=0`，拨号前只发 `AT+CFUN=1`（`pre_dial_at_cmds`）即可，无需 `rc.local` 双保险（除非用户要求）。
5. `quectel-CM-M` 日志可能写 “does not require FCC authentication”——指其内置 FCC auth 流程，**不代表** OEM `CUSTOMER`/`CFUN` 锁不存在。

## qmodem UCI 要点

路径：`/etc/config/qmodem`

**main**

- `enable_dial`：总开关
- `enable_pcie_scan`：默认常为 0；不开则重启后可能无 `modem-device`，需手动扫描
- `enable_usb_scan`：USB 模组

**modem-device（例：`0000_04_00_0`）**

- `path`：`/sys/bus/pci/devices/0000:04:00.0/`
- `at_port`：`/dev/mhi_DUN`
- `network`：`rmnet_mhi0`（拨号绑父网卡）
- `modes`：`mbim`
- `enable_dial` / `state`：`enabled`
- `soft_reboot`：建议 `0`（失败软重启易触发 MHI SYS_ERR）
- `pre_dial_at_cmds`：list，拨号前 AT
- `post_init_at_cmds`：扫描加入后 AT（可选）

网络接口常由拨号脚本创建：`network.0000_04_00_0`（dhcp → `rmnet_mhi0.1`），需在 firewall wan zone。

## 服务与脚本

| 路径 | 作用 |
|------|------|
| `/etc/init.d/qmodem_init` | 开机扫描（受 enable_*_scan 控制） |
| `/etc/init.d/qmodem_network` | 按 UCI 启动/停止 dial 实例；stop/reload 会 hang |
| `/usr/share/qmodem/modem_scan.sh` | `scan` / `add` / `disable` |
| `/usr/share/qmodem/modem_dial.sh` | dial / hang；调 pre_dial hook |
| `/usr/share/qmodem/modem_hook.sh` | 执行 `pre_dial_at_cmds` / `post_init_at_cmds` |
| `/usr/share/qmodem/modem_ctrl.sh` | LuCI `base_info` / `info` |
| `/usr/share/qmodem/vendor/foxconn.sh` | Foxconn 信息解析 |

日志目录：`/var/run/qmodem/<section>_dir/dial_log`  
信息缓存：`/tmp/cache_info_<section>`、`/tmp/cache_base_info_<section>`

## 日志关键字

| 日志 | 含义 |
|------|------|
| `modem_scan_scan: add modem t99w373` | 扫描成功 |
| `pre_dial: execute_ats ... AT+CFUN=1` | 拨号前钩子 |
| `qmodem_network: Start Dial Now` | 开始拨号 |
| `qmodem_network: Stop Dial and Hang` | **主动挂断**（stop/reload 或 enable 被关） |
| `mbim_read_thread poll err/hup` | MBIM 通道掉 |
| `MHI system error detected` | PCIe MHI 故障，网卡会 unregister |
| `uhttpd ... Failed to run operation` / `restoring old tty` | AT 口争用 |

`_update_modem` 逻辑摘要：`target=0` 当 `state=disabled` 或 `enable_dial=0` 或 `main.enable_dial=0` 或 `force_stop=1`（服务 stop）。

## 已知坑

1. **AT 口争用**：LuCI 自动刷新 + 脚本 + `modem_sim` 并行 → 回显错位、坏缓存。
2. **开机未扫 PCIe**：`enable_pcie_scan` 默认 0；hotplug 过早时 `dun_devices` 为空。
3. **拨号中 restart qmodem_network**：会 hang 掉已成功的会话，IP 瞬间消失。
4. **soft_reboot=1**：失败路径软重启模组，易连环 MHI SYS_ERR。
5. **PowerShell 远程 SSH**：管道与引号易被本地解析；用临时 `.py` + paramiko。
6. **空 root 密码**：paramiko 需尝试 none / 空密码。

## 健康检查清单（重启后）

```sh
uci show qmodem.main
uci show qmodem.0000_04_00_0
ls /dev/mhi_DUN /sys/class/net/rmnet_mhi0.1
tom_modem -d /dev/mhi_DUN -c 'AT^CUSTOMER?' -t 5
tom_modem -d /dev/mhi_DUN -c 'AT+CFUN?' -t 5
pgrep -a quectel-CM-M
ip -4 addr show rmnet_mhi0.1
ip -4 route show default
ping -c 2 -W 3 223.5.5.5
```
