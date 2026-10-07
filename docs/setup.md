# Project-K 全域執行環境設定說明 (Setup Guide)

本文檔記錄如何將 Project-K 的 Forth 命令列工具 `f` 設定為在 **WSL (Linux)** 與 **Windows (PowerShell 7 / CMD)** 任意目錄下皆可直接執行的完整流程與原理。

---

## 1. 核心檔案與角色分工

在專案目錄 `D:\GitHub\project-k\py`（WSL 下為 `/mnt/d/GitHub/project-k/py`）中，負責執行入口的檔案如下：

| 檔案 | 適用環境 | 角色與內容說明 |
| :--- | :--- | :--- |
| `f` | WSL / Linux | Python 核心入口腳本，頂部帶有 `#!/usr/bin/env python3`，支援 `-e <expr>` 單行表達式執行、執行腳本檔 `<file.f>` 或進入互動式 REPL。 |
| `f.bat` | Windows (CMD / pwsh) | Windows 批次檔，呼叫 `python "%~dp0f" %*`，將參數完整轉發給同目錄下的 `f` 腳本。 |
| `f.cmd` | Windows (CMD / pwsh) | Windows 命令腳本，內容同 `f.bat`，確保相容不同 shell 對副檔名的搜尋偏好。 |

> [!NOTE]
> 原先舊版批次檔內指向的是更名前的 `repl`（`python "%~dp0repl" %*`），已全數修正為指向 `python "%~dp0f" %*`。

---

## 2. WSL (Linux) 設定方式

WSL 環境下採用 **Symbolic Link（軟連結）** 機制：

1. **建立軟連結**：
   在使用者目錄下的 `~/.local/bin` 中建立名為 `f` 的符號連結，指向專案的 `f`：
   ```bash
   ln -sfn /mnt/d/GitHub/project-k/py/f ~/.local/bin/f
   ```

2. **確認 PATH**：
   一般現代 Linux / Ubuntu 預設在登入時會自動將 `~/.local/bin` 加入 `$PATH`。若未包含，可在 `~/.bashrc` 加入：
   ```bash
   export PATH="$HOME/.local/bin:$PATH"
   ```

3. **確認執行權限**：
   確保 `/mnt/d/GitHub/project-k/py/f` 具備可執行權限（`chmod +x`），由於有 shebang（`#!/usr/bin/env python3`），Linux 會直接調用 Python 執行。

---

## 3. Windows (pwsh / CMD) 設定方式

Windows 環境採用 **雙軌並行** 設定，兼顧「新建終端機」與「現有開啟中的終端機」：

### 策略 A：將專案路徑加入 Windows 使用者 `PATH`
透過 PowerShell（pwsh）將 `D:\GitHub\project-k\py` 寫入 Windows 使用者層級的環境變數：

```powershell
$target = 'D:\GitHub\project-k\py'
$oldPath = [Environment]::GetEnvironmentVariable('Path', 'User')
if ($oldPath -notlike "*$target*") {
    $newPath = $oldPath.TrimEnd(';') + ';' + $target
    [Environment]::SetEnvironmentVariable('Path', $newPath, 'User')
}
```
* **效果**：未來任何新啟動的 PowerShell 7 (`pwsh`) 或 `CMD` 視窗，系統搜尋路徑皆包含該目錄，直接輸入 `f` 就會自動找到 `D:\GitHub\project-k\py\f.bat` 或 `f.cmd`。

### 策略 B：在既有 PATH 路徑中建立 Shim
由於許多已開啟的終端機不會立即重新載入環境變數，且 Windows 使用者的 `C:\Users\<Your-Username>\.local\bin` 本已在系統 PATH 內，因此在該處放置了轉發 Shim：
- `C:\Users\<Your-Username>\.local\bin\f.cmd`
- `C:\Users\<Your-Username>\.local\bin\f.bat`

內容均為：
```cmd
@echo off
python "D:\GitHub\project-k\py\f" %*
```
* **效果**：現有正在運行的終端機無需重啟即可立即呼叫 `f`。

---

## 4. 驗證利器：`-e` 參數一次測透 (Test Them All)

`f` 腳本內建的 `-e`（evaluate expression）旗標非常適合作為健全度測試（Sanity Check），不需要進入互動式 REPL 再手動輸入 `bye` 退出，直接一行出結果：

### 1) WSL 測試
```bash
$ f -e "10 20 + ."
30
```

### 2) Windows pwsh (PowerShell 7) 測試
```powershell
PS> f -e '111 222 + .'
333
```

### 3) Windows CMD 測試
```cmd
> f -e "222 333 + ."
555
```

---

## 5. 常見踩坑與排錯經驗 (Troubleshooting Gotchas)

在 WSL 與 Windows 混合環境下除錯時，曾遇到以下兩個隱藏陷阱，值得特別記錄備查：

### 1. WSL 呼叫 Windows 程式時的 UNC 路徑卡死問題
* **症狀**：從 WSL 背景執行 `pwsh.exe` 或 `powershell.exe` 時整個 process 卡住不動（hang）。
* **原因**：當前工作目錄（CWD）若為 Linux 路徑（如 `~` 或 `/home/<username>`），Windows 端會嘗試存取 UNC 網路路徑 `\\wsl.localhost\Ubuntu\...`。某些情境下 Windows 探索或安全機制會卡在 UNC 掛載逾時。
* **解法**：在 WSL 呼叫 Windows 程式前，先確保工作路徑切換至 Windows 磁碟（如 `/mnt/c/...` 或 `/mnt/d/...`）。

### 2. PowerShell 背景執行時的 Stdin 阻塞
* **症狀**：呼叫 `pwsh.exe` 指令後未在預期時間內結束。
* **原因**：PowerShell 預設可能等待控制台標準輸入（stdin）。
* **解法**：指令加上 `-NonInteractive -NoProfile`，並透過 `< /dev/null` 阻斷 stdin 等待。
