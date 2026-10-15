# Project K — A Minimal Forth Kernel with Resumable Tasks

Project K grows from just two seed words into an extensible Forth system.
Its tasks can pause while waiting for external work, such as a future AI
response, and resume afterward. The kernel itself contains no AI integration.

## Quick Start: Hello World from the bare kernel

From the directory containing `projectk.py`, start Python:

```powershell
python
```

At the Python prompt, import the kernel and create a VM:

```pycon
>>> from projectk import Input, KernelError, VM, Task
>>> vm = VM()
>>> vm.dictate("code hi print('hello World!') end-code")
<projectk.Task object at ...>
>>> vm.dictate("hi")
hello World!
<projectk.Task object at ...>
```

The first `dictate()` defines a code word named `hi`; it does not run `hi`.
The second interprets the TIB `"hi"`, finds that word, and executes it.
This example uses only the two seed words `code` and `end-code`; no demo
vocabulary or console is needed.

`<projectk.Task object at ...>` is Python displaying the Task returned by
`dictate()`. The address varies. It is not an error or output from `hi`.
You can assign the result to a variable to suppress that automatic display:

```python
task = vm.dictate("hi")
print(task.status)                 # done
```

### Hello World as a colon definition

In the same Python session, enter the Forth console with its test vocabulary:

```pycon
>>> import demo
>>> demo.repl()
Forth test vocabulary loaded; enter source at k>.
Enter help for instructions; bye exits.
k> : hello s" Hello World!" . ;
k> hello
Hello World!
k>
```

Here `hello` is a colon word: `s"` supplies the string and `.` prints it.
Enter `bye` to return to Python. `demo.repl()` creates a new VM;
use `demo.repl(vm)` to work with the VM you already have.

## Continue with the Python lab


From the directory containing these files, run:

```powershell
python -m demo
```

The program runs the tests and opens a **Python REPL** at `>>>`. It provides:

- `vm`: a `VM` with the demonstration words already loaded.
- `VM`, `Task`, and the other imported kernel classes.
- `make_vm()`: construct another VM with those demonstration words.
- `repl(vm)`: an optional Forth console, if you want one later.

You are already in Python; there is no need to enter and leave a Forth console
to experiment with the kernel. You can also run:

```powershell
python -i demo.py
```

This runs the same tests and setup, then lets Python itself provide the REPL.
Plain `python demo.py` opens the lab too. Type `exit()` to leave Python.

At `>>>`, try the following Python statements. The examples omit the prompt
so they can be copied directly:

```python
vm.dictate(': square dup * ;')
vm.dictate('12 square .')           # Prints 144.
vm.dictate('see square')
vm.dictate('words')
```

`dictate()` returns a Task describing that execution. Python may display the
returned object for an unassigned expression. Assign it when you want to
inspect the result:

```python
task = vm.dictate('3 4 +')
print(task.status)                 # done
print(vm.pop())                    # 7
```

To run just the tests, without opening either console:

```powershell
python -B -m unittest -v demo
```

`projectk.py` contains only the kernel. Importing it starts no console and loads
no demonstration words. `demo.py` contains the tests, optional vocabulary, and
Python lab. It initializes `vm` only when launched as a program. From another
Python session, use `from demo import make_vm; vm = make_vm()`.
The implementation uses only the standard library.

## Starting small: mechanisms before vocabulary

A fresh `VM()` contains only `code` and `end-code`. They provide a way to
introduce operations implemented by the host. Those operations can establish
colon-definition syntax, stack operations, input parsing, and other facilities.

For example, `:` and `;` in the test vocabulary connect to the kernel's
`begin()` and `finish()` mechanisms. Once those words exist, further words can
be expressed as colon definitions:

```forth
: dup 0 pick ;
: over 1 pick ;
: swap 1 roll ;
```

The kernel supplies capabilities; the vocabulary determines how users combine
them. Even `help` is a colon definition containing a string literal and `.`.
`.s`, `words`, and `see` are code words in the test vocabulary.

This separation keeps the kernel small while allowing the surrounding system
to become much richer. Adding an application interface does not require making
that interface a new kernel feature.

## Words, code definitions, and colon definitions

A **word** is a named operation. A **definition** establishes its behavior;
“code word” and “colon word” identify two kinds of that behavior.

In traditional Forth, code definitions commonly introduce native CPU
primitives. Here the host language is Python, so a code definition creates a
Python callable. At the optional `k>` console:

```forth
code double vm.push(2 * vm.pop()) end-code
21 double .
```

This prints `42`. The equivalent host-side activity can also be registered
without parsing a code definition:

```python
from projectk import VM

vm = VM()
def double(vm):
    vm.push(2 * vm.pop())

word = vm.define('double', double)
vm.dictate('21 double')
assert vm.pop() == 42
assert callable(word.action)
```

