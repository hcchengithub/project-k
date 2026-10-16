import { Input, KernelError, Task, VM } from "./projectk.js";

function fail(message) {
  throw new Error(message);
}

export function assert(condition, message = "assertion failed") {
  if (!condition) fail(message);
}

export function equal(actual, expected, message = "") {
  if (!Object.is(actual, expected)) {
    fail(message || `expected ${String(expected)}, got ${String(actual)}`);
  }
}

export function deepEqual(actual, expected, message = "") {
  const normalize = (value) => {
    if (typeof value === "bigint") return { __bigint__: value.toString() };
    if (Array.isArray(value)) return value.map(normalize);
    if (value && typeof value === "object") {
      const out = {};
      for (const key of Object.keys(value)) out[key] = normalize(value[key]);
      return out;
    }
    return value;
  };
  const a = JSON.stringify(normalize(actual));
  const b = JSON.stringify(normalize(expected));
  if (a !== b) fail(message || `expected ${b}, got ${a}`);
}

export function throws(fn, matcher = null) {
  try {
    fn();
  } catch (error) {
    if (matcher instanceof RegExp && !matcher.test(error.message)) {
      fail(`error message did not match ${matcher}: ${error.message}`);
    }
    if (typeof matcher === "function" && !(error instanceof matcher)) {
      fail(`expected ${matcher.name}, got ${error.constructor?.name}`);
    }
    return error;
  }
  fail("expected function to throw");
}

export function grow(vm = new VM()) {
  vm.dictate(String.raw`
code :
  vm.begin(vm.input.read())
end-code

code immediate
  vm.latest.immediate = true
end-code
immediate

code ;
  vm.finish()
end-code
immediate

code dup
  vm.push(vm.peek())
end-code

code *
  const b = vm.pop(), a = vm.pop()
  vm.push(a * b)
end-code

code +
  const b = vm.pop(), a = vm.pop()
  vm.push(a + b)
end-code

code pause
  yield vm.pause()
end-code
`);
  return vm;
}

export const tests = [
  {
    name: "minimal boot exposes only code and end-code",
    run() {
      const vm = new VM();
      deepEqual([...vm.words.keys()], ["code", "end-code"]);
      deepEqual(vm.dstack, []);
    },
  },
  {
    name: "the seed can grow colon syntax and a new word",
    run() {
      const vm = grow();
      vm.dictate(": square dup * ; 12 square");
      equal(vm.pop(), 144);
      equal(vm.tick("square").category, "colon");
    },
  },
  {
    name: "captured binding survives later redefinition",
    run() {
      const vm = grow();
      vm.dictate(": square dup * ; : old 6 square ;");
      const original = vm.tick("square");
      vm.dictate("code square vm.push(99) end-code");
      assert(vm.tick("square") !== original);
      vm.dictate("old square");
      deepEqual(vm.dstack, [36, 99]);
    },
  },
  {
    name: "host objects pass through the data stack unchanged",
    run() {
      const resource = { kind: "host-resource" };
      const vm = new VM({ resource });
      vm.dictate("code resource vm.push(resource) end-code resource");
      equal(vm.pop(), resource);
    },
  },
  {
    name: "Input preserves source while moving itib",
    run() {
      const input = new Input(" one two|tail");
      equal(input.read(), "one");
      equal(input.itib, 4);
      equal(input.read("|"), " two");
      equal(input.rest(), "tail");
      equal(input.read(), null);
    },
  },
  {
    name: "pause returns control and resume continues the same task",
    run() {
      const vm = grow();
      vm.dictate(": journey 1 pause 2 ;");
      const task = vm.dictate("journey 3");
      equal(task.status, "paused");
      deepEqual(vm.dstack, [1]);
      task.resume();
      equal(task.status, "done");
      deepEqual(vm.dstack, [1, 2, 3]);
    },
  },
  {
    name: "input can be appended while a task is paused",
    run() {
      const vm = grow();
      const task = vm.dictate("1 pause 2");
      task.appendInput(" 3");
      task.resume();
      deepEqual(vm.dstack, [1, 2, 3]);
      equal(task.status, "done");
      throws(() => task.appendInput(" 4"), KernelError);
    },
  },
  {
    name: "separate tasks have private rstack and tstack",
    run() {
      const vm = grow();
      vm.define("save", m => {
        m.rstack.push(m.pop());
        m.tstack.push("private");
      });
      const first = vm.dictate("11 save pause");
      const second = vm.dictate("22 save pause");
      deepEqual(first.rstack, [11]);
      deepEqual(second.rstack, [22]);
      assert(first.rstack !== second.rstack);
      assert(first.tstack !== second.tstack);
      first.cancel();
      second.cancel();
    },
  },
  {
    name: "nested evaluate restores the outer input context",
    run() {
      const vm = grow();
      const seen = [];
      vm.define("nested", function* (m) {
        const outer = m.input;
        yield* m.evaluate("10 pause 20");
        seen.push(m.input === outer);
      });
      const task = vm.dictate("nested 30");
      equal(task.status, "paused");
      task.resume();
      deepEqual(seen, [true]);
      deepEqual(vm.dstack, [10, 20, 30]);
    },
  },
  {
    name: "a colon definition may continue across submissions",
    run() {
      const vm = grow();
      vm.dictate(": answer 40");
      assert(vm.compiling);
      equal(vm.tick("answer"), null);
      equal(vm.latest.name, "answer");
      vm.dictate("2 + ; answer");
      equal(vm.pop(), 42);
    },
  },
  {
    name: "failure preserves completed effects and old bindings",
    run() {
      const vm = grow();
      vm.dictate(": stable 7 ;");
      const old = vm.tick("stable");
      const task = new Task(vm, vm.evaluate("5 : stable 9 unknown"));
      throws(() => task.resume(), KernelError);
      equal(task.status, "failed");
      equal(vm.tick("stable"), old);
      equal(vm.latest, old);
      deepEqual(vm.dstack, [5]);
    },
  },
  {
    name: "end-code inside JavaScript data does not terminate a host body",
    run() {
      const vm = new VM();
      vm.dictate([
        "code text",
        '  vm.push("end-code")',
        "  vm.push(/end-code/.test('x') ? 1 : 2)",
        "end-code",
        "text",
      ].join("\n"));
      deepEqual(vm.dstack, ["end-code", 2]);
    },
  },
  {
    name: "latest points to the newest definition and provisional colon word",
    run() {
      const vm = grow();
      vm.define("first", () => {});
      equal(vm.latest.name, "first");
      vm.begin("building");
      equal(vm.latest.name, "building");
      vm._discard();
      equal(vm.latest.name, "first");
    },
  },
];

export async function runAll(report = () => {}) {
  let passed = 0;
  const results = [];
  for (const item of tests) {
    try {
      await item.run();
      passed += 1;
      const result = { name: item.name, ok: true };
      results.push(result);
      report(result);
    } catch (error) {
      const result = { name: item.name, ok: false, error };
      results.push(result);
      report(result);
    }
  }
  return { passed, total: tests.length, results };
}
