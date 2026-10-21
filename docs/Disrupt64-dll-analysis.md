# Disrupt_64.dll 逆向分析報告

**文件**：Disrupt_64.dll  
**大小**：132.5 MB (138,910,128 bytes)  
**類型**：PE32+ (x86-64) DLL  
**簽名**：Authenticode 代碼簽名 (RVA 0x8478200, ~6KB)  
**內部名稱**：`MIXED.dll`（導出表記錄名）  
**編譯時間**：2017-07-25 13:52:48 UTC  
**編譯器**：MSVC + MSVCR110.dll / MSVCP110.dll (Visual C++ 2012)  
**引擎**：Ubisoft Disrupt Engine（《看門狗 2》專用）

---

## 一、PE 結構

| 節區       | RVA         | 虛擬大小    | 磁盤大小    | 說明                                      |
|------------|-------------|------------|------------|------------------------------------------|
| `.reloc`   | 0x001000    | 0x34F9000  | **0x0**    | **55 MB 虛擬佔位**，運行時解壓代碼的目標區域 |
| `.edata a` | 0x34FA000   | 0x8C5000   | 0x8C5000   | 導出數據區（Wwise API 代碼）             |
| `.idata`   | 0x3DBF000   | 0x8961E0   | 0x15A000   | 導入數據（壓縮後）                        |
| `.pdata a` | 0x4656000   | 0x32BC00   | 0x32BC00   | 異常處理展開信息                          |
| `.arch`    | 0x4982000   | 0x600      | 0x600      | 架構描述符                               |
| `.srdata`  | 0x4983000   | 0x1800     | 0x1800     | 靜態只讀數據                              |
| `.sdata`   | 0x4985000   | 0x2AE      | 0x400      | 靜態數據                                 |
| `.data1`   | 0x4986000   | 0x15D      | 0x200      | 數據段1                                  |
| `.text`    | 0x4987000   | 0x1000     | 0x1000     | 文本段（4 KB，僅存根）                    |
| `.rdata`   | 0x4988000   | 0x4C       | 0x200      | **EP 所在**（76 字節，含 DLL 入口跳轉）  |
| **`.tls em`** | 0x4989000 | **0x76BB000** | **0x76BB000** | **118 MB 主代碼段（偽裝為 TLS）** |
| `.code`    | 0xC044000   | 0x6E720    | 0x6EA00    | 資源段（與 Resource 目錄重合）            |

**結論**：真正的遊戲引擎代碼全部在 `.tls em`（118 MB），以偽 TLS 節名掘蓋；`.reloc` 是 55 MB 的虛擬佔位，用於在初始化時接收解壓代碼。

---

## 二、入口點分析

- **DLL EP**：RVA `0x4988021`，位於 `.rdata`＀76 字節節區內）
- `.rdata` 只有 76 字節有效內容，EP 偏移 `0x21` 字節處——推測為一個短跳轉存根，跳入 `.tls em` 中的真正 `DllMain`
- **TLS 回調目錄**：RVA `0x3C0D900`——TLS 回調在 EP 之前由加載器執行，可能包含解壓/初始化邏輯

---

## 三、導出函數（EAT）— 250 個

導出函數可分為四類：

### 3.1 遊戲引擎入口（被 WatchDogs2.exe 調用）

| 序號 | 函數名       | 說明                                          |
|------|------------|-----------------------------------------------|
| 249  | `RunGame`  | 舊版引擎入口（Legacy）                          |
| 250  | `RunGameEx`| **主入口**：`RunGameEx(HINSTANCE, LPWSTR, HINSTANCE, int)` |

### 3.2 Wwise 音效引擎 API（~240 個）

Disrupt_64.dll 直接嵌入完整的 **Audiokinetic Wwise** 音效引擎，並透過導出表暴露全部 API：

| 命名空間                              | 代表函數                             | 功能               |
|--------------------------------------|-------------------------------------|-----------------|
| `AK::SoundEngine`                    | `PostEvent`, `SetRTPCValue`, `Init` | 音效事件、參數、初始化 |
| `AK::MemoryMgr`                      | `Malloc`, `Free`, `CreatePool`      | Wwise 內存池管理    |
| `AK::MusicEngine`                    | `Init`, `Term`, `GetPlayingSegmentInfo` | 互動音樂引擎    |
| `AK::MotionEngine`                   | `RegisterMotionDevice`              | 手柄震動反饵        |
| `AK::Query::SoundEngine`             | `GetRTPCValue`, `GetState`          | 音效狀態查詢        |
| `AK::DynamicDialogue::SoundEngine`   | `ResolveDialogueEvent`              | 動態對話系統        |
| `AK::DynamicSequence::SoundEngine`   | `Open`, `Play`, `Stop`              | 動態音頻序列        |
| `AK::Monitor`                        | `PostCode`, `SetLocalOutput`        | 音效監控/調試       |

