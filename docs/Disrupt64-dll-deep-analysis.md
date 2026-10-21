# Disrupt_64.dll 深度反彙編分析報告

**基礎文件**：延伸自《Disrupt_64.dll 逆向分析報告》（靜態 PE 結構分析）  
**工具**：Capstone 5.0.7（x86-64 反彙編引擎）  
**分析重點**：DLL 入口存根、RunGameEx 主函數、RunGame 包裝器、G4 框架函數

---

## 一、DLL 入口存根分析（EP Stub）

**位置**：RVA `0x4988021`，節區 `.rdata`（76 位元組有效節）  
**VA**：`0x184988021`

```asm
; DllMain 入口存根（76 位元組）
; 參數: RCX=hinstDLL, RDX=fdwReason, R8=lpvReserved
0x184988021  mov qword ptr [rip - 0x28], rcx   ; 保存 hinstDLL
0x184988028  mov qword ptr [rip - 0x27], rdx   ; 保存 fdwReason
0x18498802F  mov qword ptr [rip - 0x26], r8    ; 保存 lpvReserved
0x184988036  mov qword ptr [rip - 0x25], r9    ; 保存 R9（預留）
0x18498803D  cmp  rdx, 1                        ; fdwReason == DLL_PROCESS_ATTACH?
0x184988041  jne  0x1882657bb                   ; 非 ATTACH → 跳至簡短處理路徑
0x184988047  jmp  0x184986151                   ; DLL_PROCESS_ATTACH → 跳入 .tls em 真正 DllMain
```

### 分析

| 項目 | 說明 |
|------|------|
| 設計模式 | **Trampoline Stub**（彈跳板存根） |
| fdwReason 路由 | `DLL_PROCESS_ATTACH`（=1）→ 真正 DllMain（0x184986151），其餘 → 0x1882657bb（快速返回或清理） |
| 真正 DllMain VA | `0x184986151`（RVA `0x4986151`），位於 `.tls em` 主代碼節 |
| 非 ATTACH 處理 VA | `0x1882657bb`（RVA `0x2657bb`），位於 `.edata a` 節 |
| 目的 | 節省 `.rdata` 空間；`.rdata` 僅 76 位元組，真正邏輯在 118 MB 的 `.tls em` 中 |

**結論**：EP 是一個「6 條指令」的參數轉發存根，根據 `fdwReason` 做條件跳轉，將控制權傳給 `.tls em` 段中真正的初始化邏輯。這種設計讓 `.rdata` 保持最小化，使靜態分析者看到的入口點幾乎沒有可分析的內容。

---

## 二、RunGame 與 RunGameEx 關係

### RunGame（Legacy 包裝器）
**RVA**：`0x72E0A9C`，VA：`0x1872E0A9C`

```asm
sub  rsp, 0x38
lea  rax, [rip - 0x2e0d]          ; 預設 lpCmdLine（NULL 或空字符串）
lea  r9,  [rip - 0x104f]          ; nShowCmd 預設值
mov  qword ptr [rsp + 0x20], rax  ; 第 5 個參數（RunGameEx 的第 5 arg）
call RunGameEx                     ; 直接跳入 RunGameEx 0x1872E0AC0
add  rsp, 0x38
ret
```

RunGame 只有 **6 條有效指令**，僅填充預設參數後立即呼叫 RunGameEx。兩者入口地址僅差 0x24 位元組（`0x72E0A9C` vs `0x72E0AC0`）。

---

## 三、RunGameEx 深度分析

**RVA**：`0x72E0AC0`，VA：`0x1872E0AC0`，FileOff：`0x36A62C0`

### 3.1 函數序言（Frame Setup）

```asm
; === 棧框建立（x64 呼叫慣例）===
0x1872E0AC0  mov  rax, rsp
0x1872E0AC3  mov  qword ptr [rax + 0x10], rbx  ; 保存 RBX
0x1872E0AC7  mov  qword ptr [rax + 0x18], rsi  ; 保存 RSI
0x1872E0ACB  mov  qword ptr [rax + 0x20], rdi  ; 保存 RDI
0x1872E0ACF  mov  qword ptr [rax + 8], rcx     ; 保存 HINSTANCE（第 1 參數）
0x1872E0AD3  push rbp
0x1872E0AD4  push r12
0x1872E0AD6  push r13
0x1872E0AD8  push r14                           ; r14 = HINSTANCE（稍後使用）
0x1872E0ADA  push r15
0x1872E0ADC  lea  rbp, [rax - 0xd8]            ; 建立自訂 RBP 框架
0x1872E0AE3  sub  rsp, 0x1b0                   ; 分配 432 位元組本地變量空間
```

