# Project K 如何執行 (How to Run)

> 本文件專注於**「如何以最快方式讓程式跑起來」**與執行環境的配置指南。  
> 關於 Project K 的架構設計理念、雙 stack 模型與語彙核心機制，請參閱核心手冊 [`manual-py.md`](manual-py.md)。手冊與本指南分開的原因在於：**手冊記錄的是穩定不變的設計理念，而如何執行與環境配置方式則會隨工具鏈演進而隨時迭代**。

---

## ⚡ 快速上手（首次設定後即可啟動）

核心 VM 只需要 Python 3 (3.10+)。互動式 REPL 需要 `prompt_toolkit`，請把它安裝在執行 REPL 的 Python 環境中。WSL/Linux 和 Windows 使用不同的 VENV，不能共用同一個環境；兩者都可放在 repo 外，避免 OneDrive 同步虛擬環境。

#### Linux / WSL（Bash）

在 `py/.env` 設定 Linux/WSL 的外部 VENV：

```dotenv
PROJECTK_VENV=~/venvs/project-k
```

從 repo 根目錄建立環境並安裝依賴：

```bash
uv venv ~/venvs/project-k
uv pip install --python ~/venvs/project-k/bin/python -r py/requirements.txt
```

`./py/f.sh` 會讀取 `py/.env` 的 `PROJECTK_VENV`，並使用該 Linux/WSL VENV。

#### Windows（PowerShell / CMD）

Windows 必須有自己的 Windows VENV。以下範例在 `%USERPROFILE%\.venvs\project-k` 建立環境並安裝 REPL 依賴。

PowerShell：
```powershell
uv venv "$env:USERPROFILE\.venvs\project-k"
uv pip install --python "$env:USERPROFILE\.venvs\project-k\Scripts\python.exe" -r py\requirements.txt
. "$env:USERPROFILE\.venvs\project-k\Scripts\Activate.ps1"
```

CMD：
```cmd
uv venv "%USERPROFILE%\.venvs\project-k"
uv pip install --python "%USERPROFILE%\.venvs\project-k\Scripts\python.exe" -r py\requirements.txt
call "%USERPROFILE%\.venvs\project-k\Scripts\activate.bat"
```

啟用 VENV 後，Windows 的 `python py\repl.py`、`py\f.cmd` 和 `py\f.bat` 才會使用這個環境。兩個批次檔只呼叫 PATH 上的 `python`；也可改用已安裝依賴的 Windows Python。WSL 的 `~/venvs/project-k` 不會被 Windows launcher 使用。

### 1. 互動式 REPL 模式

```bash
# Linux / WSL 終端機：
./py/f.sh

# Windows PowerShell（先啟用 Windows VENV）：
.\py\f.cmd

# Windows CMD（先啟用 Windows VENV）：
py\f.cmd
```
在 REPL 中，Enter 送出整個編輯框；Ctrl+J 或 Esc 後再按 Enter 插入新行。Shift+Enter 只有在終端提供可區分的按鍵序列時才能使用；部分終端也可能把 Ctrl+Enter 傳成 Ctrl+J，因此它會插入新行。多行貼上會完整保留在編輯框內，不會逐行執行。看到 `Project K Forth REPL` 後，可鍵入基礎算術驗證：
```forth
> 10 20 + . cr
30
> bye
```
*(輸入 `bye` 或按下 `Ctrl+D` 即可隨時退出)*

---

### 2. 單行表達式測試（免進入 REPL）

使用 `-e` (evaluate expression) 參數直接在終端機求值：

```bash
# Linux / WSL
python3 py/repl.py -e '10 20 + . cr s" Hello Project K!" . cr bye'

# Windows
python py\repl.py -e "50 50 + . cr bye"
```

---

### 3. 本地快捷腳本

如果你切換進 `py/` 目錄：
* **Linux / WSL**：`./f.sh`
* **Windows**（先啟用已安裝 REPL 依賴的 Windows VENV）：`.\f.cmd`

---

## 🛠️ 全域命令配置（在任何目錄敲 `f` 就能執行）

若希望在作業系統的**任意工作目錄**下，只需輸入 `f` 即可立即喚起 Project K，請依據你的作業系統進行以下極簡設定：

### A. Windows (PowerShell / CMD) 設定

1. **建立全域轉發腳本**：  
   在已經加入系統 `PATH` 的目錄（推薦為 `%USERPROFILE%\.local\bin`）中建立全域 `f.cmd` 與 `f.bat`。它們也會呼叫 PATH 上的 `python`；使用外部 Windows VENV 時，請先啟用該 VENV：

   ```cmd
   @echo off
   if not defined PROJECTK_HOME (
       set "PROJECTK_HOME=%USERPROFILE%\OneDrive\Documents\GitHub\project-k"
   )
   python "%PROJECTK_HOME%\py\repl.py" %*
   ```

