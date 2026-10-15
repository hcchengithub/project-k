/*
 * Project K, implemented from its conceptual specification (JavaScript).
 *
 * Only code/end-code belong to a new VM.
 * Host bodies use JavaScript and receive `vm` plus copied host bindings.
 * A host body is compiled as a generator function, so it may `yield vm.pause()`
 * or `yield* vm.evaluate(...)` like any other continuation.
 *
 * Numbers: decimal and 0x/0o/0b integers, then floats.  Integers within the
 * safe range are Numbers; larger ones are BigInt so no precision is lost.
 * Tasks are cooperative and not thread-safe.  Frames are task-private, but the
 * data stack, vocabulary and single unfinished definition remain shared.
 *
 * Tested on Node (>= 18).  The kernel imports nothing from Node, so it should also load as
 * an ES module in a browser; that has not been tried yet.
 */

export class KernelError extends Error {
  constructor(message, options) {
    super(message, options);
    this.name = "KernelError";
  }
}

// Thrown by vm.abort(); deliberately not an Error so host code cannot mistake it for one.
class Abort {}

const PAUSE = Symbol("pause");
const ALL = Symbol("all");
const MAX_SAFE = BigInt(Number.MAX_SAFE_INTEGER);
const GeneratorFunction = Object.getPrototypeOf(function* () {}).constructor;
const INSPECT = Symbol.for("nodejs.util.inspect.custom");
const isGenerator = (x) => Object.prototype.toString.call(x) === "[object Generator]";

const RESERVED = new Set(
  ("break case catch class const continue debugger default delete do else enum export extends " +
   "false finally for function if import in instanceof new null return super switch this throw " +
   "true try typeof var void while with yield let static implements interface package private " +
   "protected public await arguments eval").split(" "));

export class Input {
  constructor(tib = "", itib = 0) {
    if (typeof tib !== "string") throw new KernelError("TIB must be text");
    this.tib = tib;
    this.itib = itib;
  }

  get itib() { return this._itib; }
  set itib(value) {
    if (!Number.isInteger(value) || value < 0 || value > this.tib.length) {
      throw new KernelError("itib is outside TIB");
    }
    this._itib = value;
  }

  get remaining() { return this.tib.slice(this._itib); }

  append(text) {
    if (typeof text !== "string") throw new KernelError("Appended input must be text");
    this.tib += text;
  }

  consume(count) {
    if (!Number.isInteger(count) || count < 0) {
      throw new KernelError("Character count must be a nonnegative integer");
    }
    const result = this.remaining.slice(0, count);
    this.itib += result.length;
    return result;
  }

  rest() { return this.consume(this.remaining.length); }

  read(until = null) {
    const text = this.remaining;
    if (until === null || until === undefined) {
      const match = /\S+/.exec(text);
      if (match === null) {
        this.itib = this.tib.length;
        return null;
      }
      this.itib += match.index + match[0].length;
      return match[0];
    }
    let start, end;
    if (typeof until === "string") {
      if (!until) throw new KernelError("Boundary cannot be empty");
      start = text.indexOf(until);
      if (start < 0) throw new KernelError(`Missing boundary: ${JSON.stringify(until)}`);
      end = start + until.length;
    } else if (until instanceof RegExp) {
      const match = new RegExp(until.source, until.flags.replace(/[gy]/g, "")).exec(text);
      if (match === null) throw new KernelError(`Missing boundary: ${until}`);
      start = match.index;
      end = start + match[0].length;
      if (start === end) throw new KernelError("Boundary must consume characters");
    } else {
      throw new KernelError("Boundary must be text or a RegExp");
    }
    const result = text.slice(0, start);
    this.itib += end;
    return result;
  }
}

export class Word {
  constructor(name, action = null, immediate = false, category = "host",
              source = "", help = "", comment = "", properties = {}) {
    Object.assign(this, { name, action, immediate, category, source, help, comment, properties });
  }
  toString() { return `<Word '${this.name}' (${this.category})>`; }
  [INSPECT]() { return this.toString(); }
}

export class Literal {
  constructor(value) {
    this.value = value;
    Object.freeze(this);
  }
  toString() { return `Literal(${String(this.value)})`; }
  [INSPECT]() { return this.toString(); }
}

export class Frame {
  constructor(word, colonCode, ip = 0) {
    this.word = word;
    this.colonCode = colonCode;
    this.ip = ip;
  }
}

export class Task {
  constructor(vm, continuation) {
    this.vm = vm;
    this.continuation = continuation;
    this.inputs = [];
    this.frames = [];
    this.rstack = [];
    this.tstack = [];
    this.status = "ready";
    this.error = null;
  }