This direct registration has category `host`; a word created through
`code ... end-code` has category `code` and retains its body source. Both
execute host callables.

A **colon definition** combines existing operations. At the optional `k>` console:

```forth
: twice double ;
21 twice .
```

To build a colon word directly through the Python API:

```python
from projectk import VM, Literal

vm = VM()
vm.define('double', lambda m: m.push(2 * m.pop()))
vm.begin('answer')
vm.literal(21)
vm.comma('double')
word = vm.finish()
assert word.category == 'colon'
assert isinstance(word.action, tuple)
assert isinstance(word.action[0], Literal)
assert word.action[1] is vm.tick('double')
vm.execute('answer')
assert vm.pop() == 42
```

The definition is a sequence of executable operations, not stored source text
that must be parsed again on every call. Literals push values; word references
invoke captured definitions.

## Dictionary and vocabulary

The **dictionary** makes definitions discoverable by name. **Vocabulary**
describes the available named operations. Traditional Forth systems may support
multiple vocabularies or word lists and a search order. This kernel currently
provides one mapping, not that larger search-order facility.

```python
from projectk import VM

vm = VM()
assert set(vm.words) == {'code', 'end-code'}
word = vm.define('answer', lambda m: m.push(42))
assert vm.words['answer'] is word
assert vm.tick('answer') is word
assert vm.tick('missing') is None
```

The test word `words` simply exposes this mapping's names. Neither dictionary
inspection nor the user interface requires a separate REPL command mechanism.

## Captured definitions and an evolving vocabulary

```forth
: square dup * ;
: old 6 square ;
code square vm.push(99) end-code
old square .s
```

The stack ends with `36` and `99`. `old` captured the original `square` Word
when it was built. Subsequent lookup of `square` finds the replacement.

Replacing a name's binding therefore does not redirect existing colon-body
references. This is consistent with the familiar behavior of compiled word
references in many Forth systems. It supports incremental vocabulary growth
without silently changing previously captured references.

Captured identity does not imply complete immutability. Modifying an existing
Word object or state used by its behavior can affect calls through that object.

## Python activities below, word interfaces above

A code word can import a Python module and expose its behavior through the
stack interface:

```forth
code sqrt import math; vm.push(math.sqrt(vm.pop())) end-code
: length-squared dup * swap dup * + ;
: length length-squared sqrt ;
3 4 length .
```

This prints `5.0`. The module provides a low-level activity. The code word
adapts it to the word interface. Colon words express the higher-level behavior.

Internal Python dependencies can be organized using modules and functions
instead of forcing every implementation helper into the Forth vocabulary.
The visible word-definition order then reflects more of the high-level
logical dependency and less of the low-level implementation detail.

Dependencies still exist. A colon definition must find the words it records
when it is built. In this example, `length-squared` and `sqrt` must exist before
`length` is defined. Layering reduces incidental vocabulary dependencies; it
does not eliminate genuine ones.

## TIB, input buffer, and input offset

