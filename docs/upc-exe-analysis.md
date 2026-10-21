# upc.exe 逆向分析報告

**文件**：upc.exe  
**大小**：17 MB (17,826,816 bytes)  
**類型**：PE32 (x86-32) GUI 可執行文件  
**簽名**：Authenticode 代碼簽名 (RVA 0x10C2000, ~15KB)  
**版權**：Ubisoft Entertainment  
**產品**：Ubisoft Connect v174.2.13389（前身：Uplay）  
**編譯器**：MSVC (推測 Visual C++ 2015–2019)

---

## 一、PE 結構

| 節區       | 虛擬地址     | 虛擬大小   | 文件大小   | 說明                              |
|------------|-------------|-----------|-----------|-----------------------------------|
| `.text`    | 0x00401000  | 0xFC22A2  | **0x0**   | 代碼區 — 虛擬節，RawSize=0，由 UBX 打包器在運行時解壓 |
| `.rdata`   | 0x013C4000  | 0x37AC40  | **0x0**   | 只讀數據 — 虛擬節，同上            |
| `.data`    | 0x0173F000  | 0x125650  | **0x0**   | 全局變量 — 虛擬節，同上            |
| `.fptable` | 0x01865000  | 0x80      | **0x0**   | 函數指針表 — 虛擬節，同上          |
| `.ubx0`    | 0x01866000  | 0x64C989  | **0x0**   | UBX 打包器工作區 — 虛擬節         |
| `.ubx1`    | 0x01EB3000  | 0x1DC     | 0x200     | UBX 節描述符表（512 bytes on disk）|
| `.ubx2`    | 0x01EB4000  | 0x100D1A4 | **0x100D200** | **打包代碼數據（16.8 MB）**   |
| `.rsrc`    | 0x02EC2000  | 0xB3F7E   | 0xB4000   | 資源（~738 KB：圖標、版本信息）    |
| `.reloc`   | 0x02F76000  | 0x6B8     | 0x800     | 基址重定位表                       |

**結論**：實際文件幾乎只有 `.ubx2`（打包代碼）和 `.rsrc`（資源）有磁盤數據，其他節區在文件中不佔空間，由打包器在運行時解壓填充。

---

## 二、UBX 自定義打包器架構

Ubisoft 在 Ubisoft Connect 中使用名為 **UBX** 的自製代碼壓縮方案，三個特殊節區協同工作：

```
磁盤上的文件結構：
┌──────────────────────────────────┐
│ .ubx1  （512 B）  節描述符表     │  ← 記錄各節解壓後的目標 VA 與參數
│ .ubx2  （16.8MB） 打包代碼數據  │  ← 所有代碼+數據壓縮後的載荷
│ .rsrc  （738KB）  資源           │
│ .reloc （2KB）    重定位表        │
└──────────────────────────────────┘

進程加載後（運行時）：
┌──────────────────────────────────────────────────────────┐
│ .text    (0x401000, ~16MB)  ← 從 .ubx2 解壓填充          │
│ .rdata   (0x13C4000, ~3.5MB) ← 同上                      │
│ .data    (0x173F000, ~1.2MB) ← 同上                      │
│ .fptable (0x1865000, 128B)  ← 同上                       │
│ .ubx0    (0x1866000, ~6.4MB) ← UBX 打包器自身工作內存    │
│ [原始 .ubx2 內容已完成使命]                               │
└──────────────────────────────────────────────────────────┘
```

### 執行入口點
- **EP**：`0x01BC1350` — 位於 `.ubx2` 節內
- 啟動時首先執行打包器代碼（在 `.ubx2` 中），完成所有節的解壓後跳轉至真正的 `WinMain`

### .ubx1 描述符表（部分）
`.ubx1` 包含 22 個 8-byte 條目，每條記錄一個解壓目標地址：

| 索引 | 目標 VA       |
|------|-------------|
| [0]  | 0x021EF724   |
| [1]  | 0x8000006F   |
| [2]  | 0x029DA802   |
| [3]  | 0x023FC7A0   |
| …    | …            |