  appendInput(text) {
    if (["done", "aborted", "failed"].includes(this.status) || this.inputs.length === 0) {
      throw new KernelError("Task has no live input to append to");
    }
    this.inputs[this.inputs.length - 1].append(text);
    return this;
  }

  resume() {
    if (this.status !== "ready" && this.status !== "paused") {
      throw new KernelError(`Cannot resume a ${this.status} task`);
    }
    this.status = "running";
    this.vm._active.push(this);
    try {
      try {
        const step = this.continuation.next();
        if (step.done) {
          this.status = "done";
        } else if (step.value !== PAUSE) {
          throw new KernelError("Only the pause signal may be yielded");
        } else {
          this.status = "paused";
        }
      } catch (error) {
        if (error instanceof Abort) {
          this.status = "aborted";
          this.vm._discard();
        } else {
          this.status = "failed";
          this.error = error;
          this.vm._discard();
          throw error;
        }
      } finally {
        if (["done", "aborted", "failed"].includes(this.status)) this.continuation.return();
      }
    } finally {
      this.vm._active.pop();
    }
    return this;
  }

  cancel() {
    if (this.status === "running") {
      throw new KernelError("A running task must abort from inside execution");
    }
    if (this.status === "ready" || this.status === "paused") {
      this.vm._active.push(this);
      try {
        this.status = "aborted";
        try {
          this.continuation.return();
        } finally {
          this.vm._discard(this);
        }
      } finally {
        this.vm._active.pop();
      }
    }
    return this;
  }
}

export class VM {
  constructor(host = {}) {
    this.dstack = [];
    this.words = new Map();
    this.host = { ...host };
    this._active = [];
    this._builder = null;
    this.latest = null;
    this.define("code", (m) => { m._hostDefinition(); });
    this.define("end-code", (m) => { m._unmatchedEnd(); });
  }

  get task() {
    if (this._active.length === 0) throw new KernelError("No active task");
    return this._active[this._active.length - 1];
  }
  get input() {
    const inputs = this.task.inputs;
    if (inputs.length === 0) throw new KernelError("No active input");
    return inputs[inputs.length - 1];
  }
  get rstack() { return this.task.rstack; }
  get tstack() { return this.task.tstack; }
  get frame() {
    const frames = this.task.frames;
    return frames.length ? frames[frames.length - 1] : null;
  }
  get compiling() { return this._builder !== null; }

  push(...values) {
    this.dstack.push(...values);
    return this;
  }

  _index(depth) {
    if (!Number.isInteger(depth) || depth < 0 || depth >= this.dstack.length) {
      throw new KernelError("Invalid data stack depth (or empty stack)");
    }
    return this.dstack.length - 1 - depth;
  }
  peek(depth = 0) { return this.dstack[this._index(depth)]; }
  pop(depth = 0) { return this.dstack.splice(this._index(depth), 1)[0]; }

  static _name(name) {
    if (typeof name !== "string" || !name || /\s/.test(name)) {
      throw new KernelError("A name must be nonempty and contain no whitespace");
    }
  }

  tick(name) { return this.words.get(name) ?? null; }

  _resolve(operation) {
    if (typeof operation === "string") {
      const word = this.tick(operation);
      if (word === null) throw new KernelError(`Unknown word: ${operation}`);
      return word;
    }
    return operation;
  }

  _publish(word) {
    this.words.delete(word.name);   // a redefined word moves to the end
    this.words.set(word.name, word);
    this.latest = word;
    return word;
  }

  define(name, action, { immediate = false, category = "host", source = "",
                         help = "", comment = "", properties = {} } = {}) {
    VM._name(name);
    if (typeof action !== "function" && !Array.isArray(action)) {
      throw new KernelError("Behavior must be a function or colon body array");
    }
    return this._publish(new Word(name, action, immediate, category, source,
                                  help, comment, { ...properties }));
  }

  begin(name) {
    if (this.compiling) throw new KernelError("A colon definition is already being built");
    VM._name(name);
    const word = new Word(name, null, false, "colon");
    const owner = this._active.length ? this._active[this._active.length - 1] : null;
    this._builder = { word, owner, previous: this.latest, colonCode: [] };
    this.latest = word;
    return word;
  }

  comma(operation) {
    if (!this.compiling) throw new KernelError("No unfinished colon definition");
    operation = this._resolve(operation);
    if (!(operation instanceof Word) && !(operation instanceof Literal) &&
        typeof operation !== "function") {
      throw new KernelError("Compile an operation; use literal() for data");
    }
    this._builder.colonCode.push(operation);
  }

