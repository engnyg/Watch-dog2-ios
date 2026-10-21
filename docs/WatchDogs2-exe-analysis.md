# WatchDogs2.exe 逆向分析报告

**文件**：WatchDogs2.exe  
**大小**：525 KB (537,600 bytes)  
**类型**：PE32+ (x86-64) GUI 可执行文件  
**签名**：Authenticode 代码签名 (RVA 0x81A00, 6KB)  
**版权**：© 2016 Ubisoft Entertainment  
**PDB**：`K:\bin\WatchDogs2.pdb`  
**编译器**：MSVC + MSVCR110.dll (Visual C++ 2012)

---

## 一、PE 结构

| 节区     | RVA        | 大小    | 用途                      |
|----------|-----------|---------|---------------------------|
| `.text`  | 0x1000    | 0xB7B   | 代码（2939 字节，极小）    |
| `.rdata` | 0x2000    | 0xA1A   | 只读数据、IAT、导入表      |
| `.data`  | 0x3000    | 0x370   | 全局变量                   |
| `.pdata` | 0x4000    | 0x114   | 异常处理展开信息           |
| `.rsrc`  | 0x5000    | 0x7F5D0 | 资源（**~522KB，占全文件**）|
| `.reloc` | 0x85000   | 0x24    | 基址重定位                 |

**结论**：几乎整个文件是资源数据，代码逻辑极简单。

---

## 二、资源清单

| 类型 | ID | 大小     | 内容         |
|------|----|---------|-------------- |
| PNG  | 100 | 452 KB  | 启动画面图片  |
| RT_CURSOR (1) | 1–3 | ~12 KB | 鼠标光标 |
| RT_ICON (3)   | 4–7 | ~40 KB | 程序图标 |
| RT_VERSION (16) | 1  | 780 B  | 版本信息 |

嵌入的 PNG（`offset 0x12E00`）是游戏启动画面（Splash Screen）图像，约 442 KB。

---

## 三、导入函数（IAT）

### KERNEL32.dll（核心逻辑相关）
- `LoadLibraryW` — 加载 `Disrupt_64.dll`
- `GetProcAddress` — 获取 `RunGameEx` 函数指针
- `GetModuleFileNameW` — 获取自身路径
- `CreateProcessW` — 启动 `SplashScreen.exe`
- `TerminateProcess` / `GetCurrentProcess` — 传递退出码
- `CreateMutexW` / `OpenMutexW` — 防止重复运行
- `WaitForSingleObject` / `ReleaseMutex` / `CloseHandle` — 互斥体管理

### SHLWAPI.dll
- `StrStrIA` — 不区分大小写子字符串搜索（检测 `-nosplash` 参数）

---

## 四、完整执行流程（逆向重构）

```
EP (0x140001570)
  │
  ├─► sub_140001890   初始化安全 Cookie（栈金丝雀）
  │    └── GetSystemTimeAsFileTime × GetCurrentThreadId × GetTickCount64 × QueryPerformanceCounter
  │
  └─► sub_140001584   CRT 启动包装器（__tmainCRTStartup 等价物）
       │
       ├── __crtGetShowWindowMode
       ├── _initterm_e / _initterm    (全局 C++ 构造函数)
       ├── __getmainargs              (解析 argc/argv/envp)
       │
       └─► sub_1400013a8             ← 实际 WinMain 逻辑
            │
            ├── sub_1400011b4        [检查命令行是否有 -nosplash]
            │    ├── GetCommandLineA
            │    ├── StrStrIA(cmdline, "-nosplash")
            │    └── 若无 -nosplash → sub_1400011e8
            │
            ├── sub_14000111c        [加载 Disrupt_64.dll]
            │    ├── GetModuleFileNameW    (获取 WatchDogs2.exe 所在目录)
            │    ├── _wsplitpath_s         (分解路径: drive+dir+name+ext)
            │    ├── vswprintf_s(buf, "%s%s%s", dir, "\\", "Disrupt_64.dll")
            │    └── LoadLibraryW(buf) → HMODULE
            │
            ├── GetProcAddress(hDll, "RunGameEx")
            │
            ├── 若找到 RunGameEx:
            │    └── RunGameEx(hInst, cmdLine, NULL, nShowCmd) ← 传入 WinMain 参数
            │
            ├── 若未找到 RunGameEx:
            │    └── exit code = 0xFFFFFFFE
            │
            └── TerminateProcess(GetCurrentProcess(), exit_code)


sub_1400011e8  [启动 SplashScreen.exe]
  ├── sub_14000102c            检查是否已有实例在运行（OpenMutexW）
  ├── 若已运行 → 直接返回
  ├── CreateMutexW             创建实例互斥体
  ├── GetModuleFileNameW + _wsplitpath_s
  ├── wcscpy_s + wcscat_s × 4  拼接: drive + dir + "SplashScreen.exe" + args
  └── CreateProcessW(".....\\SplashScreen.exe", ...)
```

---

## 五、关键发现

### 5.1 游戏引擎 DLL：Disrupt_64.dll

这个启动器本身 **不包含任何游戏逻辑**，全部逻辑在 `Disrupt_64.dll` 中。
- "Disrupt" 是 Ubisoft 《看门狗 2》专用引擎名
- 入口函数：`RunGameEx(HINSTANCE, LPWSTR cmdLine, HINSTANCE prev, int show)`
- 签名与标准 WinMain 相同，但通过动态加载调用

### 5.2 -nosplash 参数

- 检测路径：`StrStrIA(GetCommandLineA(), "-nosplash")`
- 若命令行 **不包含** `-nosplash`，则先启动 `SplashScreen.exe`（显示开场动画）
- 若包含则跳过动画，直接加载引擎

### 5.3 互斥体防重复运行

两级互斥体：
1. `sub_14000102c`：`OpenMutexW(0x20000, FALSE, name)` — 检测 SplashScreen 是否已经在跑
2. `sub_140001084`：创建两个互斥体管理整个进程生命周期

### 5.4 Authenticode 签名

数据目录 `Security`（RVA=0x81A00, size=0x17B0）包含 Ubisoft 代码签名证书，
确认这是 Ubisoft 官方发布的未篡改二进制。

---

## 六、资源提取

| 路径 | 内容 |
|------|------|
| `extracted_resource.bin` | 嵌入的 PNG 启动画面（~442 KB，有效 PNG 文件） |

---

## 七、总结

WatchDogs2.exe 是一个极简的 **引擎加载器**（约 3 KB 代码），职责：

1. 可选地启动 `SplashScreen.exe`（显示启动动画）
2. 动态加载 `Disrupt_64.dll`（真正的游戏引擎）
3. 调用 `RunGameEx` 把控制权完全交给引擎
4. 引擎退出后，通过 `TerminateProcess` 传递返回码

此设计使游戏引擎可以独立更新而不需要重新签名启动器。