Wwise 導出全局變量：
- `?g_DefaultPoolId` — 預設內存池 ID
- `?g_pRTPCMgr` — RTPC（實時參數控制）管理器指標
- `?g_pRegistryMgr` — 遊戲對象注冊表管理器
- `?g_pSwitchMgr` — 音效狀態開關管理器

### 3.3 GPU / 平台輔助函數

| 函數名                            | 說明                                       |
|----------------------------------|-----------------------------------------|
| `AmdPowerXpressRequestHighPerformance` | 強制使用獨立顯卡（AMD Optimus 等效）   |
| `G4_GetSP`                       | 取得樿指標（Ubisoft G4 框架—內部性能分析工具） |
| `G4_GetBP`                       | 取得幀指標                                 |
| `G4_GetNonVolatileRegisters`     | 取得非易失暫存器狀態                        |
| `G4_ResetECX`                    | 重置 ECX 暫存器                             |
| `G4_RestoreNonVolatileRegisters` | 還原非易失暫存器                            |

---

## 四、導入函數（IAT）— 38 個 DLL

### 4.1 標準 Windows API（18 個）

| DLL                  | 主要用途                    |
|----------------------|-----------------------------|
| `KERNEL32.dll`       | 核心 Win32                  |
| `USER32.dll`         | 窗口、消息                  |
| `GDI32.dll`          | 基礎繪圖                    |
| `ADVAPI32.dll`       | 注冊表、服務                |
| `SHELL32.dll`        | Shell 集成                  |
| `ole32.dll`          | COM                         |
| `OLEAUT32.dll`       | OLE 自動化                  |
| `WINMM.dll`          | 多媒體定時器                |
| `COMCTL32.dll`       | 通用控件                    |
| `VERSION.dll`        | 版本資源讀取                |
| `SHLWAPI.dll`        | 路徑/字符串工具             |
| `SETUPAPI.dll`       | 裝置安裝                    |
| `RPCRT4.dll`         | RPC 運行時                  |
| `PSAPI.DLL`          | 進程狀態查詢                |
| `IPHLPAPI.DLL`       | 網路接口枚舉                |
| `WS2_32.dll`         | Winsock 網路                |
| `gdiplus.dll`        | GDI+ 圖像                   |
| `ncrypt.dll`         | 密鑰存儲                    |

### 4.2 DirectX 渲染棧（6 個）

| DLL                     | 用途                          |
|-------------------------|-------------------------------|
| `d3d11.dll`             | DirectX 11 渲染               |
| `d3d9.dll`              | DirectX 9 相容                |
| `dxgi.dll`              | DXGI 交換鏈                   |
| `D3DCOMPILER_46.dll`    | HLSL 著色器編譯                |
| `OPENGL32.dll`          | OpenGL 支援                   |
| `bcrypt.dll`            | Windows CNG 加密               |

### 4.3 NVIDIA GameWorks SDK（3 個）

| DLL                              | 功能                                    |
|----------------------------------|-----------------------------------------|
| `GFSDK_SSAO_D3D11.win64.dll`     | **HBAO+**（Horizon-Based AO+）          |
| `GFSDK_ShadowLib_DX11.win64.dll` | **PCSS**（柔性陰影）                    |
| `GFSDK_Txaa.win64.dll`           | **TXAA**（NVIDIA 時間性抗鍛齒）         |

### 4.4 遊戲平台 / 第三方中間件（7 個）

| DLL                         | 功能                                     |
|-----------------------------|------------------------------------------|
| `uplay_r1_loader64.dll`     | **Ubisoft DRM / Uplay 集成**             |
| `amd_ags_x64.dll`           | AMD GPU Services（Crossfire / GPU 信息） |
| `DINPUT8.dll`               | DirectInput（遊戲控制器/鍵盤）           |
| `XINPUT9_1_0.dll`           | Xbox 控制器支援                          |
| `bink2w64.dll`              | **Bink 2 影片播放器**（過場動畫）        |
| `CRYPT32.dll`               | 憑證/加密                               |
| `WINTRUST.dll`              | Authenticode 驗證                        |

### 4.5 延遲加載（Delay Import）— 2 個

| DLL                 | 功能                                  |
|---------------------|---------------------------------------|
| `steam_api64.dll`   | Steam 平台集成（成就、好友、雲存檔）  |
| `libScePad.dll`     | PlayStation DualShock/DualSense 支援  |

---

## 五、關鍵技術組件

### 5.1 Wwise 音效引擎（嵌入版）
完整的 Audiokinetic Wwise SDK 靜態鏈接進 Disrupt_64.dll，包含：
- SoundEngine（音效事件調度）
- MusicEngine（互動音樂狀態機）
- MotionEngine（手柄震動）
- MemoryMgr（獨立內存池）
- DynamicDialogue（動態語音選擇系統）

