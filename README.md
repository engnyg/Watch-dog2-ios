# Watch Dogs 2 → iPad（原生 ARM64 路線）

依據《赛博朋克 2077》iPad 移植經驗整理。**目前狀態：只有前置工具與計畫，尚未取得 Watch Dogs 2 的 macOS 二進位，沒有任何可執行的移植成果。**

## 第 0 關：先判斷這條路線是否適用（決定性）

Cyberpunk 能成功，前提是 Steam 上有**原生 ARM64、未加密**的 macOS 版。Watch Dogs 2 是否有 macOS 版、是否含 arm64 切片，我沒有驗證，必須用實際檔案確定：

```sh
python3 -I tools/audit.py "<遊戲>/…/MacOS/<主程式>"
```

- `VERDICT: NO-GO`（只有 x86_64，或 cryptid≠0）：本路線不適用。x86_64 需要 CPU 模擬／JIT，是另一個專案，不要硬套下面的步驟。
- `VERDICT: GO`：記錄 UUID、`__text` SHA-256、依賴庫，繼續。

另需 Mac + Xcode、有效開發簽名、含目標 iPad 的描述文件、自己合法持有的遊戲資源。Linux 雲端環境只能跑本倉庫的 Python 工具，不能建置或簽名。

## 路線（沿用 Cyberpunk 的做法）

UIKit 宿主 → 載入經轉換的遊戲 ARM64 映像 → 桌面介面（AppKit/Cocoa/路徑/顯示）相容層 → 原生 Metal（`CAMetalLayer`）→ AVAudioSession → GameController。不用 Windows 版、CPU 模擬、JIT 或串流。

## 階段與驗收

| # | 階段 | 驗收（要有證據，不用「看起來可以」） |
|---|------|------|
| 1 | 審計 `tools/audit.py` | 報告含 UUID、平台、依賴、cryptid、`__text` 雜湊；原檔不動 |
| 2 | 格式轉換（平台/依賴路徑，列為 `prepare.py`，待寫） | 轉換前後 `__text` 雜湊相同；多架構先取 arm64 |
| 3 | 附帶庫對齊（如 Bink 類符號字串池需 8 位元組對齊） | 只改元資料，不改指令 |
| 4 | 宿主 + 簽名 + 安裝 | dyld 能載入；信任問題與載入錯誤分開判斷 |
| 5 | 資源傳輸（AFC，4 MiB 分塊、`.part` 續傳、原子改名）+ `tools/resource_manifest.py` | **裝置端**重算 SHA-256 與本機一致；檢查大小寫路徑（如 `Mac` vs `mac`，用符號連結，不偽造查詢結果） |
| 6 | 窗口/啟動 | 逐項區分黑屏：進程被暫停？入口執行？窗口可見？有 drawable？命令緩衝完成？ |
| 7 | 輸入/音訊 | 手柄：系統控制器→原生事件→遊戲回調→實際回應，四段分別驗；若遊戲只聽連接通知，初始化後主動補同步；音訊驗會話/路由/PCM 非零 |
| 8 | 記憶體 | 見下 |
| 9 | 畫質/幀率 | 實測，區分原生幀與生成幀 |

## 從 Cyberpunk 帶過來的關鍵教訓

1. **閃退先分類**：SIGSEGV、SIGTRAP+ENOMEM、GPU 命令錯誤（`NotPermitted`＝後台提交）、被 LLDB 暫停，原因不同。每次記錄 `.ips`、PID、UUID、異常、遊戲偏移、場景、啟動參數。
2. **進程可用額度 ≠ 虛擬位址空間**。Cyberpunk 在仍有約 4.8 GB 額度時，因原遊戲預留 4 GiB 連續位址而 `mmap` 回傳 ENOMEM。個人開發團隊拿不到 extended-virtual-addressing，所以只縮小遊戲的預留常量。
3. **補丁規則**：只改有崩潰證據指向的預留；先審 UUID 與原始位元組（`tools/patch_memory_budget.py` 強制）；保留原 OOM/增長/釋放邏輯；不用 `MAP_FIXED` 或位址提示假裝修好；不偽造 mmap 成功。**偏移與雜湊只對該版本有效，Watch Dogs 2 需從零找，Cyberpunk 的四個偏移完全不能搬。**
4. **棧**：引擎若有大棧幀（Cyberpunk 約 527 KB），GCD 工作緒 512 KiB 不夠，原入口放 8 MiB 棧的 NSThread。
5. **設定檔字串不等於實際演算法**：超分/限幀要用 HUD 與基準旗標交叉核對。
6. **不偽造**：Steam 授權/連網失敗就如實記錄，不假裝登入成功；TLS 不關校驗。
7. 工作目錄放 iCloud 之外；原始資源不改；不一次用 CoreDevice 複製數十 GB 目錄。
8. 簽名描述文件有到期日，到期需重簽更新並保留 Bundle ID 與資料容器。

## 工具（已實作並有單元測試）

```sh
python3 -I -m unittest discover -s tests
python3 -I tools/audit.py <Mach-O> [--json]
python3 -I tools/patch_memory_budget.py <in> <out> patches.json [--check]
python3 -I tools/resource_manifest.py <遊戲根目錄> manifest.json
```

## 待辦（需要 Mac 與實際檔案才能做）

- `prepare.py`（Mach-O 平台/依賴轉換）、`stage.py`（逐個簽名＋嚴格驗證）、UIKit 宿主與相容層、`transfer_resources.py`。
- 以真實崩潰證據找出 Watch Dogs 2 的預留位址/棧需求，再填 `patches.json`。
- 這些在沒有目標二進位前不能憑空寫對；請先提供第 0 關的審計輸出。
