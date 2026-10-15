# Project K — A Minimal Forth Kernel with Resumable Tasks

Conceptual Specification

## 1. Purpose

Project K is a small, extensible execution system that grows from a minimal seed. It lets a host application introduce primitive operations, combine them into new operations, and evaluate input using the resulting vocabulary.

The kernel supplies mechanisms for defining, finding, composing, and executing operations. Higher-level syntax and facilities are built through those mechanisms rather than imposed as a fixed language.

This specification describes concepts and observable behavior. It does not prescribe a programming language, object representation, memory layout, or implementation technique. The more mature Project K implementation is the behavioral reference; implementation accidents are not automatically requirements.

## 2. Fundamental concepts

**VM.** A persistent environment containing a vocabulary, a data stack, host bindings, and the current colon-definition building state. Separate VMs have independent kernel state. Objects intentionally supplied by a host may still be shared.

**Word.** A named operation. Its behavior is either supplied by the host or composed from other operations. A word may also carry descriptive information and extension-defined properties.

**Vocabulary.** The VM's mapping from names to currently visible words. Names are case-sensitive, nonempty, and contain no whitespace.

**Data stack.** An ordered collection of values shared by executions on the same VM. The most recently added value is the top. Values need not be restricted to numbers or text; they may include host resources and other opaque values.

**Input context.** A TIB (Terminal Input Buffer) together with itib, the character offset of its next unread character. Here TIB names the logical input text regardless of whether its source is a terminal or a host submission.

**Task stack (T-stack).** An additional task-private stack for temporary values and control markers, separate from the data stack, return stack, and invocation frames.

**Task.** One execution and its retained continuation. A task can complete, pause, abort, or fail. A paused task can resume from its suspended position.

**Colon definition.** A word whose executable behavior is an ordered sequence of operations. The term names the kind of definition; it does not require a particular implementation language or representation.

**Frame.** A runtime instance of a colon definition: a reference to its program plus an instruction pointer (IP) for this invocation, together with the invoked word's identity. The program is shared rather than copied; invocation progress is separate.

**Frame stack.** A task-private, last-in, first-out collection of unfinished colon invocations. It belongs to the execution engine, distinct from the data stack, return stack, task stack, and compile-time control-flow markers. Its physical representation is implementation-dependent.

**Literal.** An operation that places a captured value on the data stack when executed.

**Immediate word.** A word that executes during colon definition building instead of being recorded for later execution.

## 3. Minimal seed and extensibility

A newly created VM exposes two seed words: `code` and `end-code`. Together they allow source input to introduce a host-defined operation under a vocabulary name.

The kernel delegates the meaning and validity of the host-operation body to the host execution environment. No particular host programming language is required by this conceptual specification. Host-defined operations act with the capabilities provided by that environment.

The kernel must distinguish an actual definition terminator from the same text appearing as quoted data or a comment in the host body, according to the host body's lexical rules.

The seed is sufficient to introduce extensions that manipulate stacks, read input, begin and finish colon definitions, mark words as immediate, and invoke other operations. Familiar syntax for colon definitions, strings, constants, variables, arithmetic, control flow, and interaction may be constructed in the extension layer.

These higher-level words are not part of the initial vocabulary merely because a demonstration or an application supplies them.

## 4. Vocabulary and definition identity

Looking up a name returns its currently visible word, or an absent result if no word has that name. Looking up an absent name is distinct from attempting to execute one; execution requires a valid operation.

Publishing a new definition under an existing name replaces that name's visible binding. Existing colon definitions retain the word identities they captured when built. Rebinding a name therefore changes subsequent lookup without redirecting existing compiled references.

Capturing identity does not imply that every property of the captured word is immutable. Extensions may modify word objects and associated state where the system exposes that capability.

The VM also exposes the most recently defined word. During colon definition building, this reference identifies the provisional word being built. Discarding that unfinished definition restores the preceding reference.

Descriptive information may include a word's category, source, help, comments, and extension properties. Such information supports inspection and tooling; it does not by itself determine execution semantics.

## 5. Input model

An input context contains one logical text sequence, TIB, and a character-position cursor, itib. Reading advances the cursor without deleting the consumed text. Both consumed history and unread text remain identifiable from the source and cursor.

