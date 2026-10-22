# Watch Dogs 2（Steam）在 Madeira 上的 Bug 記錄與解決方式

> 環境：Madeira `main` @ 279fd0f，iPhone18,3，iOS 26.6.1，JIT via StikDebug  
> 遊戲：Watch Dogs 2（Steam app 447040）  
> 日期：2026-10-21

---

## 一、FEX 32-bit 指令 `0x82` 解碼失敗（已修復）

### 問題描述

x86 32-bit 指令集中，opcode `0x82` 是 `0x80` 的別名，兩者語意相同（`ADD/OR/AND/SUB/XOR r/m8, imm8` 加上立即數 imm8），只是 opcode 數字不同。FEX 的 `OpDispatchBuilder::SecondaryALUOp` 的 `switch` 敘述只列了 `0x80`、`0x81`、`0x83`，漏掉 `0x82`，導致遇到該 opcode 時輸出：

```
Unknown ALU Op: 0x10/0x11/0x14/0x15/0x16
```

並觸發 `DecodeFailure`。在 `upc.exe` 單次執行中出現 **34 次**。

### 根本原因

`FEX/FEXCore/Source/Interface/Core/OpcodeDispatcher/ALU.cpp`（或對應路徑）的群組表把 `0x82` 路由進 `SecondaryALUOp`，但函式內的 `switch` 沒有對應的 case 標籤。

### 解決方式

在該 `switch` 的五個子運算（ADD/OR/AND/SUB/XOR）case 標籤中，各補上 `OpToIndex(0x82)` 的 fall-through label，讓 `0x82` 與 `0x80` 走完全相同的邏輯。

修復工具已放在：`tools/patch-fex-0x82.py`  
CI 階段：`01b-fex-patch` → `07g-fex-wow64`

**修復後效果**：`Unknown ALU Op` 由 34 行降為 0 行。  
**注意**：此修復本身不影響 `upc.exe` 最終崩潰的結果（詳見第三節）。

---

## 二、SMC（自修改程式碼）檢查導致的啟動迴圈（已繞過）

### 問題描述

未加任何設定時，`WatchDogs2.exe` 的 64-bit 主程式在啟動後數分鐘內，會卡在 `Disrupt_64.dll+0x8417C80` 附近的 SMC（Self-Modifying Code）例外迴圈，無法繼續執行。

### 根本原因

FEX 預設啟用 SMC 完整性檢查；遊戲引擎的熱修補（hot-patching）機制反覆觸發 SMC 偵測，產生大量例外，FEX 持續回到翻譯模式，形成無限迴圈。

### 解決方式

在遊戲的 per-game 設定（Madeira Dock → 遊戲設定）中加入：

```
env.FEX_SMCCHECKS = none
```

此設定關閉 FEX 的 SMC 完整性檢查，迴圈消失，遊戲可正常進入 `WatchDogs2.exe` 主流程。

**副作用**：理論上若遊戲本身有自修改程式碼需要追蹤，可能有翻譯快取不一致的風險；但實際測試中 WD2 主程式並無此問題。

---

## 三、`upc.exe`（Ubisoft Connect）啟動約 8 秒後以 `0xDEADC0DE` 退出（**未解決**）

### 問題描述

`WatchDogs2.exe` 啟動後會把控制權交給 32-bit 的 `UbisoftGameLauncher.exe`，後者再啟動 `upc.exe`（32-bit，基於 CEF 的 Ubisoft Connect 遊戲啟動器）。`upc.exe` 在約 8 秒後呼叫 `NtRaiseHardError(0x50000018)` 並以結束碼 `0xDEADC0DE` 退出，整個遊戲因此無法進入主選單。

### 觀測到的死亡序列（兩次 trace 完全一致）

```
x86 INT1（opcode 0xF1）
  → FEX 發出 BRK #0（0xd4200000），log 顯示 [store-undecoded] / [int3-guest]
  → Wine ntdll：trap_handler → EXCEPTION_ILLEGAL_INSTRUCTION
  → libwow64fex：重新包裝為 EXCEPTION_SINGLE_STEP（EIP=0x2C1662F，TF=0）
  → upc.exe SEH handler 接收例外，開始執行
  → 多次呼叫 NtQueryInformationProcess
      · 類別 0x1A（ProcessDebugPort）
      · 類別 0x3F2（ProcessDebugObjectHandle）
      · 類別 0x07（ProcessImageFileName）
      · 類別 0x1E / 0x25 / 0x24 / 0x00
  → NtRaiseHardError(0x50000018, ...)
  → NtTerminateProcess(0xDEADC0DE)
```