**棧框大小**：5 push（40 位元組）+ `sub rsp, 0x1b0`（432 位元組）= **472 位元組**  
**局部空間**：rbp-0x18 到 rbp+0xe0 之間的變量區域

### 3.2 參數保存

```asm
0x1872E0AEA  mov  r14, rcx     ; r14 = HINSTANCE（貫穿整個函數使用）
0x1872E0AED  lea  rcx, [rbp - 0x60]
0x1872E0AF1  mov  r13, r9      ; r13 = 4th param（nShowCmd）
```

### 3.3 Phase 1：CRT / 安全 Cookie 初始化

```asm
0x1872E0AF4  call 0x184a9fd60  ; 初始化函數（以 [rbp-0x60] 為參數）
```

**推測**：這是 CRT 初始化或安全 Cookie 初始化（等同於 `__security_init_cookie`）。被呼叫的函數 RVA `0x4a9fd60` 位於 `.tls em` 節中。

### 3.4 Phase 2：命令列解析

```asm
0x1872E0AFE  xor  r15d, r15d               ; r15 = 0（計數器）
0x1872E0B05  lea  rax, [rip - 0x38ad16c]   ; RVA→ 指向命令列關鍵詞表
0x1872E0B11  mov  qword ptr [rbp-0x10], rax
0x1872E0B33  call qword ptr [rip+0x1161bff] ; IAT: GetCommandLineW
0x1872E0B41  call qword ptr [rip+0x1162941] ; IAT: CommandLineToArgvW（argvW, &argc 存至 [rsp+0x58]）
```

```asm
; 命令列參數循環（解析 -nosplash 等標誌）
LOOP:
0x1872E0B62  mov  rdx, qword ptr [r15]  ; r15 指向關鍵詞表條目
0x1872E0B65  mov  rcx, qword ptr [rsi]  ; rsi 指向 argvW 當前參數
0x1872E0B68  call qword ptr [rip+0x11625ea]  ; IAT: lstrcmpiW（不區分大小寫比較）
0x1872E0B6E  test eax, eax
0x1872E0B70  je   MATCH                 ; 匹配 → 設標誌
; ... 迭代邏輯
```

**設計**：引擎維護一個命令列關鍵詞表，循環比對每個 `argv` 參數。通過 `lstrcmpiW` 做大小寫不敏感匹配，匹配的參數設置對應標誌位（存於 rbp 附近）。

### 3.5 Phase 3：引擎子系統初始化

```asm
; 第一個子系統初始化（可能是文件系統 / 配置）
0x1872E0BB0  lea  rcx, [rip - 0x335ef1f]   ; 配置字符串指針
0x1872E0BB7  lea  rdx, [rip - 0x3dca1e0]   ; 模塊名稱
0x1872E0BB7  call 0x184b05690               ; 子系統 Init #1

; 第二個子系統初始化（可能是日誌 / 控制台）
0x1872E0BBC  lea  rdx, [rip - 0x3dca1f3]
0x1872E0BC3  lea  rcx, [rip - 0x32f9e2a]
0x1872E0BCA  call 0x185f08d1e               ; 子系統 Init #2
```

### 3.6 Phase 4：命令列標誌讀取 & 應用

```asm
; 讀取已解析的標誌（-nosplash 等）
0x1872E0BCF  movzx eax, byte ptr [rip - 0x32f9dfc]   ; 讀全局標誌 A
0x1872E0BD6  cmp   byte ptr [rsp + 0x51], r15b        ; 比較解析結果
0x1872E0BDB  cmovne eax, ebx                           ; 條件移動更新
0x1872E0BDE  mov   byte ptr [rip - 0x32f9e0a], al     ; 寫回全局標誌

; 推測為 DRM/平台驗證
0x1872E0BE4  call  0x18700cf7f
```

### 3.7 Phase 5：平台句柄 & 模塊分配