  literal(value) { this.comma(new Literal(value)); }

  finish() {
    if (!this.compiling) throw new KernelError("No unfinished colon definition");
    const builder = this._builder;
    builder.word.action = Object.freeze([...builder.colonCode]);
    this._builder = null;
    return this._publish(builder.word);
  }

  _discard(owner = ALL) {
    if (this.compiling && (owner === ALL || this._builder.owner === owner)) {
      this.latest = this._builder.previous;
      this._builder = null;
    }
  }

  pause() { return PAUSE; }

  abort() {
    this.task;   // requires an active task
    throw new Abort();
  }

  dictate(tib) { return new Task(this, this.evaluate(tib)).resume(); }
  execute(operation) { return new Task(this, this.call(operation)).resume(); }

  *call(operation) {
    this.task;   // calls inside a continuation require active task context
    operation = this._resolve(operation);
    if (operation instanceof Literal) {
      this.push(operation.value);
      return;
    }
    const action = operation instanceof Word ? operation.action : operation;
    if (Array.isArray(action)) {
      const frame = new Frame(operation, action);
      const frames = this.task.frames;
      frames.push(frame);
      try {
        while (frame.ip < frame.colonCode.length) {
          if (frame.ip < 0) throw new KernelError("Negative execution position");
          const step = frame.colonCode[frame.ip];
          frame.ip += 1;
          yield* this.call(step);
        }
      } finally {
        frames.pop();
      }
    } else if (typeof action === "function") {
      try {
        const result = action(this);
        if (isGenerator(result)) {
          yield* result;
        } else if (result === PAUSE) {
          yield PAUSE;
        }
      } catch (error) {
        if (error instanceof KernelError || error instanceof Abort) throw error;
        const name = operation instanceof Word ? operation.name : (action.name || "<anonymous>");
        throw new KernelError(`${name}: ${error?.message ?? error}`, { cause: error });
      }
    } else {
      throw new KernelError(`Not executable: ${String(operation)}`);
    }
  }

  static number(text) {
    const toInt = (sign, digits) => {
      let value = BigInt(digits);
      if (sign === "-") value = -value;
      return value >= -MAX_SAFE && value <= MAX_SAFE ? Number(value) : value;
    };
    let m = /^([+-]?)(\d+(?:_\d+)*)$/.exec(text);
    if (m) return toInt(m[1], m[2].replaceAll("_", ""));
    m = /^([+-]?)(0[xX][0-9a-fA-F]+(?:_[0-9a-fA-F]+)*|0[oO][0-7]+(?:_[0-7]+)*|0[bB][01]+(?:_[01]+)*)$/.exec(text);
    if (m) return toInt(m[1], m[2].replaceAll("_", ""));
    if (/^[+-]?(?:\d+(?:_\d+)*(?:\.(?:\d+(?:_\d+)*)?)?|\.\d+(?:_\d+)*)(?:[eE][+-]?\d+(?:_\d+)*)?$/.test(text)) {
      return Number(text.replaceAll("_", ""));
    }
    m = /^([+-]?)(inf(?:inity)?|nan)$/i.exec(text);
    if (m) {
      if (m[2].toLowerCase() === "nan") return NaN;
      return m[1] === "-" ? -Infinity : Infinity;
    }
    throw new KernelError(`Unknown input: ${text}`);
  }

  *evaluate(tib) {
    const source = new Input(tib);
    const inputs = this.task.inputs;
    inputs.push(source);
    try {
      let token;
      while ((token = source.read()) !== null) {
        const word = this.tick(token);
        if (word === null) {
          const value = VM.number(token);
          if (this.compiling) this.literal(value);
          else this.push(value);
        } else if (this.compiling && !word.immediate) {
          this.comma(word);
        } else {
          yield* this.call(word);
        }
      }
    } finally {
      inputs.pop();
    }
  }

