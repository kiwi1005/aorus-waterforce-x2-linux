# AORUS WATERFORCE X II 的 Linux 溫度顯示

已在 **X II 240／USB 0414:7a5e／F2.0** 實機確認，水冷頭能顯示真實 CPU
溫度，並隨負載升降。包含開機服務及選用的韌體更新工具。

## 修正了什麼

- 開發時遇到 F1.2 黑屏，更新到 F2.0 後恢復畫面。這是單一實機結果，不能保證所有黑屏都能靠更新解決。
- F2.0 改了溫度封包位置；舊程式會把16個執行緒誤當成16°C。本工具依韌體版本選擇格式。
- 自動尋找 k10temp／zenpower／coretemp，拒絕把不存在的感測值當成0°C。

## 使用

需要 Linux、Python3.11以上、可正常讀取的 CPU hwmon 感測器。
先停止 RigDeck、CoolerControl 或其他會使用同一水冷裝置的程式。

```sh
sudo python3.11 -m waterforce_linux status
sudo python3.11 -m waterforce_linux display-temperature --save
sudo python3.11 -m waterforce_linux monitor
```

確認畫面正常後，用 `sudo ./install.sh` 安裝專用低權限帳號、udev規則與
systemd服務。它不會自動刷韌體。日誌：

```sh
journalctl -u waterforce-linux -f
```

若 btop 顯示16°C而實際 CPU 更熱，先檢查它是不是選到 acpitz；應選真正的
CPU感測器，例如 `k10temp/Tctl`，再重開 btop。不要任意套用主機專屬核心補丁。

## 更換圖片／動畫

另需 FFmpeg（含 libx264）及 ffprobe。支援 PNG、JPEG、GIF 與常見影片，
自動轉成320×320；圖片以靜止短片播放，動畫循環播放。預設保留完整圖片並加黑邊，
可用 `--fit crop` 裁切填滿。預設最多10秒，可用 `--duration 30` 調整，上限60秒。

```sh
# 上傳並播放圖片
sudo python3.11 -m waterforce_linux media --manage-service upload photo.png --name photo.mkv --play
# 上傳並播放動畫
sudo python3.11 -m waterforce_linux media --manage-service upload animation.gif --name animation.mkv --play
# 列出已存檔案
sudo python3.11 -m waterforce_linux media --manage-service list
# 切換已存畫面
sudo python3.11 -m waterforce_linux media --manage-service play photo.mkv
# 回到 CPU 溫度
sudo python3.11 -m waterforce_linux media --manage-service temperature
```

`--manage-service` 會暫停並恢復原本正在執行的溫度服務；轉檔先完成才暫停服務。
不會覆寫同名檔案、刪除原有圖片或重新排序。圖片會寫入裝置儲存空間；播放或切回溫度時會自動套用並儲存設定。
實測 F2.0 若省略套用，雖然設定讀回改變，螢幕仍不會切換。這些操作不會重刷韌體。
完整說明與實測範圍見[圖片與動畫](media.md)。

## 韌體更新與限制

[韌體操作說明](firmware.md)只涵蓋已測試的 X II 240 F1.2 → 指定 F2.0。
專案不提供技嘉 EXE、DLL或韌體；請自行取得合法來源的檔案。
更新會寫入裝置，失敗可能需要原廠協助，不能任意斷電或盲目重刷。

服務重啟已測試；整機斷電重開、其他尺寸與版本尚未驗證。
CPU溫度、頻率、使用率有提供；GPU與功率等未實作欄位不要開啟顯示。

GPL-3.0-or-later，部分程式來自 RigDeck，詳見 [來源標註](../NOTICE.md)。
