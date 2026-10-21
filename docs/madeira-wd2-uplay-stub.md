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
