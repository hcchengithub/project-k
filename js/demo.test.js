// Port of the Python test suite (py/demo.py). Run with:  node --test
import test from "node:test";
import assert from "node:assert/strict";
import { Input, KernelError, Task, VM } from "./projectk.js";
import { EXPLORER, activity, makeVM, repl } from "./demo.js";

/** Run fn while capturing console.log output; returns the text. */
async function capture(fn) {
  const original = console.log;
  let text = "";
  console.log = (...args) => { text += args.join(" ") + "\n"; };
  try { await fn(); } finally { console.log = original; }
  return text;
}
const captureSync = (fn) => {
  const original = console.log;
  let text = "";
  console.log = (...args) => { text += args.join(" ") + "\n"; };
  try { fn(); } finally { console.log = original; }
  return text;
};
const explorer = () => makeVM();

test("canonical names and shared colon code", () => {
  const vm = makeVM();
  vm.dictate(": work 1 pause 2 ;");
  const task = vm.execute("work");
  const word = vm.tick("work");
  const frame = task.frames.at(-1);
  assert.equal(frame.word, word);
  assert.equal(frame.colonCode, word.action);
  assert.equal(frame.ip, 2);
  assert.deepEqual(vm.dstack, [1]);
  assert.deepEqual(task.rstack, []);
  assert.deepEqual(task.tstack, []);
  for (const name of ["stack", "returnStack", "temporaryStack", "lookup", "record", "start"]) {
    assert.ok(!(name in vm), name);
  }
  for (const name of ["operations", "position"]) assert.ok(!(name in frame), name);
  task.resume();
  assert.deepEqual(vm.dstack, [1, 2]);
});

test("generator creation is lazy and needs an active task", () => {
  const vm = makeVM();
  const generator = vm.evaluate("3 4 +");
  assert.deepEqual(vm.dstack, []);
  assert.throws(() => generator.next(), { name: "KernelError", message: /No active task/ });
  assert.equal(generator.next().done, true);   // the failed generator is closed
  const task = vm.dictate("3 4 +");
  assert.equal(task.status, "done");
  assert.deepEqual(vm.dstack, [7]);
});

test("activity continuation prints after only on resume", () => {
  const vm = makeVM();
  vm.define("activity", activity);
  let task;
  let output = captureSync(() => { task = vm.execute("activity"); });
  assert.equal(output, "before\n");
  assert.equal(task.status, "paused");
  assert.deepEqual(vm.dstack, [1]);
  assert.equal(task.inputs.length, 1);
  output += captureSync(() => task.resume());
  assert.equal(output, "before\nafter\n");
  assert.equal(task.status, "done");
  assert.deepEqual(vm.dstack, [1, 2]);
  assert.deepEqual(task.inputs, []);
});

test("task handle reassignment does not cancel old work", () => {
  const vm = makeVM();
  let task = vm.dictate("1 pause 2");
  const retained = task;
  task = vm.dictate("3 pause 4");
  assert.notEqual(task, retained);
  assert.equal(retained.status, "paused");
  assert.equal(task.status, "paused");
  retained.resume();
  task.cancel();
  assert.deepEqual(vm.dstack, [1, 3, 2]);
  assert.equal(task.status, "aborted");
});

test("repl has no command dispatch or automatic stack output", async () => {
  const text = await capture(() => repl(makeVM(), ["3 4 +", ".s", "see dup", "help", "bye"]));
  assert.equal(text.split("[7]").length - 1, 1);
  assert.ok(text.includes("<Word 'dup' (colon)>"));
  assert.ok(text.includes("All commands are vocabulary words."));
});

test("display and help are vocabulary words", () => {
  const vm = explorer();
  vm.push(10, 20);
  const output = captureSync(() => vm.dictate(".s see dup help 30"));
  assert.deepEqual(vm.dstack, [10, 20, 30]);
  assert.ok(output.includes("[10, 20]"));
  assert.ok(output.includes("<Word 'dup' (colon)>"));
  assert.ok(output.includes("All commands are vocabulary words."));
  assert.equal(vm.tick("help").category, "colon");
  assert.equal(vm.tick("see").category, "code");
  assert.equal(vm.tick(":help"), null);
  assert.equal(vm.tick(":see"), null);
  assert.equal(vm.tick("stack"), null);
});