### 5.2 NVIDIA GameWorks 三件套
| 技術    | DLL                      | 效果                              |
|---------|--------------------------|-----------------------------------|
| HBAO+   | GFSDK_SSAO_D3D11         | 高品質環境遞蔽（比 SSAO 真實）    |
| PCSS    | GFSDK_ShadowLib_DX11     | 柔陰影（近處清晰 / 遠處模糊）     |
| TXAA    | GFSDK_Txaa               | 時間性 AA，以運動模糊換抗鍛齒     |

### 5.3 多平台支援
- **Steam**：延遲加載（`steam_api64.dll`），PC 版成就/存檔
- **PS4 手柄**：延遲加載（`libScePad.dll`），DualShock 4 觸覺/燈條
- **Xbox 手柄**：靜態鏈接（`XINPUT9_1_0.dll`）
- **Uplay DRM**：靜態鏈接（`uplay_r1_loader64.dll`）

### 5.4 G4 框架（Ubisoft 內部工具）
導出 5 個 `G4_*` 函數——這是 Ubisoft 的內部性能分析/調試框架的殘留接口，用於在生產版本中提供最小化的性能探针。

---

## 六、安全特性

| 特性                     | 詳情                                    |
|--------------------------|-----------------------------------------|
| Authenticode 簽名        | RVA 0x8478200，Ubisoft 官方證書         |
| TLS 回調                 | RVA 0x3C0D900，在 EP 之前執行           |
| Uplay DRM                | `uplay_r1_loader64.dll` 靜態鏈接       |
| `WINTRUST.dll`           | 自身及關鍵 DLL 的簽名驗證               |
| `bcrypt.dll`             | Windows CNG 加密 API                    |
| LoadConfig               | RVA 0x3C0D890，安全 Cookie 保護樿       |

---

## 七、數據目錄摘要

| 目錄        | RVA          | 大小       | 說明                |
|-------------|--------------|-----------|---------------------|
| Export      | 0x8443DD0    | 0x4A69    | 250 個導出函數       |
| Import      | 0x84488A8    | 0x2F8     | 36 個靜態 DLL        |
| Resource    | 0xC044000    | 0x6E720   | 資源（圖標、版本）   |
| Exception   | 0x4656000    | 0x32BBB4  | SEH 展開信息         |
| Security    | 0x8478200    | 0x17B0    | Authenticode 簽名   |
| TLS         | 0x3C0D900    | 0x28      | TLS 回調表          |
| LoadConfig  | 0x3C0D890    | 0x70      | 安全 Cookie、CFG    |
| Debug       | 0x8443D90    | 0x38      | PDB 路徑指標        |
| DelayImport | 0x3DB37D8    | 0x60      | 2 個延遲加載 DLL     |
| BaseReloc   | 0xBF74000    | 0xCF894   | 基址重定位           |

---

## 八、與 WatchDogs2.exe 的關係

```
WatchDogs2.exe（525 KB 啟動器）
    │
    ├── LoadLibraryW("Disrupt_64.dll")    ← 加載本文件
    │
    └── GetProcAddress(hDll, "RunGameEx") ← 取入口函數
         │
         └── RunGameEx(hInst, cmdLine, NULL, nShowCmd)
              │
              └── 完整遊戲引擎接管控制
                   ├── Wwise 音效初始化（SoundEngine::Init）
                   ├── D3D11 渲染器初始化
                   ├── NVIDIA GameWorks（HBAO+ / PCSS / TXAA）
                   ├── Uplay DRM 驗證
                   ├── Steam / PS4 手柄（延遲加載）
                   ├── Bink 2 影片系統（過場動畫）
                   └── 主遊戲循環（.tls em 節，118 MB 代碼）
```

---

## 九、總結

`Disrupt_64.dll` 是《看門狗 2》的**全量遊戲引擎 DLL**，包含：

1. **Ubisoft Disrupt 引擎核心**（`RunGameEx`），118 MB 代碼藏在偽裝成 TLS 的 `.tls em` 節中。

2. **完整 Audiokinetic Wwise 音效引擎**靜態嵌入，導出 240+ API 供外部模組調用。

3. **NVIDIA GameWorks** 三件套（HBAO+、PCSS、TXAA），解釋了為何《看門狗 2》的 NVIDIA 顯卡畫面顯著優於 AMD。

4. **多平台控制器支援**（Xbox XInput、PS4 DualShock、Steam）透過靜態/延遲加載方式在同一 DLL 中共存。

5. 異常的節區命名（`.tls em`、`.edata a`、`.pdata a`）是 Ubisoft 對抗靜態分析的一種輕度混淡手段。