2. **設定環境變數 `PROJECTK_HOME` (選用，支援專案任意搬遷)**：  
   在 CMD 中執行：
   ```cmd
   setx PROJECTK_HOME "%USERPROFILE%\OneDrive\Documents\GitHub\project-k"
   ```

---

### B. Linux / WSL (Bash / Zsh) 設定

1. **建立全域符號連結 (Symbolic Link)**：  
   在使用者專屬的 `~/.local/bin` 目錄下建立軟連結，直接指向專案的 `f.sh`：

   ```bash
   ln -sfn /path/to/project-k/py/f.sh ~/.local/bin/f
   ```

2. **確認 PATH**：  
   確保 `~/.local/bin` 已加入使用者的環境變數（若未加入，可在 `~/.bashrc` 加入 `export PATH="$HOME/.local/bin:$PATH"`）。

3. **符號連結穿透解析 (內部機制)**：  
   `f.sh` 內建自動穿透解析技術（`readlink -f`），即使透過符號連結呼叫，也能自動精確找到同目錄下的 `repl.py` 與 `base.f`，無須依賴固定的執行目錄。

---

## 🧪 自動化測試

在專案根目錄執行：

```bash
# Linux / WSL
python3 py/verify_projectk.py

# Windows PowerShell / CMD
python py\verify_projectk.py
```

目前套件包含 65 項自動化測試。

---
## 📂 檔案角色分工一覽

專案目錄 `py/` 下各檔案各司其職：

| 檔案 | 適用環境 | 角色與內容說明 |
| :--- | :--- | :--- |
| `repl.py` | 跨平台 (Python 3) | **REPL 核心進入點**。負責初始化 VM、載入 `base.f`、`auxiliary.f` 和 `ai.f`、多行代碼緩衝處理，以及命令列引數解析 (`-e` 或指定檔案)。 |
| `base.f` | 純 Forth 原始碼 | **核心字典正本 (Bootstrap)**。包含控制結構、字串家族、Defining Words、`see` 等核心 words，由 `repl.py` 啟動時載入。 |
| `auxiliary.f` | Forth 擴充 | **輔助工具 words**。包含以 Forth `code` 直接定義的 `cls` 和 `stringify`。 |
| `ai.f` | Forth 擴充 | **AI words 與流程**。以 `code` 和 colon words 定義 Agents API 的對話、工具交握、核准及 session 操作；傳輸與少量 Python host 功能由 `ai_bridge.py` 提供。 |
| `ai_bridge.py` | Python 標準函式庫 | **AI 基礎 host 功能**。負責 HTTP/SSE、API 請求、session index 檔案，以及 Forth 執行輸出擷取。 |
| `projectk.py` | 跨平台 (Python 3) | **微核心 VM 引擎**。定義 `VM`、雙 stack 容器、`Task` 狀態機、`_Word` 資料結構，以及 Python 原生代碼塊解析器。 |
| `verify_projectk.py` | 跨平台 (Python 3) | **自動化驗證套件**。涵蓋 69 項測試。 |
| `f.sh` | Linux / WSL | **Linux/WSL 啟動腳本**。解析符號連結，從 `PROJECTK_VENV` 選擇 Python 環境。 |
| `f.cmd` / `f.bat` | Windows | **Windows 啟動腳本**。呼叫 PATH 上的 `python`；外部 VENV 需先啟用。 |

---

## 🔍 常見排錯經驗 (Troubleshooting)

1. **PowerShell 當前目錄執行規則**：
   * **現象**：在 `py/` 目錄下直接打 `f` 顯示找不到命令。
   * **解法**：PowerShell 預設基於安全性不搜尋當前目錄，請打 `.\f.cmd`，或在設定好全域 PATH 後於任意目錄直接打 `f`。
2. **Git Dubious Ownership (WSL 與 Windows 跨區掛載)**：
   * **現象**：在 WSL 中對掛載磁碟 `/mnt/c/...` 執行 git 時出現 `fatal: detected dubious ownership`。
   * **解法**：執行 `git config --global --add safe.directory /mnt/c/Users/<Your-Username>/...` 將專案加入信任清單。
3. **路徑移轉與環境變數快取**：
   * **現象**：專案改名或移至其他硬碟後無法啟動。
   * **解法**：更新 `PROJECTK_HOME` 環境變數或確認符號連結指向最新目錄。