---

## 三、導出函數（EAT）— 22 個 Argon2 函數

upc.exe 導出完整的 **Argon2 密碼哈希庫** API，供其他 Ubisoft 組件（DLL、插件）調用：

| 序號 | 函數名                   | 用途                         |
|------|--------------------------|------------------------------|
| 1    | `argon2_ctx`             | 通用上下文執行（指定算法類型）|
| 2    | `argon2_encodedlen`      | 計算編碼哈希的輸出長度        |
| 3    | `argon2_error_message`   | 將錯誤碼轉為可讀字符串        |
| 4    | `argon2_hash`            | 高層哈希 API（自動選類型）    |
| 5    | `argon2_type2string`     | 算法類型轉字符串              |
| 6    | `argon2_verify`          | 驗證密碼與哈希是否匹配        |
| 7    | `argon2_verify_ctx`      | 帶上下文的驗證                |
| 8    | `argon2d_ctx`            | Argon2d：抗 GPU，防側信道弱   |
| 9    | `argon2d_hash_encoded`   | Argon2d 生成 PHC 格式哈希     |
| 10   | `argon2d_hash_raw`       | Argon2d 生成原始字節哈希      |
| 11   | `argon2d_verify`         | Argon2d 驗證                  |
| 12   | `argon2d_verify_ctx`     | Argon2d 帶上下文驗證          |
| 13   | `argon2i_ctx`            | Argon2i：抗側信道，防 GPU 弱  |
| 14   | `argon2i_hash_encoded`   | Argon2i 生成 PHC 格式哈希     |
| 15   | `argon2i_hash_raw`       | Argon2i 生成原始字節哈希      |
| 16   | `argon2i_verify`         | Argon2i 驗證                  |
| 17   | `argon2i_verify_ctx`     | Argon2i 帶上下文驗證          |
| 18   | `argon2id_ctx`           | Argon2id：兼顧兩者（推薦用）  |
| 19   | `argon2id_hash_encoded`  | Argon2id 生成 PHC 格式哈希    |
| 20   | `argon2id_hash_raw`      | Argon2id 生成原始字節哈希     |
| 21   | `argon2id_verify`        | Argon2id 驗證                 |
| 22   | `argon2id_verify_ctx`    | Argon2id 帶上下文驗證         |

**意義**：Argon2 是 2015 年密碼哈希競賽（PHC）冠軍算法，專為抵抗暴力破解設計。Ubisoft Connect 用它哈希本地憑證（帳號密碼緩存），並將 API 暴露給同套件其他模組（如 `Disrupt_64.dll`）。

---

## 四、導入函數（IAT）— 22 個 DLL

| DLL                                      | 主要用途                    |
|------------------------------------------|-----------------------------|
| `KERNEL32.dll`                           | 核心 Win32 API              |
| `USER32.dll`                             | 窗口、消息循環              |
| `GDI32.dll`                              | 基礎繪圖                    |
| `ADVAPI32.dll`                           | 注冊表、服務、加密           |
| `SHELL32.dll`                            | Shell 集成（文件關聯等）     |
| `ole32.dll` / `OLEAUT32.dll`             | COM / OLE 自動化             |
| `gdiplus.dll`                            | GDI+ 圖像渲染               |
| `IMM32.dll`                              | 輸入法（IME）支持            |
| **`libcef.dll`**                         | **Chromium Embedded Framework — 內嵌瀏覽器（Ubisoft Connect 商店/UI）** |
| `WINHTTP.dll`                            | HTTP/HTTPS 客戶端網絡請求   |
| `WS2_32.dll` / `WSOCK32.dll`            | Winsock 網絡套接字          |
| `IPHLPAPI.DLL`                           | 網絡接口枚舉（NAT 穿透）     |
| `RPCRT4.dll`                             | RPC 運行時（`UuidCreate`）  |
| `CRYPT32.dll`                            | 憑證、CMS 解析               |
| **`bcrypt.dll`**                         | Windows 加密 API（`BCryptGenRandom` 等）|
| **`WINTRUST.dll`**                       | `WinVerifyTrust` — 驗證 Authenticode 簽名 |
| `Secur32.dll`                            | SSPI / Kerberos / NTLM      |
| `d3d9.dll`                               | Direct3D 9 渲染              |
| `api-ms-win-core-winrt-l1-1-0.dll`      | WinRT 核心 API              |
| `api-ms-win-core-winrt-string-l1-1-0.dll`| WinRT 字符串               |

