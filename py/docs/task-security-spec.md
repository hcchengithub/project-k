# Project K: AI Task 安全審核與執行規格書 (Task Security & Approval Spec)

## 1. 概述 (Overview)

本規格定義 Project K Python 版在引入 AI 整合（即 `(ai)` 與 `ai:`）時的安全審核機制。

其核心原則為：
1. **核心不變 (Zero Kernel Modification)**：`projectk.py` 保持 100% 原始與 Conceptual Spec 一致，所有安全機制以 Decorator / Extension 方式掛載於 `vm.call`。
2. **Word 自身決定安全性 (Self-declared Word Safety)**：每個 Forth Word 透過自身的 `word.properties["safe"]` 屬性標記其安全性（白名單機制）。
3. **支援 Task 範疇批准 (Task-Level Approval)**：使用者既可以逐詞審核，也可以直接針對整個 Task 予以批准，避免在多步驟操作中頻繁中斷。
4. **純 Forth 風格的 REPL 體驗 (Pure Forth Interactive Model)**：不依賴任何外部第三方對話框 UI，當需要審核時，Task 透過 `yield vm.pause()` 主動交回控制權，回到 `forth>` 提示字元，由使用者透過 `resume`、`see`、`.s` 等標準 Forth 方式檢視與繼續。

---

## 2. Word 安全性屬性 (`word.properties["safe"]`)

每個 `Word` 物件具備 `properties: dict`。

- **`safe: True`**：
  標記為無副作用、純讀取或純計算的詞彙。在 AI 執行情境下呼叫時，系統**直接放行**，不觸發暫停審核。
  *範例*：`dup`, `swap`, `drop`, `+`, `-`, `*`, `/`, `.`, `.s`, `words`, `see`, `help`, `depth` 等。
- **未標記或 `safe: False`**：
  任何可能修改系統狀態、呼叫 Python 系統模組、檔案讀寫、定義新詞彙或未知自訂詞彙。在 AI 執行情境下被呼叫時，**預設必須經過審核**。

### Forth 屬性標記語法
在 `projectk.f` 中，提供直觀的語法設定屬性：
```forth
' .s :: safe=True
' words :: safe=True
' + :: safe=True
```

---

## 3. 執行關卡：`vm.call` Decorator

所有 Forth Word 的執行（無論是 Outer Interpreter 讀入的 token、或是 Colon Word 內部展開的每一個步驟）皆必須通過 `vm.call(operation)`。

因此，由 `ai.py` 提供一個 Decorator，在載入 AI 模組時對 `vm.call` 進行安全包裝：

```text
               AI 發起 Task 執行 (vm.host["in_ai_task"] = task)
                                  │
                                  ▼
                            vm.call(word)
                                  │
                  ┌───────────────┴───────────────┐
                  ▼                               ▼
            非 AI 任務執行                   AI 任務執行中
            (直接原樣執行)                         │
                                                  ▼
                                      該 Task 是否已被批准？
                                     (task 是否在 approved 列表中)
                                      ┌───────────┴───────────┐
                                      ▼ 是                    ▼ 否
                                  直接放行            word.properties.get("safe")
                                                      ┌───────┴───────┐
                                                      ▼ True          ▼ False / 無
                                                   直接放行     印出審核警示
                                                                 yield vm.pause()
```

---

## 4. Task 範疇批准機制 (Task-Level Approval Scope)

為了解決「多個不安全 Word 連續執行時需頻繁中斷」的痛點，系統引入 **Task-Level 批准**：

### 4.1 狀態所有權
- 批准狀態依附於 **當前正在執行的 Task 物件**（或在 `vm.host["trusted_ai_tasks"]` 中記錄該 `task` 的引用）。
- **生命週期**：僅在該特定 `Task` 存活期間有效。當該 `Task` 達到終止狀態（`done`、`aborted` 或 `failed`）時，批准狀態即刻失效。
- **全域隔離**：批准 Task A 不會讓未來的 Task B 自動獲得信任，徹底防止安全漏洞。

### 4.2 批准模式 (Approval Modes)

當非 safe 的 Word 觸發暫停審核時，終端機會顯示被攔截的 Word 與提議程式碼，並暫停回到 `forth>`。使用者可選擇：

1. **Step-by-step（單步放行 / Allow Once）**：
   - 使用者在 `forth>` 下直接輸入：
     ```forth
     resume
     ```
   - 僅放行「當前這一個 Word」。若該 Task 後續又呼叫了其他未標記 safe 的 Word，會再次暫停等待審核。

2. **Trust Task（批准整個 Task）**：
   - 使用者在 `forth>` 下輸入專屬命令（例如）：
     ```forth
     trust-task resume
     ```
     （或由 `trust-task` 將當前 pending 的 AI Task 標記為 trusted，隨後執行 `resume`）。
   - 該 Task 在接下來的整個生命週期內，所有後續 Word 皆直接放行，直到 Task 執行完成。

3. **Reject / Cancel（拒絕執行）**：
   - 使用者在 `forth>` 下直接輸入：
     ```forth
     cancel-task
     ```
     （或直接讓該 Task 放棄，不呼叫 resume，並通知 AI 該次呼叫被使用者取消）。

---

## 5. 純 Forth 風格的 REPL 互動場景

### 場景 1：完全 Safe 的查詢（無感流暢）
```text
forth> ai: 請幫我查一下有哪些堆疊運算詞彙？
🤖 查詢字典中...
[AI 調用 projectk_search_words 或執行 words]
（所有被調用詞彙皆為 safe=True，Task 不中斷）
AI 回覆：Project K 中常用的堆疊詞彙包含 dup, swap, drop, over, rot...
 ok
forth> 
```

### 場景 2：包含非 Safe 詞彙的執行與 Task 批准
```text
forth> ai: 請幫我寫一個計算階乘的 factorial 詞彙並計算 5 的階乘
🤖 我提議執行以下程式碼：
---
: factorial dup 1 <= if drop 1 else dup 1- recurse * then ;
5 factorial .
---
[Security] Word ':' is not marked as safe.
Task paused for review. Type 'resume' for single step, 'trust-task resume' to trust this task.

forth> .s
[]
forth> see factorial
Unknown word: factorial

forth> trust-task resume
120
 ok
forth> 
```
（在批准該 Task 後，`:`、`;`、`if`、`recurse` 等編譯詞彙一路執行完畢，不需反覆中斷）。

---

## 6. 模組職責切分 (File Responsibilities)

1. **`projectk.py`**：維持純淨 Conceptual Spec 實作，完全不改動。
2. **`ai.py`**：
   - 封裝 OpenAI API 通訊（`urllib` 純標準庫）。
   - 實作 `vm.call` 的安全 Decorator。
   - 管理 `vm.host["trusted_ai_tasks"]` 與 Task 批准狀態檢查。
3. **`projectk.f`**：
   - 定義基礎 Forth 詞彙，並為安全詞彙標註 `safe=True`。
   - 定義 `(ai)`、`ai:`、`trust-task` 等輔助詞彙。
4. **`main.py`**：
   - 純標準庫 REPL，啟動後載入 `projectk.f`，處理 `forth>` 提示字元與任務暫停/繼續迴圈。