test("resume is a word and can pause again", () => {
  const vm = explorer();
  const tasks = (vm.host.pausedTasks ??= []);
  const task = vm.dictate("1 pause 2 pause 3");
  tasks.push(task);
  vm.dictate("resume 4");
  assert.deepEqual(vm.dstack, [1, 2, 4]);
  assert.deepEqual(tasks, [task]);
  vm.dictate("resume 5");
  assert.deepEqual(vm.dstack, [1, 2, 4, 3, 5]);
  assert.deepEqual(tasks, []);
  for (const name of [".s", "words", "resume", "see"]) assert.equal(vm.tick(name).category, "code");
  assert.throws(() => vm.dictate("resume"), { message: /No paused task/ });
});

test("colon stack words and bye", () => {
  const vm = explorer();
  for (const name of ["dup", "over", "swap", "bye"]) assert.equal(vm.tick(name).category, "colon");
  vm.dictate("10 20 over");
  assert.deepEqual(vm.dstack, [10, 20, 10]);
  vm.dictate("swap dup");
  assert.deepEqual(vm.dstack, [10, 10, 20, 20]);
  const task = vm.dictate("bye 99");
  assert.equal(task.status, "aborted");
  assert.equal(vm.host.exitRequested, true);
  assert.deepEqual(vm.dstack, [10, 10, 20, 20]);
});

test("seed growth and capture", () => {
  const vm = new VM();
  assert.deepEqual(new Set(vm.words.keys()), new Set(["code", "end-code"]));
  assert.deepEqual(new VM().dstack, []);
  vm.dictate(EXPLORER);
  vm.dictate(": square dup * ; : old 6 square ;");
  vm.dictate("code square vm.push(99) end-code old square");
  assert.deepEqual(vm.dstack, [36, 99]);
});

test("host objects, numeric precedence and precision", () => {
  const resource = {};
  const vm = new VM({ resource });
  vm.dictate("code resource vm.push(resource) end-code resource");
  assert.equal(vm.pop(), resource);
  vm.dictate("9007199254740993 -0x10 0o10 0b11 2.5 1_000 1e3");
  assert.deepEqual(vm.dstack, [9007199254740993n, -16, 8, 3, 2.5, 1000, 1000]);
  vm.define("123", (m) => m.push("word"));
  vm.dictate("123");
  assert.equal(vm.pop(), "word");
  assert.throws(() => vm.dictate("12abc"), { message: /Unknown input: 12abc/ });
});

test("input contract", () => {
  const named = new Input("12 34", 3);
  assert.equal(named.tib, "12 34");
  assert.equal(named.itib, 3);
  assert.equal(named.read(), "34");
  assert.equal(named.itib, 5);
  assert.throws(() => { named.itib = 6; }, KernelError);
  const source = new Input(" one two|tail");
  assert.equal(source.read(), "one");
  assert.equal(source.itib, 4);
  const original = source.tib;
  source.append(" more");
  assert.equal(source.itib, 4);
  assert.ok(source.tib.startsWith(original));
  assert.equal(source.read("|"), " two");
  const position = source.itib;
  for (const boundary of ["missing", "", /(?:)/]) {
    assert.throws(() => source.read(boundary), KernelError);
    assert.equal(source.itib, position);
  }
  assert.equal(source.rest(), "tail more");
  assert.equal(source.read(), null);
  assert.equal(source.consume(100), "");
  assert.throws(() => source.consume(-1), KernelError);
});

test("pause inside colon, append input, terminal task", () => {
  const vm = explorer();
  vm.dictate(": sequence 1 pause 2 ;");
  const task = vm.dictate("sequence");
  assert.equal(task.status, "paused");
  assert.deepEqual(vm.dstack, [1]);
  task.appendInput(" 3");
  task.resume();
  assert.deepEqual(vm.dstack, [1, 2, 3]);
  assert.equal(task.status, "done");
  assert.deepEqual([task.inputs, task.frames], [[], []]);
  assert.throws(() => task.appendInput(" 4"), KernelError);
  assert.throws(() => task.resume(), KernelError);
});

test("task private stacks and separate re-entry", () => {
  const vm = explorer();
  vm.define("save", (m) => { m.rstack.push(m.pop()); m.tstack.push("private"); });
  const first = vm.dictate("11 save pause");
  const second = vm.dictate("22 save pause");
  assert.deepEqual(first.rstack, [11]);
  assert.deepEqual(second.rstack, [22]);
  assert.notEqual(first.tstack, second.tstack);
  first.resume();
  second.cancel();
  const seen = [];
  vm.define("reentry", (m) => {
    const outer = m.task;
    const child = m.dictate("33");
    seen.push(child !== outer, m.task === outer);
  });
  vm.dictate("reentry");
  assert.deepEqual(seen, [true, true]);
  assert.deepEqual(vm.dstack, [33]);
});

