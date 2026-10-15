# Project K — From a Minimal Kernel to a New Forth System

Project K began as a small Forth kernel implemented in JavaScript and Python. The original project is preserved as **[V1](https://github.com/hcchengithub/project-k/tree/v1.0.9)**. It is frozen: its code remains available as a record of the original work, while development moves forward in a new **V2** history.

## Why V2

I had long wanted to improve my Python implementation. With today's AI tools—and especially the arrival of GPT-6.1—OpenAI encouraged me to experiment, so I asked AI to help reconstruct a specification from the existing work, then build a new implementation from that specification.

The result surprised me. The new implementation follows the same project purpose, yet the ideas, techniques, and realization produced from the specification are far beyond what I had achieved before. This repository is where I am exploring that result: first in Python, and later in JavaScript.

V2 begins from a clean, orphaned Git history. It does not carry the [V1](https://github.com/hcchengithub/project-k/tree/v1.0.9) source into its working tree; [V1](https://github.com/hcchengithub/project-k/tree/v1.0.9) remains preserved separately.

## Project structure

- [`docs/project-k-conceptual-spec.md`](docs/project-k-conceptual-spec.md) — the language-independent conceptual specification.
- [`py/`](py/) — the Python V2 implementation and its guide. See [the Python README](py/README.md).
- `js/` — a JavaScript V2 implementation is planned; it has not been added yet.

The conceptual specification describes Project K independently of its implementation language. Each language directory has its own implementation guide.

---

# Project K — 從精簡 Kernel 出發，打造新一代 Forth 系統

Project K 原本是一個以 JavaScript 和 Python 實作的 Forth kernel。原有成果保留為 **[V1](https://github.com/hcchengithub/project-k/tree/v1.0.9)**，並凍結在原來的歷史中；後續開發從新的 **V2** 開始。

## 為什麼做 V2

我一直對自己以前的 Python 功力不太滿意。現在有了強大的 AI，尤其 GPT-6.1 出現後，OpenAI 鼓勵我試著用 AI 做點不一樣的事。我請 AI 從既有成果倒推出一份 SPEC，再依照 SPEC 打造新的實作。

結果讓我非常驚喜：前後做的是同一個 Project K，但 AI 按照 SPEC 寫出的成果，在觀念、技巧和理想的實現上，都遠遠超過我以前的作品。V2 就是我探索這份新成果的地方：目前先完成 Python，之後有空再改良 JavaScript。

V2 從全新的 orphan branch 歷史開始，工作樹不帶入 [V1](https://github.com/hcchengithub/project-k/tree/v1.0.9) 的原始程式；[V1](https://github.com/hcchengithub/project-k/tree/v1.0.9) 則獨立保留。

## 專案結構

- [`docs/project-k-conceptual-spec.md`](docs/project-k-conceptual-spec.md)：不限定實作語言的 conceptual SPEC。
- [`py/`](py/)：Python V2 實作與使用說明，請見 [Python README](py/README.md)。
- `js/`：之後規劃加入 JavaScript V2，目前尚未加入。

Conceptual SPEC 描述的是 Project K 本身，不綁定 Python 或 JavaScript；各語言目錄則各自說明該語言的實作。
