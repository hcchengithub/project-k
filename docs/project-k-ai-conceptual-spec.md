# Project K — AI Supporting Conceptual Specification

Version: 2.1.0 Concept  
Author: H.C. Chen & Assistant  
Status: Draft / Behavioral Reference

---

## 1. 宗旨與邊界 (Purpose & Boundary)

Project K 是一個極簡、可自舉擴展的 Forth 核心。本規格定義 Project K 系統在支援人工智慧 (AI) 整合時的**概念架構與行為契約 (Conceptual Contract)**。

### 核心原則：
1. **核心純粹 (AI Outside the Kernel)**：
   - Project K 核心架構（`VM`、`Task`、`Input`、`Word`）本身不內建任何 AI Client、Model 呼叫或通訊協定。
   - AI 是作為 Host Extension（宿主擴充層）引入，透過核心既有的 `yield vm.pause()`、`Task.resume()` 以及 Host 互通機制完成對接。
2. **極簡克制，點到為止 (Minimal & Restrained)**：
   - 避免早期 Forth 系統或衍生專案過度膨脹的毛病。
   - 系統對外公開的 Forth 介面僅收斂至兩個核心詞彙：**`(ai)`** 與 **`ai:`**。不引進非核心的週邊設備管理、複雜看板或重型框架。
3. **語言中立性 (Language Agnostic)**：
   - 本規格描述通用的互動概念與行為預期，不限定宿主語言是 Python、JavaScript 或其他語言。

---

## 2. 概念模型 (Fundamental Concepts)

```text
 ┌────────────────────────────────────────────────────────┐
 │                      User / REPL                       │
 └───────────────────────────┬────────────────────────────┘
                             │
                      forth> ai: prompt
                             │
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │                   Forth Vocabulary                     │
 │          : ai: ... (ai) ... ;  (immediate)             │
 └───────────────────────────┬────────────────────────────┘
                             │
                             ▼
 ┌────────────────────────────────────────────────────────┐
 │              Host AI Extension (e.g. ai.py)            │
 │  ┌──────────────────────────────────────────────────┐  │
 │  │                (ai) Generator                    │  │
 │  │  - Manages Session & Turns                       │  │
 │  │  - Streams Assistant Text to User                │  │
 │  │  - Dispatches Tools                              │  │
 │  └─────────────┬──────────────────────┬─────────────┘  │
 └────────────────┼──────────────────────┼────────────────┘
                  │                      │
      1. Tool: search_words              │ 2. Tool: run_forth
                  │                      │
                  ▼                      ▼
        ┌──────────────────┐   ┌──────────────────┐
        │  Read Dictionary │   │  Security Check  │
        │    (Read-only)   │   │  (Safe? Trust?)  │
        └──────────────────┘   └─────────┬────────┘
                                         │
                                [Unsafe & Untrusted]
                                         │
                                         ▼
                                  yield vm.pause()
                           (Task Pauses, Control Returns)
```

### 2.1 對話單元 (Conversation Session & Turns)
- **Session (對話階段)**：代表使用者與 AI 模型之間的一個邏輯對話上下文，由宿主環境維護。
- **Turn (對話回合)**：單次輸入（Prompt）至 AI 回覆完畢的完整往返。一個 Turn 可能包含文字生成、單次或多次工具呼叫（Tool Calls），直到 AI 生成最終回覆。

### 2.2 雙向驅動 (Bidirectional Driving)
- **Host -> AI**：使用者或 Forth 程式發起 Prompt，驅動 AI 生成思考與回應。
- **AI -> Host**：AI 在回答過程中，可提出在當前 VM 執行的工具請求（例如查詢字典或執行 Forth 代碼），形成閉環。

---

## 3. 核心詞彙契約 (Core AI Vocabulary Contract)

系統僅向 Forth 詞彙庫暴露以下兩個詞彙：

### 3.1 `(ai)`
- **堆疊效應**：`( prompt-string stream? -- [response-string] )`
- **性質**：Host Code Definition (以 Generator 實作的合作式操作)。
- **行為契約**：
  1. 自堆疊彈出布林旗標 `stream?` 與提示字串 `prompt`。
  2. 建立或延續對話階段，將 `prompt` 發送至 AI 服務。
  3. 若 `stream?` 為 `true`：即時將 AI 回覆的文字片段串流印出至輸出終端，結束後堆疊不留返回值。
  4. 若 `stream?` 為 `false`：將 AI 完整回覆的文字字串壓入資料堆疊（Data Stack），供後續 Forth 程式處理。
  5. 支援工具呼叫處理；若執行過程中觸發安全審核，主動 `yield pause` 暫停當前 Task。