```asm
0x1872E0BF6  mov  rax, qword ptr [rip - 0x32aa575]   ; 讀平台 HANDLE（Steam/Uplay）
0x1872E0BFD  test rax, rax
0x1872E0C00  jne  HAVE_HANDLE                          ; 已有句柄 → 跳過
0x1872E0C02  cmp  dword ptr [rip - 0x32aa585], r15d   ; 平台類型 == 0?
0x1872E0C09  jne  INIT_PLATFORM

; 動態分配平台對象
0x1872E0C0B  lea  ecx, [rdi + 0xc]    ; 對象大小
0x1872E0C0E  mov  edx, edi
0x1872E0C10  call 0x184add5f0          ; 分配器（類似 new/malloc）
0x1872E0C1A  mov  rcx, rax
0x1872E0C1D  call 0x186fd5194          ; 構造函數（初始化平台對象）

HAVE_HANDLE:
0x1872E0C31  add  dword ptr [rip - 0x32aa5b3], ebx   ; 引用計數 +1
0x1872E0C3F  call 0x18702c59b          ; 平台連接/驗證
```

### 3.8 RunGameEx 執行流摘要

```
RunGameEx(HINSTANCE hInst, LPWSTR cmdLine, HINSTANCE prev, int nShow)
│
├── [Frame] 建立 472 位元組棧框，保存 rbp r12-r15
├── [Phase 1] CRT / Security Cookie 初始化
│    └── call 0x184a9fd60
├── [Phase 2] 命令列解析
│    ├── GetCommandLineW
│    ├── CommandLineToArgvW
│    └── lstrcmpiW 循環比對關鍵詞（-nosplash 等）
├── [Phase 3] 子系統初始化
│    ├── 文件系統 / 配置模塊 Init
│    └── 日誌 / 控制台模塊 Init
├── [Phase 4] 標誌讀取 & 平台驗證
│    └── DRM/Uplay 驗證入口
└── [Phase 5] 平台對象分配 & 連接
     ├── malloc/new（平台對象，0xc+rdi 位元組）
     ├── 構造函數初始化
     └── 引用計數管理
```

---

## 四、G4 框架（Ubisoft 內部性能分析工具）— 完整反彙編

G4 是 Ubisoft 內部的超輕量性能採樣/調試框架。5 個導出函數全部是 **1–9 條指令**的極簡存根。

### G4_GetSP — 獲取棧指針
**RVA** `0x762AA60`

```asm
mov rax, rsp   ; 返回當前 RSP
ret
```

### G4_GetBP — 獲取幀指針
**RVA** `0x762AA65`

```asm
mov rax, rbp   ; 返回當前 RBP
ret
```

### G4_GetNonVolatileRegisters — 保存所有非易失寄存器
**RVA** `0x762AA69`，接收一個指針 `RCX` 作為輸出緩衝

```asm
mov [rcx + 0x00], rbx   ; 非易失寄存器 1/8
mov [rcx + 0x08], rbp   ; 非易失寄存器 2/8
mov [rcx + 0x10], rsi   ; 非易失寄存器 3/8
mov [rcx + 0x18], rdi   ; 非易失寄存器 4/8
mov [rcx + 0x20], r12   ; 非易失寄存器 5/8
mov [rcx + 0x28], r13   ; 非易失寄存器 6/8
mov [rcx + 0x30], r14   ; 非易失寄存器 7/8
mov [rcx + 0x38], r15   ; 非易失寄存器 8/8
ret
```

緩衝區佈局（64 位元組）：

| 偏移 | 寄存器 | 說明 |
|------|--------|------|
| +0x00 | RBX | 基址寄存器 |
| +0x08 | RBP | 幀指針 |
| +0x10 | RSI | 來源指針 |
| +0x18 | RDI | 目標指針 |
| +0x20 | R12 | 通用非易失 |
| +0x28 | R13 | 通用非易失 |
| +0x30 | R14 | 通用非易失（RunGameEx 中保存 HINSTANCE） |
| +0x38 | R15 | 通用非易失 |

### G4_RestoreNonVolatileRegisters — 恢復所有非易失寄存器
**RVA** `0x762AA89`

```asm
mov rbx, [rcx + 0x00]
mov rbp, [rcx + 0x08]
mov rsi, [rcx + 0x10]
mov rdi, [rcx + 0x18]
mov r12, [rcx + 0x20]
mov r13, [rcx + 0x28]
mov r14, [rcx + 0x30]
mov r15, [rcx + 0x38]
ret
```

G4_GetNonVolatileRegisters 和 G4_RestoreNonVolatileRegisters 地址只差 **0x20 位元組**（`0x762AA69` vs `0x762AA89`）並緊密排布——這是編譯器打包的兩個互補函數對。

### G4_ResetECX — 清零 ECX
**RVA** `0x763C640`

```asm
xor ecx, ecx   ; ECX = 0（同時清零 RCX）
ret
```

