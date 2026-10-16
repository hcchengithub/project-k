# Project-K v2 — JavaScript Version

## A small kernel that can grow

Project K follows the **eForth tradition** of growing a useful Forth system from
a very small kernel.

The question that guides this implementation is not, “How many useful words can
we put into the kernel?” It is almost the opposite:

> **How little can a kernel know, while still giving us enough power to grow a
> whole system?**

Project K carries that idea into a modern JavaScript host. We do not try to
reproduce every historical implementation detail of an older machine: a flat
dictionary address space, a particular threading model, or the constraints of
a particular CPU. We preserve the design principle that matters here: keep the
kernel small, make its mechanisms understandable, and let the vocabulary grow
the language.

The JavaScript version of Project-K v2 adds ideas that belong to its own time—browser integration,
explicit Tasks, resumable execution, and a continuation that can pause while
the outside world does something else.

The language-independent contract lives in
[the conceptual specification](../docs/project-k-conceptual-spec.md). The
[Python V2 implementation](../py/README.md) explores the same design in a
different host.

---

## Start here: the browser is enough

Project K requires a **JavaScript runtime**, not Node.js specifically.

The kernel imports nothing from Node.js. A modern browser can load it directly
as an ES module:

```html
<script type="module">
  import { VM } from
    "https://cdn.jsdelivr.net/gh/hcchengithub/project-k@master/js/projectk.js";

  const vm = new VM();

  vm.dictate(`
    code answer
      vm.push(42)
    end-code

    answer
  `);

  console.log(vm.pop());   // 42
</script>
```

There is no npm install, build step, or local copy of Project K in that example.
The web page is the host.

For learning, however, you do not need to keep building little HTML files.
Open [`demo.html`](demo.html) after downloading it. It is the interactive laboratory used
throughout this README: a Forth input area, output, data-stack display,
vocabulary display, latest-definition display, and Task status.

The game [`games/sokoban.html`](games/sokoban.html) is deliberately separate from the
teaching demo. It is an application built *with* Project K, not the Project K
lab itself.

The browser HTML files load Project-K from jsDelivr, so after downloading an HTML file you can open it directly in a browser.\n\n---

## Repository map

```text
js/
├── projectk.js
├── README.md
├── demo.html
├── test.js
├── test-runner-browser.html
├── test-runner-node.js
├── package.json
└── games/
    └── sokoban.html
```

The separation is intentional:

| File | Role |
| --- | --- |
| `projectk.js` | The kernel. |
| [`demo.html`](demo.html) | The browser REPL/lab that accompanies this README. |
| `test.js` | Environment-neutral behavioral test cases. |
| `test-runner-browser.html` | Runs those tests in a browser. |
| `test-runner-node.js` | Runs the same tests under Node.js. |
| `games/sokoban.html` | A browser application built on Project K. |

One contract, two runners. The tests do not need separate Browser and Node
versions; only the mechanism that *runs and reports* them is host-specific.

---

# Part I — How can two words be enough?

## 1. Look at a newborn VM

A fresh VM is intentionally almost empty:

```js
import { VM } from "./projectk.js";

const vm = new VM();
console.log([...vm.words.keys()]);
// ["code", "end-code"]
```

That is not a toy state we immediately hide. It is the architectural statement.

The two seed words let us describe a new operation in JavaScript and give that
operation a Forth name. From there, an extension can grow stack operations,
colon-definition syntax, strings, control structures, inspection tools, or an
application-specific vocabulary.

**Socratic question:** if `dup`, `+`, `:`, `;`, and `if` are useful,
why not simply hardwire all of them?

Because usefulness is not the same thing as *kernel responsibility*. If a
facility can be grown naturally from a smaller mechanism, it is worth asking
whether it belongs outside the seed.

Try **“1 · Bare kernel”** in [`demo.html`](demo.html). The lab itself loads a small teaching
vocabulary after creating the VM, but the experiment lets you inspect where the
growth began.

---

## 2. Grow the first operation

A code definition borrows the host language:

```forth
code double
  vm.push(vm.pop() * 2)
end-code
```

Now:

```forth
21 double
```

leaves `42` on the data stack.

What happened?

1. `code` read the name `double`.
2. It consumed a JavaScript body up to the matching `end-code`.
3. The kernel compiled that body into host behavior.
4. A Word named `double` was published in the vocabulary.
5. Later lookup of `double` found that Word and executed it.