The input mechanism supports:

- Reading the next whitespace-delimited token, consuming leading whitespace and the token.
- Reading text up to a specified boundary, returning the preceding text and consuming the boundary.
- Reading up to a pattern-defined boundary that consumes at least one character.
- Consuming a requested nonnegative number of characters, limited by the available text.
- Consuming and returning all remaining text.
- Appending text at the source's tail without moving the cursor.

Token reading returns an end-of-input result when no token remains. A requested boundary that cannot be found is an input error. An empty boundary or a zero-width matched boundary is an error. Boundary-search failure does not advance the cursor.

Appending does not insert separators. The caller is responsible for any whitespace or other delimiter needed between existing and appended text. Appended text is read after existing unread text unless an extension explicitly changes the input position.

Extensions may use the input cursor to implement interpretation-time repetition or other source navigation. The kernel does not supply those constructs as initial words.

## 6. Evaluation

Evaluation repeatedly reads a token from the active input context and performs these steps:

1. Look up the token in the vocabulary.
2. If a word exists, execute it in interpretation mode. During colon definition building, record it unless it is immediate; execute immediate words at once.
3. If no word exists, attempt numeric interpretation. Place the resulting value on the data stack in interpretation mode, or record it as a literal during colon definition building.
4. If neither lookup nor numeric interpretation succeeds, report an error.

Vocabulary lookup takes precedence over numeric interpretation. An extension can therefore define a word whose name would otherwise be interpreted as a number.

Numeric interpretation supports signed decimal integers, integers with recognized radix prefixes, and floating-point values. Integer interpretation takes precedence so that large integers are not unnecessarily converted through an inexact floating-point representation. A concrete implementation must document its numeric syntax, range, and precision.

End of input completes that evaluation. It does not implicitly finish or reject an unfinished colon definition; a colon definition may be continued by a later evaluation on the same VM.

## 7. Colon definition building

The VM supports one unfinished colon definition at a time. Beginning another while one is active is an error.

Beginning a colon definition creates a provisional word and an initially empty sequence. The provisional word is available as the latest definition but is not published as the new vocabulary binding until finishing succeeds. An older binding under the same name remains visible in the meantime.

The builder can record word references, host operations, and literal values. Recording a word by name resolves its identity when recorded, not when the colon definition later executes.

Finishing installs the recorded sequence as the word's behavior and publishes the new binding. Attempting to record or finish without an active definition is an error. The seed host-definition mechanism cannot be invoked to build a host definition inside an unfinished colon definition.

Colon definition execution processes operations in sequence. Extensions can implement control flow through execution-position facilities. The particular instruction representation and control-flow vocabulary are outside this conceptual specification.

## 8. Tasks and continuations

Starting evaluation or execution creates a task and runs it immediately until it pauses or reaches a terminal outcome.

A task has these states:

| State | Meaning |
| --- | --- |
| Ready | Created but not yet running. |
| Running | Currently executing. |
| Paused | Suspended with a continuation available. |
| Done | Execution completed normally. |
| Aborted | Execution was deliberately terminated. |
| Failed | Execution terminated with an error. |

Only ready or paused tasks may be resumed. A resume continues until the next pause or terminal outcome. Terminal tasks cannot be resumed.

Pausing is cooperative: an operation explicitly requests that execution return to the host. The system retains the continuation needed to resume the surrounding colon definition and evaluation. Host-defined operations that need to retain their own internal continuation must use the host integration's continuation-aware execution mechanism.

Evaluating additional input or invoking an operation within the current task preserves that task's context. Starting a separate execution creates a distinct task, even when initiated by an operation already running on the VM. These two forms of invocation must remain semantically distinct.

A task with an active input context may append source to its innermost active input. Appending to a terminal task or a task without active input is an error. A completed task cannot be revived by appending source. End of input is not an implicit wait for future input.

The system is cooperative. This specification does not require threads, preemptive scheduling, persistent continuations, or automatic scheduling of paused tasks.

## 9. State ownership

| VM state | Task state |
| --- | --- |
| Vocabulary and visible bindings | Nested active input contexts |
| Data stack | Return stack |
| Host bindings | Task stack (T-stack) |
| Latest-definition reference | Execution status and failure information |
| Unfinished colon definition | Task continuation and internal frame stack |