**TIB** means **Terminal Input Buffer**: the traditional name for storage
holding terminal input to be interpreted. More generally, an interpreter has a
current input buffer whose text can come from a terminal, file, or evaluated
string. Standard Forth's `SOURCE` exposes the current buffer, and `>IN` gives
access to the character offset into that buffer. See
[`SOURCE`](https://forth-standard.org/standard/core/SOURCE) and
[`>IN`](https://forth-standard.org/standard/core/toIN).

Here those roles are represented by an `Input` object, whose `tib` holds the text and `itib` is its character offset:

| Input concept | Kernel representation |
| --- | --- |
| TIB / current input buffer | `Input.tib` |
| Character offset, analogous in purpose to `>IN` | `Input.itib` |
| Unread parse area | `Input.remaining` |
| Current input context | `vm.input` inside active execution |

The kernel does not install literal `TIB`, `SOURCE`, or `>IN` words. This is a
mapping of concepts, not a claim of standard-word implementation. The text is
a Python string rather than an address-and-length pair in flat memory.

```python
from projectk import Input

source = Input('12 square .')
assert source.read() == '12'
assert source.itib == 2
assert source.tib == '12 square .'  # Reading preserves the complete source.
assert source.remaining == ' square .'
saved = source.itib
assert source.read() == 'square'
assert source.itib == 9
source.itib = saved             # Rewind the input offset.
assert source.read() == 'square'
```

Each active evaluation creates an input context. Nested evaluation pushes
another context on `task.inputs` and restores the enclosing one afterward.
The contexts belong to the task that is interpreting them.

## A submission becomes a Task: dictate and execute

A **Task** is one execution of submitted work. TIB is its input text; Task is
the execution that carries it out. In the optional Forth console each line
submitted with Enter starts a Task. In Python, the boundary is a call to one
of these two entry points:

| Entry point | Work submitted | Return value |
| --- | --- | --- |
| `vm.dictate(tib)` | Interpret a TIB containing words and literals. | An already-started Task. |
| `vm.execute(word)` | Execute one named Word or Word object. | An already-started Task. |

A word may call many subwords. They normally belong to this same execution;
a Task is not created for every subword call. For now, use ordinary executions
that finish immediately:

```python
from demo import make_vm

vm = make_vm()
task = vm.dictate(': square dup * ; 12 square')
print(task.status)                 # done
print(vm.pop())                    # 144
vm.push(5)
task = vm.execute(vm.tick('square'))
print(task.status)                 # done
print(vm.pop())                    # 25
```

`dictate` reads source text; `execute` starts from a Word without requiring a
TIB. Both start work immediately. The Task owns the execution's inputs,
private stacks, and runtime call records. Its status tells the host the outcome.
The later sections introduce executions that do not finish immediately.

## Multiple VMs

`VM` is the kernel class; `vm` is an instance. Each VM has its own dictionary,
data stack, and execution state. Tasks on one VM share that VM's data stack
and definitions. Creating another VM creates a separate kernel environment:

```python
from projectk import VM

vm1 = VM()
vm2 = VM()
vm1.push(42)
vm1.define('answer', lambda vm: vm.push(42))
assert vm1.dstack == [42]
assert vm2.dstack == []
assert vm2.tick('answer') is None
```

Host objects deliberately supplied to more than one VM can still be shared.
There is no additional shared kernel environment above these VM instances.

## Data stack, return stack, and the new task stack

These are three distinct stacks:

| Stack | Kernel name | Owner and purpose |
| --- | --- | --- |
| Data stack | `vm.dstack` | Data shared within one VM exchanged by operations and submissions. |
| Return stack | `task.rstack`, exposed by `vm.rstack` | Task-private auxiliary storage; separate from the interpreter's Frame stack here. |
| Task stack / T-stack | `task.tstack`, exposed by `vm.tstack` | Additional task-private storage for temporary values and control markers. |

The **task stack**, or **T-stack**, is an explicit addition in this design,
alongside the familiar data and return stacks. Its current Python field is
named `tstack`; “task stack” and “T-stack” refer to that same facility. It is not the list of tasks, the Frame stack, or the host's call
stack. We are introducing a facility in Project K, not claiming that no earlier
Forth system has ever offered extra private stacks.

**Kernel excerpt — `Task.__init__`:**

```python
self.inputs = []
self.frames = []
self.rstack = []
self.tstack = []
```

Each construction allocates fresh lists. They are not class-level or
VM-global stacks. Words reach the active task's T-stack through this
**kernel property**:

```python
@property
def tstack(self):
    return self.task.tstack
```

The property is shown at class indentation in `projectk.py`; its meaning is to
route access through the innermost active task. A host sample makes the
separation observable:

```python
from demo import make_vm

vm = make_vm()
vm.define('save', lambda vm: vm.tstack.append(vm.pop()))
a = vm.dictate('10 save')
b = vm.dictate('20 save')
assert a.status == b.status == 'done'
assert a.tstack == [10]
assert b.tstack == [20]
assert a.tstack is not b.tstack
assert a.rstack is not b.rstack
```

These tasks have finished, but the Python variables still let us inspect their
separate stacks. A later submission receives a new task and a new T-stack;
it does not inherit either list. The shared data stack is different: it belongs
to the VM and survives across submissions.

Task-private storage is useful for application temporaries and control
markers. Later we will use it to retain a value while a task waits, after
introducing how Python represents an execution that can continue later.

## State has an owner

| Owner | State |
| --- | --- |
| VM | Shared data stack, dictionary, host bindings, latest-definition reference, and unfinished colon definition. |
| Task | Input contexts, return stack, task stack (T-stack), internal frame stack, status, and error. |
| Word | The definition and its program body, plus descriptive information and properties. |
| Frame | For a colon word, a reference to `word.action` plus this invocation's `ip` and Word reference; explained below. |

The data stack persists across submissions on the same VM. A task's return and task
stacks do not become the private stacks of the next submission.

Task-private state does not mean that every VM resource is isolated.
Tasks share data and definitions. A Frame is private execution state, while
the colon body it executes is shared definition state.

## Two interpreters, two execution positions

Consider this input:

```forth
12 square .
```

The outer interpreter reads `12`, `square`, and `.`. It searches the dictionary
before trying numeric conversion. When building a colon definition, it records
ordinary words and numeric literals; immediate words execute during building.
In this implementation, `evaluate()` performs that work.

When `square` runs, the inner interpreter executes its body:

```forth
: square dup * ;
```

It executes `dup`, then `*`, and returns to the surrounding evaluation. The
colon-body execution part of `call()` performs this work.

We first follow what these loops do through the public API. Their Python
implementation uses a feature introduced later: generators. The actual kernel
loops appear there, once that feature has been explained.

To observe both interpreters through the Python API:

```python
from projectk import VM
from demo import EXPLORER

vm = VM()
vm.dictate(EXPLORER)  # Explicitly load the optional test vocabulary.
vm.dictate(': square dup * ;')
vm.dictate('12 square')  # Outer interpreter reads text; square uses inner dispatch.
assert vm.pop() == 144
vm.push(5)
vm.execute('square')  # No outer text evaluation is needed for this invocation.
assert vm.pop() == 25
```

There are therefore two different positions:

- The **input cursor** identifies the next character in source text.
- The **Frame IP** identifies the next operation in a colon body.

Rewinding input makes the outer interpreter read text again. Changing a Frame
position directs execution within an already built colon definition. These
mechanisms act on different spaces and should not be described as one loop.

## Word-local program space rather than flat dictionary addresses

A common traditional threaded Forth stores colon bodies and dictionary data
in an addressable memory space. Execution positions and branch targets are
expressed using that memory representation. Other Forth implementations use
different layouts and compilation strategies.

Here a colon word holds its own sequence of operations. A Frame indexes that
sequence. A reference to another word captures the Word object rather than
an address that an extension must manage in a flat dictionary memory.

This is **word-local program space**: execution positions are interpreted
relative to the selected word's body. It is not a per-task copy of the program,
and it is not a security boundary. The body is shared; each invocation's
execution position is private.

The kernel does not supply a traditional flat-memory dictionary, address
arithmetic, or memory-access vocabulary. An extension could introduce a
memory abstraction if its application needed one.

## Frame: word.action plus an IP for this execution

For a **colon word**, start with this simple picture:

> A Frame is a runtime instance of `word.action`: the same program, plus an
> instruction pointer (`ip`) that records this execution's progress.

Conceptually:

```text
Frame = reference to word.action + this invocation's IP
```

`word.action` already contains the colon program. When the word runs, its
Frame adds the changing position needed to execute that program. The Frame
also remembers which Word was called. It does not copy the action tuple;
“runtime instance” means a separate execution context, not a separate program.

A word definition answers, “What operations make up this word?” Its Frame
answers, “Where has this execution reached?”

The same word can have multiple active invocations. Each needs a separate
position even though all use the same definition:

```text
Word: shared colon body
    ├─ Frame A: next operation is 2
    └─ Frame B: next operation is 5
```

**Kernel excerpt — the Frame representation:**

```python
@dataclass
class Frame:
    word: object
    colon_code: tuple
    ip: int = 0
```

`colon_code` refers to the colon body being executed; `ip` belongs to
this invocation. We can inspect Frames during an ordinary running call.

### From Word.action to a runtime Frame

In the kernel, that idea becomes:

```python
frame = Frame(word=word, colon_code=word.action)
```

This is a construction excerpt, not a command to run without defining `word`.
The Word is not converted into or replaced by a Frame. It remains in the
dictionary. Its action tuple is shared by reference, while the new Frame owns
an independent `ip`, initially zero. Calling the same word again creates
another Frame with another `ip`.

For a code word, `word.action` is a Python callable. Its execution does not
create a colon Frame; its Python execution state is carried by the host call
path and the host runtime.

### task.frames is the internal frame stack

The plural `frames` names an actual list in each Task. The kernel uses it as
a **frame stack**, pushing a Frame when a colon invocation begins and popping
it when that invocation finishes or is unwound. This is runtime state, with
last-in, first-out behavior. `task.frames[-1]` is the innermost active colon
invocation; `vm.frame` selects it while that task is running.

The frame stack is VM execution machinery, owned privately by each Task.
It is distinct from the three stacks exposed for word-level use:

| Structure | Contents | Managed by |
| --- | --- | --- |
| `vm.dstack` | Values exchanged by words and submissions | Words and host application |
| `task.rstack` | Task-private return-stack values | Words using return-stack facilities |
| `task.tstack` | Task-private temporary values and control markers | Words using T-stack facilities |
| `task.frames` — frame stack | Frames for unfinished colon invocations | Kernel, on colon entry and exit |

Observe the internal frame stack without stopping execution. The code word
`observe` runs inside the current task and records what it sees:

```python
from demo import make_vm

vm = make_vm()
observed = []
def observe(vm):
    observed.append(([f.word.name for f in vm.task.frames],
                     [f.ip for f in vm.task.frames]))

vm.define('observe', observe)
vm.dictate(': inner 1 observe 2 ;')
vm.dictate(': outer 10 inner 20 ;')
task = vm.execute('outer')
assert observed == [(['outer', 'inner'], [2, 2])]
assert task.frames == []
assert vm.dstack == [10, 1, 2, 20]
vm.dstack.clear()
```

At `observe`, both colon invocations are unfinished. The outer IP points to
literal `20`; the inner IP points to literal `2`. Each Frame is removed when
its invocation returns. `observe` is a code word and adds no colon Frame.

### Compile-time markers are a different kind of state

A compiler for control-flow words can use the data stack or a dedicated
control-flow stack to hold unfinished branch locations and other compilation
markers. Such markers describe the definition being built. Our current test
vocabulary does not yet provide those compiled control-flow words.

Those markers are not runtime Frames. The frame stack is created and changed
when colon words execute, including definitions that contain no conditionals
or loops at all. The separation is between building a definition and running
an invocation of it.

Traditional Forth already supports nested calls and recursion. In threaded
implementations, instruction pointers and saved return information perform
the corresponding work. Frame does not invent those capabilities.

What changes here is their representation: invocation state becomes an
explicit object owned by a task. It can be inspected and accessed by extensions. `vm.frame` exposes the innermost
active colon invocation; its `ip` identifies the next operation.

This removes the need to store an invocation's progress in the shared Word
or in one VM-global execution cursor. Control-flow extensions can change
the current Frame's IP without modifying another invocation's position.

The ownership relationships are:

```text
VM
    ├─ dictionary → shared Words and program bodies
    ├─ shared data stack
    └─ Tasks
         ├─ input contexts → outer-interpreter positions
         ├─ private auxiliary stacks
         └─ frame stack (task.frames) → unfinished colon invocations and their IPs
```

“Outer” and “inner” name execution mechanisms. Task and Frame name execution
contexts. They are not four interchangeable loops.

## Names used consistently in source and examples

| Name | Meaning |
| --- | --- |
| `Input.tib` | TIB: the source text being interpreted. |
| `Input.itib` | Character offset into that TIB, corresponding in purpose to `>IN`. |
| `vm.dstack` | Shared data stack. |
| `task.rstack` / `vm.rstack` | Task-private return stack; the VM property selects the active task. |
| `task.tstack` / `vm.tstack` | Task-private task stack, distinct from return and Frame stacks. |
| `Word.action` | A word's behavior: host callable or colon-code tuple. |
| `Frame.colon_code` | The colon-code tuple used by this invocation; shared with the Word's action. |
| `Frame.ip` | This invocation's next-operation index in `colon_code`. |
| `vm.tick(name)` | Find a Word, returning `None` if absent. |
| `vm.comma(operation)` | Compile one operation into the unfinished colon definition. |

`tick()` follows the purpose of Forth's tick but receives a Python name argument;
it does not parse the next TIB token. `comma()` compiles an operation rather than
writing a raw cell to a flat dictionary address. These are host API names, not
additional seed words. `Word.action` stays unified: it is not split into separate
code and colon fields. The builder accumulates `colon_code` as a list; finishing
publishes it as the Word's action tuple. A Frame refers to that tuple without
copying it.

## Python generators: creating a process is not running it

An ordinary Python function starts running when called. A function containing
`yield` is different: calling it creates a **generator object**. Its body starts
only when something drives that object, for example with `next()`.

Try this directly in the Python lab:

```python
def steps():
    print('before')
    yield 'checkpoint'
    print('after')

g = steps()                        # Nothing printed: only creates the generator.
print(type(g).__name__)             # generator
value = next(g)                     # Prints before, then suspends at yield.
print(value)                       # checkpoint
```

The suspended generator retains enough execution state to continue after its
`yield`. Continue it:

```python
try:
    next(g)                        # Prints after.
except StopIteration:
    print('finished')
```

`StopIteration` means that the generator finished. It is not a kernel failure.
A generator does not run in a background thread while suspended.

### Why evaluate() appears to do nothing

`evaluate()` and `call()` are generator functions too. Calling them returns
generators, not Tasks, and does not yet execute their bodies:

```python
g = vm.evaluate('3 4 +')
print(type(g).__name__)             # generator
```

Unlike the small `steps()` example, `evaluate()` accesses the active Task
while it interprets the TIB. That Task owns the input context and private
stacks. A bare `next(g)` does not establish that context:

```python
try:
    next(g)
except KernelError as error:
    print(error)                   # No active task
```

We can still run `evaluate()` directly as an experiment, by giving its
generator to a Task. Create a fresh generator: the failed attempt above has
already terminated the old one.

```python
from projectk import Task

g = vm.evaluate('3 4 +')            # Create the evaluation; nothing runs yet.
task = Task(vm, g)                  # Give it an execution owner; still not running.
print(task.status)                 # ready
task.resume()                      # Establish the active Task and drive g.
print(task.status)                 # done
print(vm.pop())                    # 7
```

The generator `g` is the evaluation process. `task.resume()` makes this Task
active, then advances that same generator. `evaluate()` can now attach its
input context to the Task, interpret `3 4 +`, and finish.

Now the connection to `dictate()` is visible: it packages those same steps.
Its implementation is:

```python
def dictate(self, tib):
    return Task(self, self.evaluate(tib)).resume()
```

This is a kernel excerpt, not a function you need to define. For everyday
use, the manual `evaluate` → `Task` → `resume` sequence becomes:

```python
task = vm.dictate('3 4 +')
print(task.status)                 # done
print(vm.pop())                    # 7
```

Both examples execute an evaluation generator under a Task. `dictate()` is
the convenient entry point, not a different way of interpreting the TIB.

The four APIs deliberately return two different kinds of objects:

| API | Immediate return | Execution |
| --- | --- | --- |
| `dictate(tib)` | An already-started Task | Creates a task and drives evaluation until pause or termination. |
| `execute(word)` | An already-started Task | Creates a task and drives the word until pause or termination. |
| `evaluate(tib)` | A generator | Must be driven within an active task. |
| `call(word)` | A generator | Must be driven within an active task. |

All four paths can participate in pausing. The difference is task creation and
who drives the generator, not whether pausing is allowed. Computed values are
normally exchanged on the data stack; they are not the generator object itself.

### Following evaluate and call through the kernel

With generator creation and driving now established, the outer and inner
interpreter implementation can be read directly:

**Kernel excerpt — the outer loop in `VM.evaluate()`:**

```python
while (token := source.read()) is not None:
    word = self.tick(token)
    if word is None:
        value = self.number(token)
        if self.compiling:
            self.literal(value)
        else:
            self.push(value)
    elif self.compiling and not word.immediate:
        self.comma(word)
    else:
        yield from self.call(word)
```

This is the token-reading loop. It can execute a word or build a colon body;
“outer” does not mean that it only runs at the terminal prompt.

**Kernel excerpt — colon-body dispatch in `VM.call()`:**

```python
frame = Frame(operation, action)
frames = self.task.frames
frames.append(frame)
try:
    while frame.ip < len(frame.colon_code):
        if frame.ip < 0:
            raise KernelError("Negative execution position")
        step = frame.colon_code[frame.ip]
        frame.ip += 1
        yield from self.call(step)
finally:
    frames.pop()
```

Here `action` is the colon body's tuple. This loop fetches an operation by
index, advances the invocation's position, and calls the operation. A nested
colon call creates another Frame; a code word executes its host callable.
The `finally` removes this Frame when its invocation ends or is unwound.

`dictate` and `execute` supply the Task that drives these generators:

```python
def dictate(self, tib):
    return Task(self, self.evaluate(tib)).resume()

def execute(self, operation):
    return Task(self, self.call(operation)).resume()
```

These are kernel excerpts, not functions to paste into the lab. For nested
work within an existing Task, the code uses `yield from evaluate(...)` or
`yield from call(...)`. To understand what yielding through that call path
makes possible, we can now return to pause and resume.

## Continuation: remembering where to continue

A **continuation** is the execution state needed to continue work later. Here
Python generators retain the suspended call path and local state, while Frames
make colon-word positions explicit. Task provides the owner and lifecycle for
that execution. The generator object is a mechanism used to retain a
continuation; it is not itself a Task or a scheduler.

The lab provides `activity(vm)` for this experiment. Its definition is shown
below; you can also define it
at the Python prompt:

```python
def activity(vm):
    print('before')
    yield from vm.evaluate('1 pause 2')
    print('after')
```

`before` and `after` are diagnostic output only. They are not stack values or
preparation required by the computation.

Register it, then execute it in a new Task:

```python
vm.dstack.clear()
vm.define('activity', activity)
task = vm.execute('activity')        # Prints before; after has not run.
print(task.status)                  # paused
print(vm.dstack)                     # [1]
```

`yield from` drives the nested evaluation and passes its yielded pause signal
outward. The existing Task receives the signal and returns control to Python.
The host function remains suspended while waiting for its nested evaluation.
No second Task was created by `evaluate()`.

```python
task.resume()                       # Inner evaluation pushes 2, then prints after.
print(task.status)                  # done
print(vm.dstack)                     # [1, 2]
vm.dstack.clear()
```

The nested evaluation completes before `print('after')` runs. Replacing
`yield from vm.evaluate(...)` with an ordinary call would merely create an
undriven generator and would not perform that evaluation. The same rule applies
to `yield from vm.call(word)` for a nested word invocation.

## Pause and resume preserve the work

```python
vm.dstack.clear()
vm.dictate(': calculation 3 dup * pause 4 dup * ;')
task = vm.execute('calculation')
print(vm.dstack)                   # [9]
task.resume()
print(vm.dstack)                   # [9, 16]
vm.dstack.clear()
```

After the pause, the stack contains `9`. Resuming continues after the pause,
producing `16` as well. The VM does not restart `calculation` or reread
its input from the beginning.

A task retains the continuation needed to continue nested evaluation and word
calls. In this Python implementation, generators preserve the suspended call
path. A host operation that needs to preserve its own internal progress uses
`yield vm.pause()` and continuation-aware calls with `yield from`.

The optional Forth console keeps its paused input tasks in a registry. The `resume` code word
continues the most recently registered paused task. That registry and its
selection policy belong to the test host. Imported kernel users can instead
retain the task returned by `dictate()` and invoke `task.resume()` directly.

Pausing is cooperative. There is no automatic scheduler or preemptive
execution. A completed task cannot be revived; source can be appended only
while a task still has a live input context.

## Inspecting Frames while a Task is paused

We first inspected Frames from a running code word. A pause now gives us
another way: inspect them from Python before allowing execution to continue.

`colon_code` refers to the colon body being executed; `ip` belongs to
this invocation. You can inspect it while the task is suspended:

```python
from projectk import VM
from demo import EXPLORER

vm = VM()
vm.dictate(EXPLORER)
vm.dictate(': work 1 pause 2 ;')
task = vm.dictate('work')
assert task.status == 'paused'
assert len(task.frames) == 1
frame = task.frames[-1]
assert frame.word is vm.tick('work')
assert frame.colon_code is frame.word.action
assert frame.ip == 2  # Next is the literal 2, after literal 1 and pause.
task.resume()
assert vm.dstack == [1, 2]
assert task.frames == []
```

You can inspect the internal frame stack from Python. Starting with a ready
lab `vm`, enter:

```python
vm.dstack.clear()
vm.dictate(': inner 1 pause 2 ;')
vm.dictate(': outer 10 inner 20 ;')
task = vm.execute('outer')
print([frame.word.name for frame in task.frames])  # ['outer', 'inner']
print([frame.ip for frame in task.frames])         # [2, 2]
print(vm.dstack)                                  # [10, 1]
assert task.frames[0].colon_code is vm.tick('outer').action
assert task.frames[1].colon_code is vm.tick('inner').action
task.resume()
print(task.frames)                                # []
print(vm.dstack)                                  # [10, 1, 2, 20]
vm.dstack.clear()
```

While `inner` is paused, `outer` is also unfinished. Its Frame remembers that
its next operation is the literal `20`; the inner Frame remembers the literal
`2`. Resuming completes `inner` and pops its Frame, then continues `outer`
and eventually pops that Frame too. The data stack contains the computation's
values throughout; it does not contain either Frame.

## Seeing task-private state in action

Why should a task have private storage? Suppose an operation saves something,
pauses, and uses that saved value later. While it is paused, another submission
may run. Its temporary values should not overwrite those of the suspended work.

The shared data stack is meant for exchanging values across operations and
submissions. Temporary progress belongs to the execution that will use it.
The distinction becomes visible with a small example you can run here.

At the optional `k>` console, enter each line separately:

```forth
code remember vm.tstack.append(vm.pop()) end-code
code recall vm.push(vm.tstack.pop()) end-code
10 remember pause recall .
20 remember recall .
resume
```

The first two lines define code words using a private stack already provided
by the kernel. `remember` moves a value from the shared data stack to the
current task's T-stack. `recall` moves it back.

The third line saves `10` and pauses. That task still owns its T-stack,
which contains `10`. The fourth line starts another task, saves `20` in its own
T-stack, retrieves it, and prints `20`. Finally, `resume` continues the
first task: it retrieves and prints `10`.

```text
Task A: T-stack [10] → pause → resume → recall → print 10
Task B: T-stack [20] → recall → print 20 → done
```

No private value was passed from Task A to Task B. They used the same words,
but those words accessed the currently running task's storage. The return
stack has the same task-private ownership, although this example uses the
separate T-stack.

Private storage does not persist automatically into the next submission.
For example, `10 remember` finishes one task; entering `recall` on the next
line creates another task with an empty T-stack. To retain progress
for later continuation, keep the original task alive by pausing it.

## From saved values to input control flow

A saved value can also describe where execution should continue. To see the
connection, imagine an extension that repeats a region of input text.

It would need to:

1. Save the input cursor just before the region begins.
2. Let the outer interpreter evaluate that region.
3. Restore the saved cursor when another repetition is needed.
4. Remove the saved position when the loop finishes.

The saved cursor is a temporary control value. If this evaluation pauses,
that value must remain available to its task. If another submission runs,
its loop markers must be kept separately. Task-private storage provides a
place for those markers; input cursor access supplies the navigation mechanism.

This would be an **interpretation-time loop**: it repeats source text by moving
the outer interpreter's cursor. A loop inside a compiled colon definition
instead changes a Word Frame's IP in the colon body. The two mechanisms
operate on different program representations.

This project's demonstration vocabulary does not yet define input-loop words. The
example above demonstrates the available private-storage mechanism without
requiring any such extension.

### A reference implementation: peforth

peforth is a separate Python-hosted Forth project used as a design reference.
Its optional vocabulary demonstrates how these mechanisms can be combined.
You do not need to install it or read its source to follow this explanation.
The following words belong to that project, not to the test console here.

Its `[begin]` word saves the current input cursor on the task's temporary
stack, called the T-stack there. `[again]` retrieves that saved cursor and
restores the input position, so the outer interpreter reads the region again.
An unconditional loop needs an exit or termination mechanism to stop repeating.

Its bracketed conditionals select regions of source: `[if]` consumes a flag;
a false flag causes input to be skipped to the corresponding `[else]` or
`[then]`. `[else]` skips the alternative region after the true region has run,
and `[then]` marks the end of the conditional. When scanning nested groups,
the implementation temporarily stores their nesting depth on the task's
T-stack. Quoted strings and comments are handled so that text inside them is
not confused with conditional markers.

Bracketed conditionals have a traditional counterpart in the standard
[conditional-compilation words](https://forth-standard.org/standard/tools/BracketELSE).
The point of this reference is how peforth assigns temporary control state
to the executing task, rather than the mere existence of conditionals.

Separate tasks get separate T-stacks. Nested input contexts within
one task still share that task's stack, so extensions must balance their
markers and clean them up when finished. Private ownership helps organize
state; it does not remove the need for disciplined use.

## Who keeps a Task alive?

Executing without assigning the result still runs the work:

```python
vm.define('activity', activity)      # Register it on the current VM.
vm.execute('activity')              # Prints before and returns a paused Task.
```

But this is a poor way to manage work that may pause. Retain the returned Task
if you intend to resume or cancel it. Python's interactive shell may keep an
unassigned result in `_`; that convenience is not a task-management policy.

A completed Task with no remaining references can be reclaimed by Python.
A paused Task with no remaining references can also become collectible, but
then the application has lost its resume handle. It does not keep running in
the background. Reclamation is not a promise to finish or explicitly cancel
the abandoned activity; cleanup timing should not be used as an application
lifecycle mechanism.

Reassigning a variable does not cancel its old Task. Keep separate handles
when there is more than one unfinished activity:

```python
vm.dstack.clear()
first = vm.execute('activity')       # Prints before; retains the first Task.
second = vm.execute('activity')      # Prints before; retains another Task.
print(first is second)              # False
first.resume()                      # Prints after; completes the first.
second.cancel()                     # Deliberately abandons the second.
print(first.status, second.status)  # done aborted
vm.dstack.clear()
```

If both assignments used `task`, the second assignment would only replace
that variable's reference. A registry or another variable might still retain
the old Task; otherwise it becomes eligible for collection once no references
keep it reachable. Internal cycles may delay collection. There is no automatic
VM-wide registry of every Task ever created.

The rule is: **the host that starts work decides who owns its handle and who
will complete or cancel it.** The optional Forth console supplies one registry;
the Python lab leaves handles under your direct control.

Completed effects survive Task disposal. Data already pushed onto the shared
stack, published words, and host side effects are not rolled back when a Task
is collected or cancelled. Host resources need their own appropriate cleanup.

## Reading the implementation

Start with `VM.evaluate()` for the outer interpreter, then
`VM.call()` for host-operation and colon-body execution. Read `Frame`
for invocation position and `Task.resume()` for execution outcomes and
continuation. `Input` supplies source navigation. `begin()`, `comma()`,
`literal()`, and `finish()` build colon definitions.

The [conceptual specification](../docs/project-k-conceptual-spec.md) describes the
behavioral contract. The tests exercise that contract; the optional vocabulary
shows how a small kernel grows into an interactive system.

Integers follow Python integer parsing and have arbitrary precision; floating
point follows `float()`. Host definitions execute ordinary Python with host
capabilities. Tasks share VM state and are not thread-safe. Failure,
abort, and cancellation preserve completed effects rather than rolling them
back. There is only one unfinished colon definition per VM, so task-private
frames and stacks do not make simultaneous definition building independent.

## Ready for future AI integration, with no AI in the kernel

There is no AI client, model, agent loop, or AI vocabulary in this kernel or
its demonstration environment. Everything above works without AI. AI remains
outside the kernel, in a future host integration.

The preparation is the ability to retain work while something external takes
time. A future code word could send a request to an AI service and yield the
pause signal. The Task returns control to the host with its execution context
intact. When the answer arrives, the host can supply the result and resume
that same Task. Execution continues after the wait rather than starting over.

The host must connect the response to the right Task and decide when to resume
it. Transport, scheduling, errors, cancellation, and result delivery are not
implemented by this kernel. A generator alone does not make a blocking network
call asynchronous; the integration must arrange for the wait to yield control.

Words provide capabilities, Frames record word-invocation progress, and Tasks
retain the execution path across a pause. This is the foundation prepared for
AI; the AI itself is deliberately not present here.