This is the first step in the small-kernel growth pattern:

```text
small seed
   ↓
host words
   ↓
language-building words
   ↓
larger vocabulary
   ↓
application
```

Try **“2 · Grow words”** in [`demo.html`](demo.html).

---

# Part II — What exactly is a Word?

## 3. Name, behavior, and identity

A **Word** is a named operation.

The vocabulary maps a name to the Word that is currently visible under that
name:

```js
const word = vm.tick("double");
console.log(word.name);       // double
console.log(word.category);   // code
```

`tick(name)` answers a very specific question:

> “Which Word is currently visible under this name?”

The VM also maintains its **latest-definition reference**, exposed in the
JavaScript implementation as `vm.latest`. During colon building it can even
refer to the provisional Word that is not yet published.

These are different questions:

- `tick("square")`: find by **name**.
- `vm.latest`: identify the **most recently established definition context**.

This distinction matters when an extension implements words such as
`immediate`: the operation usually wants the definition just created, not a
fresh name lookup supplied by the user.

The Python implementation exposes the same conceptual “last definition”
capability through its own host interface. The conceptual specification
requires the capability, not one spelling in every language.

---

## 4. Redefinition does not rewrite history

Suppose we grow a normal `square` and then use it inside another colon word:

```forth
: square dup * ;
: old-square 6 square ;
```

Now replace the visible meaning of `square`:

```forth
code square
  vm.push(99)
end-code
```

What should happen here?

```forth
old-square square
```

Project K leaves:

```text
36 99
```

Why?

When `old-square` was built, it captured the **Word identity** of the old
`square`. Redefining the name changes future lookup; it does not silently
redirect references already compiled into existing colon definitions.

This is a subtle but important property of an evolving Forth system. A name can
move forward without secretly changing old compiled behavior.

Try **“4 · Captured binding”** in [`demo.html`](demo.html).

---

# Part III — Why a stack?

## 5. Data has to travel between words

Consider:

```forth
3 4 +
```

How does `+` know which values to add?

Project K uses the Forth data stack as the ordinary channel between operations.
The VM owns it:

```js
vm.push(3, 4);
const right = vm.pop();
const left  = vm.pop();
vm.push(left + right);
```

The public operations include:

- `push(...values)`
- `pop(depth = 0)`
- `peek(depth = 0)`
- `vm.dstack` for host-side inspection

Depth zero is the top.

The kernel does **not** need to know words such as `dup`, `swap`, or
`over`. Those can be vocabulary:

```forth
code pick
  vm.push(vm.peek(vm.pop()))
end-code

: dup  0 pick ;
: over 1 pick ;
```

The same question appears again: if a word can be grown, does it deserve to be
a seed primitive?

---

# Part IV — Input is not just split(" ")

## 6. TIB and itib

Forth has long had the idea of a current input buffer and a position within it.
Project K represents that explicitly with an `Input` object:

| Concept | Project-K v2 JavaScript |
| --- | --- |
| Logical TIB | `input.tib` |
| Character position | `input.itib` |
| Unread portion | `input.remaining` |
| Active input | `vm.input` |

Example:

```js
import { Input } from "./projectk.js";

const input = new Input("12 square .");
console.log(input.read());       // "12"
console.log(input.itib);         // 2
console.log(input.remaining);    // " square ."
```

Reading advances the cursor; it does not destroy the source.

Why bother keeping an explicit cursor?

Because an extensible language sometimes needs to consume **something other
than the next whitespace token**.

---

## 7. Let the current word decide how much input it needs

Imagine a word that wants all text up to `|`:

```forth
code text
  const value = vm.input.read("|").trimStart()
  if (vm.compiling) vm.literal(value)
  else vm.push(value)
end-code
immediate
```

Now this becomes possible:

```forth
: greeting text Hello from context-sensitive input!| ;
```

A global tokenizer could not know in advance that `text` wants that region.
The **current word** knows.

That is why Project K does not reduce input to an array of tokens at the front
door. General interpretation reads tokens, but extensions may consume source
according to their own syntax.

Try **“6 · Context-sensitive input”** in [`demo.html`](demo.html).

This is one of the mechanisms by which a small kernel gives the *user of the
language* some power to become a *designer of the language*.