The return stack and task stack (T-stack) are separate task-private facilities available to extensions. The kernel need not install words for manipulating them in its seed vocabulary.

An operation requesting the active input, return stack, or task stack must have the corresponding active task context. The innermost running task supplies that context.

Nested evaluation restores the enclosing input context on completion or termination.

Task-private state does not make tasks independent VMs. They share the data stack, vocabulary, and colon-definition building state. General safety for arbitrarily interleaving paused tasks, especially while building definitions or manipulating execution frames, is not established by this contract. A concrete implementation must document any stronger scheduling guarantees.

## 10. Stack operations

The data-stack interface supports adding values, removing the top value, inspecting a value at a specified depth, and removing a value at a specified depth. Depth zero denotes the top.

Inspection leaves the stack unchanged. Removal preserves the relative order of the remaining values. Invalid depths and removal from an empty stack are errors.

The kernel does not prescribe a complete stack-manipulation vocabulary. Operations such as duplication, swapping, arithmetic, and display can be provided by extensions.

## 11. Errors, abort, and cancellation

Errors include unknown input, invalid definitions, missing input boundaries, invalid stack access, invalid task transitions, and failures of host-defined operations.

Execution failure marks the task as failed, retains failure information, and reports the failure to the host. Host-operation diagnostics should identify the failing operation and preserve the underlying cause where possible.

An executing task may deliberately abort. A ready or paused task may be cancelled. A running task must terminate through the active execution's abort mechanism rather than external cancellation.

Termination releases suspended execution and input contexts. Abort or failure discards the VM's unfinished colon definition if one exists. Cancellation discards an unfinished colon definition when it belongs to the cancelled task. These rules do not provide isolation for unrelated tasks building on the same VM.

Abort, failure, and cancellation are not transactions. They do not undo stack changes, completed definitions, or host side effects already performed. Discarding an unfinished replacement preserves the previously published definition.

## 12. Kernel boundary

The kernel is responsible for vocabulary identity, data-stack access, input consumption, colon definition building and execution, active task context, cooperative continuation, and execution outcomes.

Extensions and hosts are responsible for their chosen vocabulary, application behavior, user interface, resource access, persistence, and scheduling policy.

A console, file loader, agent integration, network interface, or application-specific vocabulary can be built around the kernel without becoming a kernel requirement. The same applies to particular names and syntax for loops, conditionals, constants, variables, and string literals.

## 13. Behavioral acceptance scenarios

A conforming design should demonstrate these outcomes independently of implementation language:

1. **Minimal boot:** a new VM exposes only the two seed words before extensions are loaded.
2. **Growth:** host-defined words establish colon definition syntax, which then defines and executes a new colon word.
3. **Binding capture:** a colon definition retains its previously captured word after that name is rebound; direct lookup finds the replacement.
4. **Opaque data:** a host resource can pass through the data stack without being converted to text or a number.
5. **Input position:** reading advances the character cursor while retaining source history; appending preserves the cursor and existing unread text.
6. **Suspend and continue:** execution pauses inside a colon definition, returns to the host, and resumes with the remaining operations and input intact.
7. **Append while paused:** evaluating `1 pause 2`, appending ` 3`, and resuming produces data-stack values `1`, `2`, `3` in that order, assuming a pause word has been installed.
8. **Terminal input:** appending to a completed task fails instead of restarting execution.
9. **Private auxiliary stacks:** separate tasks have distinct return and task stacks while sharing their VM's data stack.
10. **Nested evaluation:** additional evaluation within a task restores the outer input context afterward.
11. **Definition across inputs:** a later evaluation can finish a colon definition begun by an earlier evaluation on the same VM.
12. **Partial effects:** an error or cancellation preserves completed effects while discarding the applicable unfinished definition.
13. **Host-body boundaries:** terminator text inside quoted data or comments does not prematurely end a host definition.

## 14. Design principle

Project K provides a small set of mechanisms through which a host and an evolving vocabulary can define their own execution language. Its conceptual identity rests on extensible named operations, stack-based value exchange, captured word bindings, explicit input position, and cooperative resumable execution.