**用途**：在使用 G4 採樣時，可能需要 `ECX` 為 0 以避免寄存器汙染。被外部 G4 採樣基礎設施（通過導出表）在特定採樣點調用。

### G4 框架設計說明

| 函數 | 指令數 | 功能 |
|------|--------|----- |
| `G4_GetSP` | 2 | 讀 RSP |
| `G4_GetBP` | 2 | 讀 RBP |
| `G4_GetNonVolatileRegisters` | 9 | 保存 8 個非易失寄存器到 64B 緩衝 |
| `G4_RestoreNonVolatileRegisters` | 9 | 從 64B 緩衝恢復 8 個非易失寄存器 |
| `G4_ResetECX` | 2 | 清零 ECX |

**設計意圖**：G4 採樣器在外部（例如性能監控驅動）注入採樣時，通過導出表呼叫這些函數來捕獲調用棧快照，無需訪問 PDB 符號。`GetSP`+`GetBP`+`GetNonVolatileRegisters` 組合可完整重建 x64 調用棧的幀鏈，用於離線分析。

---

## 五、DLL 入口點流向圖（完整）

```
Windows DLL Loader
│
├── TLS 回調（RVA 0x3C0D900，在 EP 之前執行）
│    └── [解壓/初始化邏輯]
│
└── EP（RVA 0x4988021，DllMain Stub）
     │
     ├── 保存 RCX/RDX/R8/R9（DllMain 4 個參數）
     ├── cmp fdwReason, DLL_PROCESS_ATTACH(1)
     │
     ├── [DLL_PROCESS_ATTACH]
     │    └── jmp → 0x184986151（真正 DllMain，.tls em）
     │
     └── [DLL_THREAD_ATTACH / DETACH / 其他]
          └── jmp → 0x1882657bb（快速路徑，.edata a）


WatchDogs2.exe
│
└── RunGame(hInst, NULL, NULL, nShow)     ← Legacy 入口（6 條指令包裝器）
     └── call RunGameEx(hInst, NULL, NULL, nShow, "<default_cmdline>")

     RunGameEx(hInst, cmdLine, prev, nShow)
     │
     ├── [Frame] RSP-472，保存 RBP r12-r15
     ├── [CRT Init]    call 0x184a9fd60
     ├── [Cmd Parse]   GetCommandLineW → CommandLineToArgvW → lstrcmpiW 循環
     ├── [Subsys Init] 文件系統 + 日誌/控制台初始化
     ├── [Flags]       應用命令列標誌到全局配置
     ├── [DRM]         call 0x18700cf7f（Uplay/Steam 驗證）
     └── [Platform]    分配/初始化平台對象，引用計數管理
          └── → 完整遊戲引擎主循環（繼續於 .tls em）
```

---

## 六、TLS 回調入口

**TLS 目錄 RVA**：`0x3C0D900`  
**回調表 VA**：`0x183516870`（RVA `0x3516870`，位於 `.edata a` 節，有磁盤數據）

TLS 回調比 EP 更早由 Windows 加載器執行，是 Disrupt 引擎的初始化前置步驟。根據整體架構推斷，TLS 回調可能負責：
1. 驗證代碼簽名完整性（在執行任何代碼前）
2. 初始化內存池（為後續代碼解壓提供空間）
3. 反調試/反分析檢查（IsDebuggerPresent、硬件斷點檢測）

---

## 七、關鍵地址速查表

| 符號 | RVA | VA | FileOff |
|------|-----|----|---------|
| DLL EP Stub | 0x4988021 | 0x184988021 | 0xD4E621 |
| 真正 DllMain | 0x4986151 | 0x184986151 | N/A（.tls em 內） |
| RunGame | 0x72E0A9C | 0x1872E0A9C | 0x36A629C |
| RunGameEx | 0x72E0AC0 | 0x1872E0AC0 | 0x36A62C0 |
| G4_GetSP | 0x762AA60 | 0x18762AA60 | 0x39F0260 |
| G4_GetBP | 0x762AA65 | 0x18762AA65 | 0x39F0265 |
| G4_GetNonVolatileRegisters | 0x762AA69 | 0x18762AA69 | 0x39F0269 |
| G4_RestoreNonVolatileRegisters | 0x762AA89 | 0x18762AA89 | 0x39F0289 |
| G4_ResetECX | 0x763C640 | 0x18763C640 | 0x3A01E40 |
| AmdPowerXpressRequestHighPerformance | 0x3E3D620 | 0x183E3D620 | 0x943C20 |
| TLS 回調表 | 0x3516870 | 0x183516870 | 0x1CE70 |
