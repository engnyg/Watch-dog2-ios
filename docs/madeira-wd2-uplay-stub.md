# Fix: Watch Dogs 2 RunGameEx 初始化呼叫 uplay_r1_loader64.dll 卡死

## 問題根源

`WatchDogs2.exe`（525 KB stub）初始化流程：

```
WatchDogs2.exe
  └─ LoadLibraryW(L"Disrupt_64.dll")
  └─ GetProcAddress(hDisrupt, "RunGameEx")
  └─ RunGameEx(argv, arg2, &exit_code, NULL, mutex_callback)
        └─ Disrupt_64.dll 內部
              └─ LoadLibraryW("uplay_r1_loader64.dll")
              └─ UPLAY_Start(3619, sdk_ver, hwnd)
                    └─ 透過 named pipe 聯繫 upc.exe 做 Steam 帳號驗證
                          ↑ 在 Madeira/FEX 上 upc.exe 以 0xDEADC0DE 退出
                            (SteamInfoReceiver "Failed receive local steam response"
                             → pipe \\.\pipe\terminal_1_game_start_ipc_pipe_ 從未建立)
                          → UPLAY_Start 掛住或回傳失敗 → 遊戲退出
```

原始分析見 `docs/madeira-wd2-ubisoft-connect-issue.md`。

## 修法：stub `uplay_r1_loader64.dll`

`tools/uplay-stub/uplay_r1_loader64.c` 實作一個只回傳「離線成功」的替代 DLL：

| 函式 | Stub 行為 |
|------|-----------|
| `UPLAY_Start` | 立刻回傳 `TRUE`，不啟動也不等待 upc.exe |
| `UPLAY_User_IsOwned` / `UPLAY_IsOwned` | 回傳 `TRUE`（假設已擁有遊戲） |
| `UPLAY_User_GetIdHex` | 回傳固定假 ID `DEADBEEFCAFEBABE` |
| `UPLAY_Overlay_IsEnabled` | 回傳 `FALSE`（不顯示 overlay） |
| 其餘 75 個 export | 回傳空串列或 `TRUE`（不操作） |

不呼叫 upc.exe、不碰 Steam registry、不建立 IPC pipe。

## Disrupt_64.dll 分析結果

靜態分析 `Disrupt_64.dll`（133MB，高度保護/打包）的結果：

- **Delay import table**：只有 `libScePad.dll` 和 `steam_api64.dll`；uplay 不在其中。
- **uplay 載入方式**：Disrupt 在執行期透過 `LoadLibraryW("uplay_r1_loader64.dll")` 再 `GetProcAddress` 取得各函式——不使用 delay import。
- **命名方案**：Disrupt 使用全大寫元件名稱（`UPLAY_USER_*`、`UPLAY_OVERLAY_*`、`UPLAY_FRIENDS_*` 等），**非** 初版 stub 的混合大寫（`UPLAY_User_*`）。Windows named export 區分大小寫，因此原版 stub 的 `UPLAY_User_IsOwned` 無法被 `GetProcAddress("UPLAY_USER_IsOwned")` 找到。

**Disrupt 實際呼叫的函式**（從 .edata 字串表取得）：

| 類別 | 函式 |
|------|------|
| 核心 | `UPLAY_Start`, `UPLAY_Update`, `UPLAY_GetNextEvent`, `UPLAY_GetLastError`, `UPLAY_HasOverlappedOperationCompleted`, `UPLAY_GetOverlappedOperationResult` |
| 用戶 | `UPLAY_USER_IsOwned`, `UPLAY_USER_IsConnected`, `UPLAY_USER_IsInOfflineMode`, `UPLAY_USER_GetNameUtf8`, `UPLAY_USER_GetAccountIdUtf8`, `UPLAY_USER_GetTicketUtf8`, `UPLAY_USER_SetGameSession`, `UPLAY_USER_ClearGameSession` |
| Overlay | `UPLAY_OVERLAY_Show`, `UPLAY_OVERLAY_ShowNotification`, `UPLAY_OVERLAY_ShowShopUrl` |
| 好友 | `UPLAY_FRIENDS_Init`, `UPLAY_FRIENDS_GetFriendList`, `UPLAY_FRIENDS_InviteToGame`, `UPLAY_FRIENDS_ShowFriendSelectionUI` |
| 派對 | `UPLAY_PARTY_*`（8 個函式） |
| 存檔 | `UPLAY_SAVE_*`（7 個函式） |
| 安裝 | `UPLAY_INSTALLER_*`（6 個函式） |
| 其他 | `UPLAY_ACH_EarnAchievement`, `UPLAY_AVATAR_Get/Release`, `UPLAY_WIN_RefreshActions` |

**upc.exe 分析**：17MB PE32，`.text`/`.rdata`/`.data` 皆 rawsz=0（執行期解壓），`.ubx2` 為 16.8MB 打包資料，字串完全加密，無法靜態取得 SteamInfoReceiver 細節。

## 建置

CI (`madeira-ipa.yml` stage `13h2-uplay-stub`) 在 stage 03 (llvm-mingw) 之後自動建置：

```bash
bash build/uplay-stub/build.sh
```

輸出：
- `app/Madeira/arm64ec-windows/uplay_r1_loader64.dll`
- `app/Madeira/arm64ec-windows/uplay_r2_loader64.dll`（同一個檔案的複本，因部分 Steam 版本用 R2 名稱）

這兩個路徑在 Madeira 的 Wine 前置中位於 system DLL 搜尋路徑，會在遊戲目錄中同名的真實 DLL 之前被找到。

## 手動部署（不重新建 IPA）

若要在不重新建 IPA 的情況下測試，可以在已安裝的 Watch Dogs 2 目錄直接放入 stub：

```bash
# 在安裝有 llvm-mingw 的 macOS 上
bash build/uplay-stub/build.sh

# 把 stub 複製到遊戲的 bin/ 目錄（替換真實 DLL）
cp app/Madeira/arm64ec-windows/uplay_r1_loader64.dll \
   "<Steam Library>/steamapps/common/Watch_Dogs2/bin/uplay_r1_loader64.dll"
```

## 已知限制

- 線上功能（好友、排行榜、成就同步、Uplay 商店）完全停用。
- 若遊戲在 `UPLAY_Start` 之後還用 `UPC_Init` 等 UPC API（`uplay_r2_loader64.dll` 有此 API），
  則需確認 R2 stub 也涵蓋。目前 R2 版本與 R1 完全相同。
- 若遊戲做了更深入的反盜版檢查（例如在 `Disrupt_64.dll` 內部校驗 pipe
  是否在超時前建立），需要追加測試。
- Easy Anti-Cheat (EAC) 是另一個問題，與 uplay stub 無關。

## 與 FEX 0x82 修正的關係

`docs/madeira-wd2-ubisoft-connect-issue.md` 中的 FEX opcode 0x82 修正
（`tools/patch-fex-0x82.py`）解決了 `upc.exe` 的 decode failure，但
upc.exe 最終仍因 SteamInfoReceiver 失敗而退出。即使 0x82 修正完整生效，
認證流程也無法完成。uplay stub 在 `UPLAY_Start` 層級繞過整個 upc.exe
流程，兩個修正不衝突，可同時套用。