### 分析

1. **Wine/FEX 傳遞例外是正確的**  
   - EIP=0x2C1662F（.ubx 打包層在高位段的程式碼）、TF=0  
   - `BeingDebugged=0`、`ProcessDebugPort=0`（`[bad-close]` handler 正確回傳 `STATUS_INVALID_HANDLE`）  
   - 模擬器這端沒有傳錯任何參數。

2. **upc.exe 是單執行緒啟動**（tid 00c0，無 CEF 執行緒）  
   整個崩潰發生在 CEF 初始化之前，所以不是 CEF 或網路問題。

3. **upc.exe 沒有任何外部 I/O**  
   - 沒有開啟 Steam registry key、Steam 檔案、Steam socket  
   - 只有 `WSAStartup`（初始化 Winsock），沒有後續的網路呼叫  
   - Launcher 建立的 `Local\UPC_SDK_GameStarter_Event_3619` 從未被 upc.exe 開啟

4. **結論：這是 `.ubx` 打包層的完整性自查流程**  
   INT1（`0xF1`）是 x86 ICE Breakpoint，常見於 anti-tamper / 反偵錯保護；後續一連串 `NtQueryInformationProcess` 查詢偵錯器相關資訊，確認後由自身的 SEH handler 決定以 `0xDEADC0DE` 結束。這是 Ubisoft 保護機制的一部分，不是模擬器的錯誤。

5. **Launcher 端的現象**  
   Launcher 以 `STATUS_OBJECT_NAME_NOT_FOUND` 輪詢 `\\.\pipe\terminal_1_game_start_ipc_pipe_` 達 98 次，這條 pipe 從未被建立，因為 upc.exe 在建立之前就已退出。

### 可能的後續方向（需要 Madeira 作者確認）

- Ubisoft Connect（32-bit CEF `upc.exe`）在 WoW64 路徑下是否屬於預期支援的案例？
- 在 `-uplay_steam_mode` 模式下，是否有繞過 upc.exe 完整性檢查的官方或已知方式？
- `0x2C1662F`（.ubx 高位段）的完整性觸發條件是否可能源自 FEX 翻譯層對某些指令的微小語意差異（如記憶體排序、EFLAGS 時序），而非真正的反偵錯觸發？

**重要限制**：分析到此為止。「讓 upc.exe 跑過去」需要繞過 Ubisoft 的 `.ubx` 打包保護，這不在本專案範圍內，也不是 Madeira 應該做的事。

---

## 四、i386 Wine farm 建置（已完成，前置工作）

| 項目 | 狀態 |
|------|------|
| `i386-windows` farm（725 檔案，含 DXMT i386）| ✅ 完成 |
| `xtajit.dll`（FEX WoW64，含 0x82 修復）| ✅ 完成 |
| DXMT i386 shim（`d3d9.dll`）| ✅ 完成 |
| 32-bit `steam_api.dll` / `steamclient.dll` | ✅ 存在於 prefix |
| `UbisoftGameLauncher.exe` 可啟動、執行緒正常 | ✅ 正常 |
| `upc.exe` 能載入 `libcef.dll`、`d3d9.dll`（DXMT shim）、winhttp | ✅ 能載入 |

---

## 五、附錄：相關文件

| 文件 | 說明 |
|------|------|
| `docs/madeira-wd2-ubisoft-connect-issue.md` | 準備發給 Madeira 作者的 issue 草稿（尚未發出） |
| `docs/madeira-wd2-smc-atomic-issue.md` | SMC 原子性問題詳細記錄 |
| `tools/patch-fex-0x82.py` | FEX 0x82 opcode 補丁腳本 |
| `.github/workflows/madeira-ipa.yml` | CI 建置流程（含 `01b-fex-patch`、`07g-fex-wow64`、`13i0-wine-i386` 等階段） |