  /*
   * Find the `end-code` that closes a host body, ignoring occurrences inside
   * strings, template literals, regex literals and comments.  Returns
   * {start, end} offsets into `text`, or null if there is none / the body is
   * lexically malformed.
   */
  static hostBoundary(text) {
    const n = text.length;
    const isIdent = (c) => c !== undefined && /[\p{L}\p{N}_$]/u.test(c);
    const REGEX_AFTER = new Set(["return", "typeof", "instanceof", "in", "of", "new", "delete",
                                 "void", "throw", "case", "do", "else", "yield", "await"]);
    const stack = [];          // "t" = inside template text, "$" = inside ${ }, "{" = nested brace
    let prev = null;           // last significant token: null | "val" | "kw:<word>" | single punctuation
    let i = 0;
    while (i < n) {
      const top = stack[stack.length - 1];
      const c = text[i];
      if (top === "t") {
        if (c === "\\") i += 2;
        else if (c === "`") { stack.pop(); prev = "val"; i += 1; }
        else if (c === "$" && text[i + 1] === "{") { stack.push("$"); prev = "{"; i += 2; }
        else i += 1;
        continue;
      }
      if (/\s/.test(c)) { i += 1; continue; }
      if (c === "/" && text[i + 1] === "/") {
        const nl = text.indexOf("\n", i);
        if (nl < 0) return null;
        i = nl + 1;
        continue;
      }
      if (c === "/" && text[i + 1] === "*") {
        const close = text.indexOf("*/", i + 2);
        if (close < 0) return null;
        i = close + 2;
        continue;
      }
      if (c === "'" || c === '"') {
        i += 1;
        for (;;) {
          if (i >= n || text[i] === "\n") return null;
          if (text[i] === "\\") i += 2;
          else if (text[i] === c) { i += 1; break; }
          else i += 1;
        }
        prev = "val";
        continue;
      }
      if (c === "`") { stack.push("t"); i += 1; continue; }
      if (c === "{") { stack.push("{"); prev = "{"; i += 1; continue; }
      if (c === "}") {
        if (top === "$" || top === "{") stack.pop();
        prev = "}";
        i += 1;
        continue;
      }
      if (c === "/") {
        // A "/" starts a regex after an operator, "(", "{", "}", "," ... or a keyword
        // such as `return`; after a value (identifier, number, string, ")", "]") it divides.
        const regexAllowed = prev === null || prev === "}" || prev.length === 1 ||
          (prev.startsWith("kw:") && REGEX_AFTER.has(prev.slice(3)));
        if (regexAllowed) {
          i += 1;
          let inClass = false;
          for (;;) {
            if (i >= n || text[i] === "\n") return null;
            const d = text[i];
            if (d === "\\") i += 2;
            else if (d === "[") { inClass = true; i += 1; }
            else if (d === "]") { inClass = false; i += 1; }
            else if (d === "/" && !inClass) { i += 1; break; }
            else i += 1;
          }
          while (isIdent(text[i])) i += 1;   // flags
          prev = "val";
        } else {
          prev = "/";
          i += 1;
        }
        continue;
      }
      if (/\d/.test(c)) {
        while (i < n && /[\w.]/.test(text[i])) i += 1;
        prev = "val";
        continue;
      }
      if (isIdent(c)) {
        const start = i;
        while (isIdent(text[i])) i += 1;
        const word = text.slice(start, i);
        if (word === "end" && text.startsWith("-code", i)) {
          const end = i + 5;
          const before = text[start - 1];
          const after = text[end];
          const joined = (x) => x !== undefined && (/[\p{L}\p{N}_]/u.test(x) || x === "-");
          if (!(start > 0 && joined(before)) && !(end < n && joined(after))) {
            return { start, end };
          }
        }
        prev = REGEX_AFTER.has(word) ? `kw:${word}` : "val";
        continue;
      }
      prev = c === ")" || c === "]" ? "val" : c;
      i += 1;
    }
    return null;
  }

  _hostDefinition() {
    if (this.compiling) throw new KernelError("Cannot build host code inside a colon definition");
    const name = this.input.read();
    VM._name(name);
    const boundary = VM.hostBoundary(this.input.remaining);
    if (boundary === null) throw new KernelError("Missing end-code (or malformed host body)");
    const { start, end } = boundary;
    const body = this.input.remaining.slice(0, start);
    this.input.consume(end);
    const names = Object.keys(this.host).filter(
      (k) => /^[A-Za-z_$][\w$]*$/.test(k) && k !== "vm" && !RESERVED.has(k));
    if (!names.includes("KernelError")) names.push("KernelError");
    const values = names.map((k) => (k in this.host ? this.host[k] : KernelError));
    let operation;
    try {
      const compiled = new GeneratorFunction("vm", ...names, `"use strict";\n${body}`);
      operation = (vm) => compiled(vm, ...values);
    } catch (error) {
      throw new KernelError(`Cannot define ${name}: ${error.message}`, { cause: error });
    }
    this.define(name, operation, { category: "code", source: body });
  }

  _unmatchedEnd() {
    throw new KernelError("end-code has no matching code");
  }
}
