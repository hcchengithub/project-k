/*
 * Project K demonstration vocabulary, optional Forth console and helpers.
 *
 *   node demo.js          open the k> console (bye exits)
 *   node --test           run the test suite (demo.test.js)
 *
 * projectk.js contains only the kernel.  Everything here is built on its public API.
 */
import readline from "node:readline";
import { pathToFileURL } from "node:url";
import { VM } from "./projectk.js";

export const EXPLORER = String.raw`
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
code pick
    vm.push(vm.peek(vm.pop()))
end-code
code roll
    vm.push(vm.pop(vm.pop()))
end-code
: dup 0 pick ;
: over 1 pick ;
: swap 1 roll ;
code drop
    vm.pop()
end-code
code +
    const right = vm.pop(), left = vm.pop()
    vm.push(left + right)
end-code
code *
    const right = vm.pop(), left = vm.pop()
    vm.push(left * right)
end-code
code .
    console.log(String(vm.pop()))
end-code
code pause
    yield vm.pause()
end-code
code .s
    const show = (v) => typeof v === 'string' ? JSON.stringify(v) : String(v)
    console.log('[' + vm.dstack.map(show).join(', ') + ']')
end-code
code words
    console.log([...vm.words.keys()].join(' '))
end-code
code see
    const name = vm.input.read()
    const word = vm.tick(name)
    if (word === null) throw new KernelError('Unknown word: ' + name)
    console.log(String(word))
    console.log(word.source || '(' + word.action.map(String).join(', ') + ')')
end-code
code resume
    const tasks = (vm.host.pausedTasks ??= [])
    if (tasks.length === 0) throw new KernelError('No paused task')
    const task = tasks.pop()
    try {
        task.resume()
    } finally {
        if (task.status === 'paused') tasks.push(task)
    }
end-code
code abort
    vm.abort()
end-code
code (bye)
    vm.host.exitRequested = true
end-code
: bye (bye) abort ;
code s"
    let text = vm.input.read('"')
    if (text.startsWith(' ')) text = text.slice(1)
    if (vm.compiling) vm.literal(text)
    else vm.push(text)
end-code
immediate
: help s" Type numbers and words, then press Enter. Stack top is on the right.
  3 4 + .                 print 7
  10 20 over .s           show [10, 20, 10]
  : square dup * ;        define a colon word
  12 square .             print 144
  .s                      show the data stack without changing it
  words                   list available words
  see NAME                show a word's source or colon definition
  1 pause 2               pause before pushing 2
  resume                  continue the most recently paused task
  bye                     exit
Host definitions can be entered on one line:
  code answer vm.push(42) end-code
Basic words are already loaded. All commands are vocabulary words." . ;
`;

/** Print before; evaluate "1 pause 2"; then print after, all in one Task. */
export function* activity(vm) {
  console.log("before");
  yield* vm.evaluate("1 pause 2");
  console.log("after");
}

/** Construct a VM with the optional demonstration vocabulary. */
export function makeVM() {
  const vm = new VM();
  vm.dictate(EXPLORER);
  return vm;
}

/**
 * The optional k> console.  `lines` is any (async) iterable of input lines; by
 * default it reads standard input.  Paused tasks are kept for `resume`.
 */
export async function repl(vm = makeVM(), lines = null) {
  delete vm.host.exitRequested;
  const pausedTasks = (vm.host.pausedTasks ??= []);
  let rl = null;
  if (lines === null) {
    rl = readline.createInterface({ input: process.stdin, output: process.stdout, prompt: "k> " });
    lines = rl;
  }
  console.log("Forth test vocabulary loaded; enter source at k>.");
  console.log("Enter help for instructions; bye exits.");
  rl?.prompt();
  try {
    for await (const line of lines) {
      try {
        if (line.trim()) {
          const task = vm.dictate(line);
          if (vm.host.exitRequested) break;
          if (task.status === "paused") {
            pausedTasks.push(task);
            console.log("Paused; enter resume to continue.");
          }
        }
      } catch (error) {
        console.log(`${error.name}: ${error.message}`);
      }
      rl?.prompt();
    }
  } finally {
    rl?.close();
    for (const task of pausedTasks) task.cancel();
  }
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  await repl();
}
