# Display presets / 顯示預設

Presets configure the device's native live-data layouts. They do not encode a
screenshot repeatedly or rewrite fan/pump curves. The monitor continues sending
real CPU temperature, frequency and utilization every 1.5 seconds.

| Name | 顯示內容 / Display |
|---|---|
| `temperature` | CPU 溫度大字 / large CPU temperature |
| `frequency` | CPU 頻率大字 / large CPU frequency |
| `temp-clock` | 溫度＋頻率 / temperature + frequency |
| `dashboard` | 溫度、頻率、使用率、風扇 RPM / four information zones |
| `cooling` | 溫度、風扇與水泵輪播、頻率 / temperature, alternating fan/pump RPM, frequency |
| `network` | 本機 IPv4，搭配溫度與頻率輪播 / local IPv4 plus rotating temperature/frequency |

The native layouts retain the manufacturer's background/artwork. Colors are
orange, cyan, light green and white. Selected items within a zone rotate every
3 seconds. CPU frequency is the average current frequency reported by Linux,
shown in GHz to one decimal; it is not a maximum boost-clock measurement.

## Select / 選擇預設

From the source directory, use `python3.11 -m waterforce_linux`. If the console
entry point is installed, replace that prefix with `waterforce-linux`.

```sh
# No hardware access / 列出選項
python3.11 -m waterforce_linux preset list

# Interactive menu / 數字選單
sudo python3.11 -m waterforce_linux preset --manage-service choose

# Select by name / 直接指定
sudo python3.11 -m waterforce_linux preset --manage-service apply temp-clock
sudo python3.11 -m waterforce_linux preset --manage-service apply dashboard
sudo python3.11 -m waterforce_linux preset --manage-service apply network

# Pick a network interface / 指定網卡
sudo python3.11 -m waterforce_linux preset --manage-service apply network --interface eth0

# Saved preference, not a USB readback of current display mode
python3.11 -m waterforce_linux preset current
```

Applying a preset saves settings once, after display and cooling-mode readback
checks. `--manage-service` pauses/restores the active telemetry service. Root is
required to save `/etc/waterforce-linux/preset.json`. Press Enter to cancel the
interactive menu. Later image/video selection can override the display without
changing this saved preset preference; apply a preset again to return to it.

IP uses the native CPU-name text field on layout 2. The updated monitor must be
running; an older monitor will overwrite it with the CPU model name. The monitor
rechecks configuration and the address approximately every 10 seconds, sending
text only when it changes, without flash writes. It uses the default IPv4
route's source address (a local routing lookup, no outbound packet), or the first
global-scope IPv4 address on `--interface`. VPN routes may select a VPN address;
choose the physical interface if needed. No address displays `IP OFFLINE`.
IPv6 and simultaneous multiple-address display are not implemented.

IP 預設必須搭配新版溫度服務，約每10秒檢查位址變化；沒有位址時顯示
`IP OFFLINE`。它顯示本機網路位址，不是查詢外部網站取得的公網 IP。
預設以系統路由選擇網卡，可用 `--interface` 指定。更新 IP 不會寫入韌體或快閃設定。

## Cooling boundary / 散熱界線

Preset code sends display commands only. Tests reject accidental introduction
of fan/pump control opcodes, and the hardware path checks modes before saving.
The existing monitor still requests volatile Turbo on missing/invalid CPU sensor
readings; this is an error response, not part of preset selection.

One X II 240 F2.0 was checked with Default fan / Balanced pump: idle about 42°C,
fan 1,380 RPM and pump 2,660 RPM. A 12-second synthetic workload reached about
57°C with fan 1,780 RPM and pump 2,940 RPM. A background-activity rise during
recovery peaked at 62°C; the reading returned to 42°C. Modes remained unchanged.
These are observations from one short run, not a thermal certification or proof
of behavior without telemetry, during long full load, or after a cold boot.

目前測試顯示會隨溫度調速；不能因此保證所有開機、服務中斷或長時間滿載狀況。
持續更新 CPU 溫度的服務應保持運作。原廠韌體掌管風扇／水泵控制，不能宣稱
更新韌體永遠不影響散熱；此專案的預設功能不改寫曲線。

## Validation status

All six presets passed mode/field readback on X II 240 F2.0, and fan/pump modes
and stored curves matched the pre-test snapshot afterward. The updated telemetry
service restarted and supplied live data in network mode. The owner visually confirmed all four dashboard values update, and that the
complete IP label and rotating temperature/frequency display correctly. Other
layouts passed device readback but were not individually visually confirmed;
other devices are unverified.