test("nested continuation restores input", () => {
  const vm = explorer();
  const seen = [];
  vm.define("nested", function* (m) {
    const outer = m.input;
    yield* m.evaluate("10 pause 20");
    seen.push(m.input === outer);
    yield* m.call("dup");
  });
  const task = vm.dictate("nested 30");
  assert.equal(task.inputs.length, 2);
  task.appendInput(" 25");
  task.resume();
  assert.deepEqual(vm.dstack, [10, 20, 25, 25, 30]);
  assert.deepEqual(seen, [true]);
});

test("cross-input definition and immediate words", () => {
  const vm = explorer();
  vm.dictate(": result 40");
  assert.ok(vm.compiling);
  assert.equal(vm.tick("result"), null);
  assert.equal(vm.latest.name, "result");
  vm.dictate("2 + ; result");
  assert.deepEqual(vm.dstack, [42]);
  vm.dictate(': message s" hello" ; message');
  assert.equal(vm.pop(), "hello");
});

test("partial failure, abort and cancellation", () => {
  const vm = explorer();
  vm.dictate(": stable 7 ;");
  const old = vm.tick("stable");
  const task = new Task(vm, vm.evaluate("5 : stable 9 unknown"));
  assert.throws(() => task.resume(), KernelError);
  assert.equal(task.status, "failed");
  assert.ok(task.error instanceof KernelError);
  assert.equal(vm.tick("stable"), old);
  assert.equal(vm.latest, old);
  assert.deepEqual(vm.dstack, [5]);
  vm.dictate("code stop vm.abort() end-code");
  assert.equal(vm.dictate("6 stop 8").status, "aborted");
  assert.deepEqual(vm.dstack, [5, 6]);
  vm.define("building", function* (m) {
    m.begin("unfinished");
    yield m.pause();
  });
  const suspended = vm.dictate("building");
  suspended.cancel();
  assert.ok(!vm.compiling);
  assert.equal(vm.tick("unfinished"), null);
  assert.deepEqual(suspended.inputs, []);
});

test("host lexical boundaries and multiline strings", () => {
  const vm = new VM();
  vm.dictate([
    "code text",
    "    // end-code is a comment",
    '    vm.push("end-code")',
    "    vm.push(`first",
    "  end-code",
    "last`)",
    "    vm.push(/end-code/.test('x') ? 1 : 2)",
    "end-code text",
  ].join("\n"));
  assert.deepEqual(vm.dstack, ["end-code", "first\n  end-code\nlast", 2]);
  vm.dictate("code empty end-code empty");
  const old = vm.tick("text");
  assert.throws(() => vm.dictate("code text this is invalid javascript ! end-code"), KernelError);
  assert.equal(vm.tick("text"), old);
  assert.throws(() => vm.dictate("code unfinished vm.push('end-code)"), KernelError);
});

test("depth errors and host failure cause", () => {
  const vm = new VM();
  vm.push(1, 2, 3);
  assert.equal(vm.peek(1), 2);
  assert.equal(vm.pop(1), 2);
  assert.deepEqual(vm.dstack, [1, 3]);
  for (const depth of [-1, 2, "0"]) assert.throws(() => vm.pop(depth), KernelError);
  vm.define("broken", () => { throw new RangeError("boom"); });
  assert.throws(() => vm.execute("broken"), (error) => {
    assert.ok(error instanceof KernelError);
    assert.match(error.message, /broken/);
    assert.ok(error.cause instanceof RangeError);
    return true;
  });
});

test("invalid yield unwinds", () => {
  const vm = new VM();
  vm.define("bad", function* () { yield "invalid signal"; });
  const task = new Task(vm, vm.evaluate("bad"));
  assert.throws(() => task.resume(), KernelError);
  assert.equal(task.status, "failed");
  assert.deepEqual(task.inputs, []);
  assert.deepEqual(vm._active, []);
});

test("extension can change execution position", () => {
  const vm = new VM();
  vm.define("skip", (m) => { m.frame.ip += 1; });
  vm.begin("jump");
  vm.comma("skip");
  vm.literal("skipped");
  vm.literal("kept");
  vm.finish();
  vm.execute("jump");
  assert.deepEqual(vm.dstack, ["kept"]);
});