---

## 五、安全特性

### 5.1 Authenticode 代碼簽名
- `Security` 數據目錄：RVA `0x10C2000`，大小 `0x39F8`（~15KB）
- 包含 Ubisoft 官方簽名證書，驗證文件完整性

### 5.2 TLS 回調（Thread Local Storage）
- `TLS` 數據目錄：RVA `0x1B434E4`
- TLS 回調在 `main` 之前由 Windows 加載器執行，常用於：
  - 反調試檢測
  - 打包器初始化
  - 環境完整性校驗

### 5.3 WinVerifyTrust 自我驗證
- 導入 `WINTRUST.dll` → `WinVerifyTrust`
- 推測在啟動時驗證自身及關鍵 DLL 的 Authenticode 簽名，防止文件被篡改

### 5.4 bcrypt 加密基礎
- 導入 `bcrypt.dll`（Windows CNG API）
- 用於安全隨機數生成、對稱加密、密鑰派生等

---

## 六、數據目錄摘要

| 目錄       | RVA         | 大小    | 說明                |
|------------|-------------|---------|---------------------|
| Export     | 0x29AC528   | 0x27E   | Argon2 導出表        |
| Import     | 0x29F36A0   | 0x1CC   | 22 個 DLL 的 IAT     |
| Resource   | 0x2AC2000   | 0xB3F7E | 圖標、版本信息        |
| Security   | 0x10C2000   | 0x39F8  | Authenticode 簽名    |
| TLS        | 0x1B434E4   | 0x18    | TLS 回調             |
| LoadConfig | 0x2AB8C80   | 0x40    | 安全 Cookie、GFETs  |
| Debug      | 0x2AB9240   | 0x54    | 調試信息目錄         |
| BaseReloc  | 0x2B76000   | 0x6B8   | 基址重定位           |

---

## 七、身份確認

| 字段           | 值                                    |
|----------------|---------------------------------------|
| FileDescription| Ubisoft Connect                       |
| ProductName    | Ubisoft Connect                       |
| CompanyName    | Ubisoft                               |
| ProductVersion | 174.2.13389                           |
| LegalCopyright | © Ubisoft Entertainment               |
| 前身名稱       | Uplay（2020 年更名為 Ubisoft Connect）|

---

## 八、總結

`upc.exe` 是 **Ubisoft Connect v174.2.13389** 的主進程（前身 Uplay），是 Ubisoft 的遊戲啟動/商店/社交平台客戶端。主要特征：

1. **UBX 自製打包器**：所有代碼（~21 MB 解壓）壓縮成 16.8 MB 的 `.ubx2`，在 EP 處由打包器自解壓，有效阻礙靜態分析與逆向。

2. **Argon2 密碼哈希導出**：完整暴露 22 個 Argon2 API，供 `Disrupt_64.dll` 或其他 Ubisoft 模組動態調用，用於本地帳號憑證的安全哈希存儲。

3. **Chromium 內嵌瀏覽器**（`libcef.dll`）：Ubisoft Connect 的商店界面、好友系統、新聞頁均為 CEF 渲染的 Web 內容。

4. **多層安全機制**：Authenticode 自簽名 + `WinVerifyTrust` 自我驗證 + TLS 回調 + bcrypt 加密 API，構成完整的客戶端安全棧。

5. **真正的主程序邏輯**在解壓後的 `.text`（~16 MB 代碼）中，靜態分析只能看到打包殼，動態分析（掛調試器）才能觀察解壓後的真實代碼。