---

# Part V — How does behavior become reusable?

## 8. Grow `:` and `;`

Project K's seed does not require colon syntax.

An extension can grow it:

```forth
code :
  vm.begin(vm.input.read())
end-code

code ;
  vm.finish()
end-code
immediate
```

Now:

```forth
: square dup * ;
```

becomes possible.

The host-side building interface is:

- `begin(name)`
- `comma(operation)`
- `literal(value)`
- `finish()`

A colon definition is not merely saved source that must be reparsed every time
it runs. Its action is an ordered sequence of captured operations and literals.

Try **“3 · Colon definition”** and then `see square` in the lab.

---

## 9. Why is `;` immediate?

While the VM is building a colon word, ordinary words are recorded for later
execution. But `;` must act **now**: it must finish the definition.

That is the purpose of an immediate word.

This reveals an important Forth idea: compile-time behavior is itself
extensible. The kernel does not need a giant parser containing special cases
for every future language construct. A word can participate in how definitions
are built.

The same principle can grow strings, conditionals, loops, and application
syntax.

The same small-kernel principle shows up here: **syntax itself can grow out of words.**

---

# Part VI — There are two different positions

## 10. What happens in `12 square .`?

There are two different journeys.

First, the **outer interpreter** walks through input:

```text
12 → square → .
^
input.itib moves through source text
```

When it reaches `square`, the **inner execution mechanism** walks through the
already-built colon body:

```text
square: [dup, *]
         ^
         frame.ip
```

These are not the same loop and not the same position.

- **Input cursor**: where interpretation has reached in source.
- **Frame IP**: where this invocation has reached in a colon program.

This distinction becomes essential once control flow or suspension can change
execution progress.

---

## 11. A Frame is “the program plus where this call has reached”

A colon Word answers:

> “What program makes up this word?”

A Frame answers:

> “Where has **this invocation** reached in that program?”

Conceptually:

```text
Frame = reference to colon program + this invocation's IP
```

The program is shared. The execution position is private.

The same Word could therefore have more than one invocation alive at different
positions:

```text
Word "work"
   ├── Frame A: ip = 2
   └── Frame B: ip = 5
```

This prepares us for the next question:

> If execution stops halfway, who remembers all of this?

---

# Part VII — State has an owner

## 12. VM state is not Task state

Project K deliberately assigns different state to different owners:

| Owner | State |
| --- | --- |
| VM | Data stack, vocabulary, host bindings, latest definition, unfinished colon definition |
| Task | Input contexts, return stack, T-stack, Frames, continuation, status, error |
| Word | Definition identity and executable behavior |
| Frame | One colon invocation's Word, body reference, and IP |

Why not put everything in the VM?

Because two unfinished activities may need separate execution progress even
while they share one vocabulary and one data stack.

Why not put the data stack inside each Task?

Because submissions on one Forth VM normally cooperate through persistent data.

The ownership model tells us what persists, what is private, and what may be
shared.

---

## 13. Data stack, return stack, T-stack, Frame stack

Project K distinguishes several stacks:

| Facility | Owner | Purpose |
| --- | --- | --- |
| Data stack `dstack` | VM | Ordinary values exchanged by words |
| Return stack `rstack` | Task | Extension-visible task-private auxiliary storage |
| T-stack `tstack` | Task | Additional temporary/control storage |
| Frame stack `frames` | Task | Internal unfinished colon invocations |

The T-stack is an explicit Project K facility. It is not the Frame stack and it
is not “a stack of Tasks.”

This separation matters when extensions build control structures. Temporary
markers should not accidentally become ordinary application data, and
invocation position should not have to masquerade as a user-visible return
value.

---

# Part VIII — Why does dictate() return a Task?

## 14. Normal work still creates a Task

Run:

```js
const task = vm.dictate("3 4 +");
console.log(task.status);   // done
```

Even though the work finished immediately, `dictate()` returns the execution
object that carried it out.

Likewise:

```js
const task = vm.execute("square");
```

starts one Word directly.

The important distinction is:

- `dictate(text)`: start work by interpreting input.
- `execute(word)`: start work from an operation.
- `yield* vm.evaluate(text)`: enter more input **inside the current Task**.
- `yield* vm.call(word)`: invoke more behavior **inside the current Task**.

Starting another Task and nesting work in the current Task are not the same
thing.

