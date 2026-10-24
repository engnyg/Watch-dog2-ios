# UBX 打包器反偵錯機制分析

**目的**：了解 UPC 解包後執行階段的反偵錯行為，供 iOS 移植研究參考。  
**範圍**：ICEBP 自我檢查 + NtSetInformationThread 重複呼叫。

---

## 一、執行階段時序

```
.ubx2 EP (0x1BC1350)
  │
  ├─► [Phase 1] 解壓：.ubx2 → .text/.rdata/.data/.fptable
  │
  ├─► [Phase 2] 反偵錯初始化            ← 報錯前所在位置
  │    ├── NtSetInformationThread × N    (ThreadHideFromDebugger)
  │    ├── ICEBP 自我檢查序列
  │    └── PEB/heap 旗標檢查
  │
  └─► [Phase 3] 跳轉至真正 WinMain
```

---

## 二、ICEBP（0xF1）自我檢查

### 2.1 ICEBP 是什麼

`0xF1` 是 Intel 未文件化的單位元組指令，俗稱 **ICEBP**（In-Circuit Emulator BreakPoint）或 INT1。
執行後固定產生 `STATUS_SINGLE_STEP`（0x80000004）例外——無論 TF 旗標是否設定。

### 2.2 打包器的用法模式

UBX 用 ICEBP 進行三層檢查，每層都是在 SEH/VEH 框架內執行：

#### 層 A — 偵錯器存在性

```
設置 SEH handler
  db 0xF1           ; ICEBP → 一定觸發例外
handler:
  ExceptionCode == EXCEPTION_SINGLE_STEP?
  → 是：沒有偵錯器攔截，繼續
  → 否 / handler 未被呼叫：偵錯器攔截了例外，設 bad_flag
```

沒有偵錯器時，VEH/SEH 正常接收到例外並繼續執行。
有用戶態偵錯器（如 x64dbg / WinDbg）時，偵錯器預設將 EXCEPTION_SINGLE_STEP 標為 first-chance，
若偵錯器未主動 pass 例外（或 handler 計時超時），UBX 就判定偵錯器存在。

#### 層 B — 硬體中斷點偵測

```
執行 ICEBP → 進入 handler
  讀取 ExceptionRecord→ContextRecord→Dr0..Dr7
  若 Dr0|Dr1|Dr2|Dr3 ≠ 0 → 硬體 BP 已設定 → bad_flag
  若 Dr7 & 0xFF ≠ 0      → BP 啟用位非零  → bad_flag
```

ICEBP 的 handler 會收到觸發當下完整的執行緒 CONTEXT，包括 DR 暫存器，
從而得知是否有人在程式碼或資料上設置硬體中斷點。

#### 層 C — 程式碼完整性（CRC 同步點）

```
crc32_before = crc32(code_region_start, len)
  db 0xF1           ; 作為「計算邊界」同步點
  ICEBP handler 內再計算一次 crc32
crc32_after = crc32(code_region_start, len)
assert crc32_before == crc32_after == expected_value
```

利用 ICEBP 例外作為精確的同步邊界，比較前後 CRC，
偵測是否有人在這段程式碼上打了 inline hook 或記憶體補丁。
這也是為什麼「同一段程式在報錯前剛做完 ICEBP 自我檢查」——ICEBP 本身就是完整性驗證的一部分。

---

## 三、NtSetInformationThread 重複呼叫

### 3.1 呼叫參數

```c
NtSetInformationThread(
    hThread,
    ThreadHideFromDebugger,   // ThreadInformationClass = 0x11 (17)
    NULL,
    0
);
```

### 3.2 為什麼重複呼叫

| 呼叫次數 | 目的 |
|---------|------|
| 第 1 次 | 隱藏主執行緒 |
| 第 2 次 | 隱藏解壓工作執行緒（如有多執行緒解壓） |
| 第 3+ 次 | 隱藏後續動態建立的執行緒（TLS 回調執行緒、Argon2 執行緒等） |

每個 `ThreadHideFromDebugger` 呼叫都是**針對單一執行緒**，不是全域設定，
所以打包器為每個新建立的執行緒都要呼叫一次。

### 3.3 效果

被隱藏的執行緒：
- 繼續正常執行
- 觸發的任何例外（包括 ICEBP 的 STATUS_SINGLE_STEP）**不會**傳遞給已附加的偵錯器
- 從偵錯器角度看，執行緒「消失了」

這也解釋了為什麼 ICEBP 是有效的：在執行緒被隱藏之後，即使 ICEBP 觸發例外，
偵錯器也收不到通知——只有進程內部的 SEH/VEH handler 能接收。

---

## 四、其他推測存在的內部檢查

根據 UBX 同系列打包器（Ubisoft AC 系列）的已知行為，解包後還可能進行：

| 檢查類型 | 方法 | 目標值 |
|---------|------|-------|
| PEB.BeingDebugged | `fs:[0x30]+2`（x86）| 無偵錯器時 = 0 |
| PEB.NtGlobalFlag | `fs:[0x30]+0x68` | 無偵錯器時 = 0，有時 = 0x70 |
| Heap 旗標 | `HeapBase+0x0C` | 無偵錯器時 HEAP_GROWABLE (2)；有偵錯器時多出 0x50 |
| ProcessDebugPort | `NtQueryInformationProcess(7)` | 無偵錯器時 = 0 |
| RDTSC 計時 | 前後差值 | 偵錯器單步會產生毫秒級延遲 |
| 執行緒計數 | `NtQuerySystemInformation` | 比對預期執行緒數 |

---

## 五、對 iOS 移植的意義

**macOS/ARM64 二進位不會有以上 Windows 特有的檢查**：

- `NtSetInformationThread`：Windows NT 系統呼叫，macOS 不存在
- ICEBP（0xF1）：x86 指令，ARM64 沒有等效指令
- PEB 旗標：Windows 進程環境塊，macOS 無對應結構

因此：
1. 若取得 macOS 原生 ARM64 二進位，上述檢查**全部不存在**，移植路徑的主要障礙是引擎初始化、渲染 API（Metal vs DirectX）和 UPC 線上驗證流程，而不是反偵錯邏輯。
2. 若分析的是 Windows 版行為（供參考），這些檢查解釋了為什麼在偵錯器下啟動 UPC 時，執行會在解包後的早期階段終止。

---

## 六、後續逆向方向

若需要進一步了解 UBX 內部檢查細節，建議切入點：

1. **TLS 回調**：`TLS` 目錄 RVA `0x1B434E4`——TLS 回調在 EP 之前執行，可能包含最早期的環境檢查。
2. **EP 附近的 call 圖**：從 `0x1BC1350` 開始，追蹤前 20 個 call，找到第一個設置 SEH frame 並執行 `0xF1` 的函式。
3. **NtSetInformationThread 呼叫位置**：用靜態掃描找所有 `mov ecx, 0x11` 後接 `call NtSetInformationThread` 的指令序列，定位每次呼叫的上下文。
4. **Heap 旗標操作**：搜尋 `0x40000003`（HEAP_CREATE_ENABLE_EXECUTE）或 `NtQueryVirtualMemory` 呼叫，了解記憶體保護驗證邏輯。
