# Project K — JavaScript V2

A minimal Forth kernel with resumable tasks, implemented from the
[language-independent conceptual specification](../docs/project-k-conceptual-spec.md)
and developed alongside the [Python V2 implementation](../py/README.md).

A fresh `VM` contains only two words, `code` and `end-code`. Everything else is
grown from them. Tasks can `pause` while waiting for outside work and `resume`
later. The kernel itself has no AI integration.

**Project K requires a JavaScript runtime, not Node.js specifically.**
The kernel has no dependencies and imports nothing from Node, so the same
`projectk.js` can run in Node.js or directly in a modern web browser as an
ES module.

## Quick start: browser — no installation

Because `projectk.js` is an ES module, load it with `type="module"`.

This example imports Project K directly from this GitHub repository through
jsDelivr, so the HTML file itself can be anywhere:

```html
<!doctype html>
<html>
<body>
  <script type="module">
    import { VM } from "https://cdn.jsdelivr.net/gh/hcchengithub/project-k@master/js/projectk.js";

    const vm = new VM();

    vm.dictate(`
      code hi
        console.log("hello from Project K");
      end-code
      hi
    `);
  </script>
</body>
</html>
```

No Node.js, npm, build step, or local copy of Project K is required.

A browser is itself a JavaScript host, so host words can use browser facilities
such as `document`, `fetch`, Canvas, WebSocket, Web Audio, and other Web APIs:

```html
<div id="output"></div>

<script type="module">
  import { VM } from "https://cdn.jsdelivr.net/gh/hcchengithub/project-k@master/js/projectk.js";

  const vm = new VM();

  vm.dictate(`
    code show
      document.getElementById("output").textContent = vm.pop();
    end-code

    code hello
      vm.push("Hello from Forth inside a web page");
    end-code

    hello show
  `);
</script>
```

### Browser security note

`code ... end-code` compiles JavaScript host bodies dynamically. A page with a
strict Content Security Policy that forbids dynamic code generation
(`unsafe-eval`) may therefore block host definitions. Ordinary pages without
that restriction can use them normally.

For browser use, prefer a JavaScript CDN such as jsDelivr rather than a
`raw.githubusercontent.com` URL. GitHub Raw is primarily a file-download
endpoint; a CDN provides more appropriate JavaScript delivery and caching.

## Quick start: Node.js

Node.js 18 or later is recommended for the supplied command-line demos and test
suite.

```js
import { VM } from "./projectk.js";

const vm = new VM();
vm.dictate(`
  code hi
    console.log("hello World!");
  end-code
`);                    // defines hi
vm.dictate("hi");       // prints hello World!
```

The first `dictate()` defines a code word named `hi`; it does not run it. The
second interprets the TIB `"hi"`, finds the word and executes it.

## Files

| File | Purpose |
| --- | --- |
| `projectk.js` | The kernel only: `VM`, `Task`, `Input`, `Word`, `Literal`, `Frame`, `KernelError`. Imports nothing. |
| `demo.js` | Optional demonstration vocabulary (`EXPLORER`), `makeVM()`, and the `k>` console. |
| `demo.test.js` | The Python test suite, ported test for test (20 tests). |
| `cave.js` | A text game written entirely as Forth words. Its loop pauses for input. |

```sh
node demo.js        # open the k> console (try: : square dup * ; 12 square .)
node --test         # run the tests
node cave.js        # play CAVE
```

These command-line examples require Node.js; **the Project K kernel itself does
not**.

## Differences from the Python implementation

Host bodies (`code ... end-code`) are JavaScript, so a few details differ.

- **Host bodies are generator functions.** A `code` body can `yield vm.pause()`
  or `yield* vm.evaluate("...")` directly; there is no separate "generator word"
  form. Bodies run in strict mode.
- **`end-code` detection** uses a small JavaScript scanner instead of Python's
  `tokenize`. It ignores `end-code` inside strings, template literals (including
  `${}` nesting), regex literals, and comments. A `//` comment runs to the end of
  its line, so put `end-code` on its own line after one.
- **Numbers.** Decimal and `0x`/`0o`/`0b` integers, then floats, with Python's
  `_` separators. Integers in the safe range are `Number`; larger ones are
  `BigInt` so `9007199254740993` keeps its value. Mixing `BigInt` and `Number` in
  one expression throws, and the kernel reports it as a `KernelError`.
- **Naming** follows JavaScript: `appendInput`, `colonCode`, `exitRequested`,
  `pausedTasks`. Colon bodies are frozen arrays instead of tuples, and
  `vm.words` is a `Map` (insertion ordered, a redefined word moves to the end).
- **Positions** (`itib`, `consume`) count UTF-16 code units, not code points.
- **Printing.** Demo words use `console.log`. `cave.js` takes an `out` function
  through the VM's host bindings, which is the pattern to use if you want to
  render somewhere other than stdout.

Behavior that is the same: `dictate`/`execute`, task states, `pause`/`resume`/
`cancel`, captured binding in colon words, the task-private return and temporary
stacks, cross-input definitions, and the failure rules (a failed task discards
its unfinished definition and leaves the vocabulary as it was).