---

## 15. Now make the work stop halfway

Grow:

```forth
code pause
  yield vm.pause()
end-code

: journey 1 pause 2 ;
```

Then:

```js
const task = vm.dictate("journey 3");
```

At the pause:

```text
task.status   → "paused"
data stack    → [1]
```

Control has returned to JavaScript, but the work is not done.

Later:

```js
task.resume();
```

and the stack becomes:

```text
[1, 2, 3]
```

Try **“5 · Pause / resume”** in [`demo.html`](demo.html).

This is Project K's modern addition to the minimalist Forth story: the kernel
remains small, but an execution can retain its path while the host regains
control.

---

## 16. What did pause actually save?

This is the question to linger over.

A pause is useful only if “resume” knows what “continue” means.

The retained Task connects:

- the host-language continuation,
- nested input contexts,
- the current colon Frames and their IPs,
- private return and T-stacks,
- execution status.

Nothing keeps “running in the background.” Pause means exactly what it says:
the Task has yielded control.

This makes Project K suitable for work that must wait for something external
without turning the kernel into a scheduler.

---

## 17. Appending input is not the same as restarting

A paused Task with a live input context can accept more text:

```js
const task = vm.dictate("1 pause 2");
task.appendInput(" 3");
task.resume();
```

The result is:

```text
[1, 2, 3]
```

But once a Task is done, appending does not resurrect it. End-of-input is not a
secret “wait for more input” state.

Explicit states make the contract easier to reason about.

---

# Part IX — Work can enter more work

## 18. Nested evaluation preserves context

A host operation may do this:

```js
vm.define("nested", function* (vm) {
  const outer = vm.input;

  yield* vm.evaluate("10 pause 20");

  console.assert(vm.input === outer);
});
```

The nested input becomes active while it is being evaluated. When it finishes,
the enclosing input is restored.

The same idea applies to `yield* vm.call(word)`: a word can enter another
operation without inventing a new top-level Task.

This is what makes continuation composition useful rather than merely a
one-shot pause trick.

---

# Part X — Failure is not rollback

## 19. Failed, aborted, and cancelled mean different things

Project K distinguishes three forms of non-normal termination:

- **failed** — execution encountered an error;
- **aborted** — the running activity deliberately terminated itself;
- **cancelled** — the host abandoned a ready or paused Task.

These are not transactions.

If a word already pushed data, published a completed definition, changed the
DOM, or sent something to a host API, termination does not magically undo that
effect.

What Project K *does* protect is the integrity of an unfinished definition:
the applicable provisional definition is discarded, and an older published
binding remains visible.

This is an important engineering boundary. A small kernel should make its
guarantees clear rather than pretending to provide rollback it cannot provide.

---

# Part XI — The browser is not a wrapper; it is the host

## 20. Let Forth touch the web platform

In the Python implementation, host words can use Python modules and objects.

In the JavaScript version of Project-K v2, the browser itself offers a huge host environment:

- DOM
- `fetch`
- Canvas
- WebSocket
- Web Audio
- IndexedDB
- Web Workers
- WebGPU, where available

For example:

```forth
code title
  document.title = vm.pop()
end-code
```

Then:

```forth
s" Project K owns this browser tab" title
```

Try **“7 · Browser as host”** in [`demo.html`](demo.html).

Notice what the architecture does *not* require: DOM support inside the kernel.

The browser already knows the DOM. Project K only needs a way for a Word to
borrow host capability and present it through a Forth interface.

This is a modern expression of the same old minimalist instinct: **do not copy
into the kernel what the host already knows how to do.**

---

## 21. A note about browser security

`code ... end-code` dynamically compiles JavaScript host bodies. A page whose
Content Security Policy forbids dynamic code generation (`unsafe-eval`) can
therefore block host definitions.

That is a host security policy, not a Forth parsing failure.

Applications that must operate under a strict CSP can still register trusted
host operations directly with `vm.define()`, or can choose an integration
strategy appropriate to that environment.

---

# Part XII — From kernel to application: Sokoban-K

## 22. Does this architecture grow into anything real?

This is where the abstract pieces should earn their keep.

Open **[`games/sokoban.html`](games/sokoban.html)**.

Sokoban-K uses the same Project K kernel rather than embedding another copy of
it. The page imports:

