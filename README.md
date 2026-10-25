# OpenWrt 模组笔记

OpenWrt / ImmortalWrt 上 PCIe 5G 模组（以 **Foxconn/Dell T99W373 / DW5932e** 为主）的排查与固件升级笔记，按 Cursor Agent Skill 格式整理，也可当普通 Markdown 手册读。

## Skills

| Skill | 用途 |
|-------|------|
| [skills/t99w373-firmware-qdu](skills/t99w373-firmware-qdu/) | Fedora Live + MBIM QDU 升模组固件（如 CU.001.050→063） |
| [skills/t99w373-fcc-openwrt](skills/t99w373-fcc-openwrt/) | OpenWrt/qmodem：FCC/`CUSTOMER`、MHI `SYS_ERR`、拨号 |

## 免责声明

- 模组固件升级与 AT 解锁操作有变砖 / 失联风险，后果自负。
- 仓库**不包含**厂商 `.cab` / `ota.bin`；请自行从 [LVFS](https://fwupd.org/) 获取。
- 与 Dell/Foxconn/Qualcomm 无官方关系。

## 在 Cursor 里用

把对应 skill 目录复制或软链到项目的 `.cursor/skills/`，或加入个人 skills 目录即可。