### 3.2 `ai:`
- **堆疊效應**：`( <prompt> -- )`
- **性質**：Immediate Colon Definition。
- **行為契約**：
  1. 於編譯期或解譯期讀取當前輸入緩衝區（TIB）後續的所有剩餘文字作為 prompt。
  2. 預設以串流模式 (`stream? = true`) 呼叫 `(ai)`。
  3. 這是命令列使用者最自然的互動入口：`ai: tell me a joke`。

---

## 4. 合作式調度與 Pause / Resume (Cooperative Scheduling)

Project K 的 `Task` 與 `pause/resume` 機制在此展現其最大價值：

1. **非阻塞等待 (Non-blocking Wait)**：
   - 當 AI 進行耗時的遠端運算，或提議執行需要使用者授權的動作時，`(ai)` 不應鎖死執行緒，而是產生暫停信號（`yield vm.pause()`）。
2. **上下文完整保存 (Preserved Context)**：
   - 暫停時，該 Task 擁有的 input cursor、return stack、task stack (T-stack) 以及 internal frames 完好封存於記憶體中。
3. **控制權回歸 (Yield Control to Host)**：
   - 控制權回到 Host（例如 REPL 的 `forth>` 提示字元）。使用者可在此刻檢查資料堆疊、查詢詞彙原始碼，完全掌握主控權。
4. **續行執行 (Resume)**：
   - 當使用者確認後輸入 `resume`，Task 從暫停點無縫繼續推進，接收結果並回報給 AI 完成該回合。

---

## 5. 工具抽象 (Tool Abstraction)

AI Extension 為模型提供兩項基礎工具，讓 AI 成為認識當前 VM 的專家：

### 5.1 字典搜尋 (`projectk_search_words`)
- **語意**：讀取當前 VM 字典（`vm.words`），檢索匹配的名稱、說明（help）、註解（comment）與原始碼。
- **權限**：純讀取操作，無副作用，永遠直接放行。

### 5.2 代碼提議與執行 (`projectk_run_forth`)
- **語意**：AI 提出一段 Forth 程式碼與其執行目的（Purpose），請求在當前本地 VM 中實時執行，並獲取執行後的輸出、堆疊狀態與錯誤。
- **權限**：受到安全機制保護（詳見第 6 節）。

---

## 6. 安全架構與權限邊界 (Safety & Authority Model)

為防止 AI 自動執行具破壞性的程式碼，系統實施雙層安全審核：

### 6.1 詞彙安全性屬性 (`word.properties["safe"]`)
- **白名單機制**：
  - 每個 Word 擁有自身的屬性字典。
  - 無副作用的詞（如純數學運算、堆疊操作、檢視指令）標記為 `safe = True`。
  - 任何涉及系統呼叫、檔案寫入、定義新詞彙或未知自訂詞彙，預設為未標記（不安全）。

### 6.2 咽喉關卡 (`vm.call` Decorator)
- 核心 `projectk.py` 不做修改。Host 在掛載 AI 時，以 Decorator 包裹 `vm.call`。
- 在 AI 執行脈絡下，進入任何非 safe 的詞彙時，Decorator 會觸發攔截並發起暫停審核。

### 6.3 Task 範疇批准 (Task-Level Approval Scope)
- **逐詞審核 (Step-by-step)**：使用者單純 `resume`，只放行當前步驟。
- **任務信任 (Trust Task)**：使用者批准當前 Task（例如 `trust-task resume`），則該 Task 在其生命週期內後續的所有動作一律放行，直到任務終止（`done`/`failed`/`aborted`）。
- **生命週期隔離**：批准狀態僅隨該 Task 存在，任務結束即刻銷毀，不影響後續獨立的新任務。

---

## 7. 驗收情境 (Behavioral Acceptance Scenarios)

1. **基本對話情境**：
   使用者輸入 `ai: hello`，AI 回覆文字以打字機串流即時印於終端機，執行完畢印出 `ok`。
2. **字典認知情境**：
   使用者詢問 `ai: 系統有哪些堆疊詞彙？`，AI 透過 `projectk_search_words` 查詢本地字典並給出精確答案。
3. **安全審核情境**：
   AI 提議執行包含未標記 safe 的程式碼（例如定義新詞或調用 Python 系統功能），Task 在執行該詞前主動 pause，提示字元回到 `forth>`，使用者確認輸入 `resume` 後順利完成。
4. **任務信任情境**：
   對於多步驟的複雜程式碼，使用者以 `trust-task resume` 批准該 Task，該 Task 後續詞彙一氣呵成執行完畢，不反覆中斷。

---

## 8. 結論 (Conclusion)

Project K 2.1.0 的 AI 支援並非將 AI 堆砌成龐然大物，而是透過優雅的語意邊界、Word 自宣告屬性、Task 暫停續行與 Task 範疇批准，展示一個極簡 Forth 核心如何以最小的代價，優雅且安全地駕馭現代生成式 AI。