```js
import { VM, Literal, KernelError } from "../projectk.js";
```

The game then grows its own vocabulary.

Movement is expressed as Forth words:

```text
u  d  l  r
```

The data stack records the path. `undo` can reverse a step. Control words grow
loops and conditionals. A successful route can be turned into a new colon word
and replayed later.

Meanwhile the browser host handles rendering, buttons, keyboard events,
`localStorage`, and timing.

That division is the point:

```text
Project K kernel
      ↓
game vocabulary
      ↓
browser host facilities
      ↓
Sokoban application
```

The kernel never had to learn what a box, wall, keyboard, or HTML element is.

A small kernel became an application because the system could grow.

That is where the eForth lineage becomes visible in the design itself.

---

# Part XIII — Testing the contract, not the host

## 23. Why one test suite has two runners

The behavioral tests live in **[test.js](test.js)**.

They test Project K concepts such as:

- minimal boot,
- growth from the seed,
- captured bindings,
- opaque host data,
- TIB/itib behavior,
- pause/resume,
- input append while paused,
- task-private stacks,
- nested evaluation,
- cross-submission colon definitions,
- partial failure,
- host-body boundaries,
- latest-definition behavior.

None of those test cases needs to *be* a Node test or a Browser test.

But the environments report tests differently, so there are two intentionally
thin adapters:

### Browser

Open:

**[`test-runner-browser.html`](test-runner-browser.html)**

It imports `test.js`, runs the cases, and renders pass/fail results into the
page.

### Node.js

If Node.js 18+ is available:

```sh
npm test
```

or:

```sh
node --test test-runner-node.js
```

The Node runner imports exactly the same `tests` array and adapts each case to
`node:test`.

The distinction is simple:

> **test.js says what must be true; a test runner says how this host executes
> and reports the tests.**

---

# Part XIV — Node.js is useful, but it is not the center

## 24. The same kernel works under Node

For command-line or automation work:

```js
import { VM } from "./projectk.js";

const vm = new VM();
vm.dictate("code answer vm.push(42) end-code answer");
console.log(vm.pop());
```

Node.js is a good JavaScript host. It is especially convenient for automated
tests.

It is simply no longer the assumption around which the JavaScript README is
organized.

Browser and Node host the same kernel; they offer different outside worlds.

---

# Part XV — Reading the implementation

## 25. A suggested route through projectk.js

Do not start by reading the file top to bottom.

Follow the execution questions:

1. **`VM.evaluate()`** — How does source become numbers and Word execution?
2. **`Input`** — How is source retained and consumed?
3. **`VM.call()`** — How are host and colon behaviors executed?
4. **`Frame`** — Where does one colon invocation remember its IP?
5. **`Task.resume()`** — What outcomes can execution have?
6. **`begin() / comma() / literal() / finish()`** — How is a colon Word built?
7. **`_hostDefinition()` and `hostBoundary()`** — How does the tiny seed grow
   JavaScript-backed words without mistaking `end-code` inside strings,
   templates, regexes, or comments for the real terminator?

Then return to the conceptual specification and ask whether the implementation
mechanism is serving the contract—or merely looking clever.

The specification is the design authority. JavaScript is one realization.

---

# Part XVI — Ready for AI, with no AI in the kernel

## 26. Why resumable Tasks matter later

There is no model client, agent loop, prompt system, or AI vocabulary inside
Project K.

That is deliberate.

But imagine a future word that starts an external AI request. The request may
take seconds. A traditional blocking call would trap the host; restarting the
Forth expression later would lose the execution path.

Project K already has another possibility:

```text
Forth execution
    ↓
start external request
    ↓
pause Task
    ↓
return control to host
    ↓
response arrives
    ↓
host supplies result
    ↓
resume same Task
    ↓
continue after the wait
```

Transport, scheduling, authentication, timeout policy, model selection, and
response delivery belong outside the kernel.

Again the small-kernel discipline helps: prepare the mechanism; do not confuse
one fashionable application with the kernel itself.

---

# Closing

Project K contains things eForth did not need to contain: JavaScript host
integration, explicit resumable Tasks, browser applications, and a path toward
future asynchronous or AI-assisted work.

Those mechanisms are new. The design principle is not: keep the kernel small,
understandable, and capable of growth.

**Small kernel. Extensible language. A modern continuation of the eForth idea.**
