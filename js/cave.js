/*
 * CAVE -- every part of this game is a Project K word (JavaScript edition).
 *
 * The only JavaScript outside the kernel is the launcher at the bottom, which
 * does one job: feed typed lines to a task that is paused waiting for input.
 * That is the V2 idea in miniature -- the game loop `pause`s, the host supplies
 * the input later, and the same task resumes where it stopped.
 *
 * Run:  node cave.js
 */
import readline from "node:readline";
import { pathToFileURL } from "node:url";
import { VM } from "./projectk.js";

export const FORTH = String.raw`
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
code \
    vm.input.read('\n')
end-code
immediate
\ comments work from here on: the backslash is itself a code word
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
code .
    out(String(vm.pop()) + '\n')
end-code
code words
    out([...vm.words.keys()].join(' ') + '\n')
end-code
code see
    const name = vm.input.read()
    const word = vm.tick(name)
    if (word === null) throw new KernelError('Unknown word: ' + name)
    out(String(word) + '\n' + (word.source || '(' + word.action.map(String).join(', ') + ')') + '\n')
end-code

\ ---------- game state and screen ----------
code new-game
    const rows = [
        "####################",
        "#@   #     $#      #",
        "# ## # ### ## #### #",
        "# #    #      #    #",
        "# # ##### #####  # #",
        "#   #   $     #  # #",
        "### # ####### # ## #",
        "#   #       # #    #",
        "# ####### # # #### #",
        "#         #   #  $ #",
        "####################",
    ]
    const grid = rows.map((r) => [...r])
    let x = 0, y = 0
    grid.forEach((row, j) => {
        if (row.includes('@')) { x = row.indexOf('@'); y = j; row[x] = ' ' }
    })
    vm.game = { grid, x, y, gold: 0, moves: 60, over: false,
                total: grid.flat().filter((c) => c === '$').length }
end-code

code render
    const g = vm.game
    const shown = g.grid.map((r) => [...r])
    shown[g.y][g.x] = '@'
    out('\n' + shown.map((r) => r.join('')).join('\n') + '\n')
    out('gold ' + g.gold + '/' + g.total + '   moves left ' + g.moves + '\n')
end-code

\ ---------- movement: one host word, four colon words ----------
code step
    const dy = vm.pop(), dx = vm.pop()
    const g = vm.game
    const nx = g.x + dx, ny = g.y + dy
    if (g.over) {
        // the game has ended: ignore further moves
    } else if (g.grid[ny][nx] === '#') {
        out('  *bump*\n')
    } else {
        g.x = nx; g.y = ny
        g.moves -= 1
        if (g.grid[ny][nx] === '$') {
            g.grid[ny][nx] = ' '
            g.gold += 1
            out('  *clink* you found gold!\n')
        }
        if (g.gold === g.total) {
            g.over = true
            out('  *** You got all the gold. You win! ***\n')
        } else if (g.moves <= 0) {
            g.over = true
            out('  *** Out of moves. The torch dies. You lose. ***\n')
        }
    }
end-code
: n  0 -1 step ;
: s  0  1 step ;
: e  1  0 step ;
: w -1  0 step ;
: dash e e e ;

code where
    vm.push(vm.game.x)
    vm.push(vm.game.y)
end-code
code bye
    vm.game.over = true
end-code
code help
    out('Commands are Forth words:  n s e w   (move)      where  (push x y)  then  . .\n' +
        'You can define new ones:       : dash e e e ;     : zig e s ;\n' +
        'Then use them:                 dash zig zig\n' +
        'Other words: words  see dash  help  bye          Find all the $ before the torch dies.\n')
end-code

\ ---------- main loop: pause for a line, evaluate it, repeat ----------
code play
    while (!vm.game.over) {
        out('k> ')
        yield vm.pause()                 // wait here until the host calls task.resume()
        const line = vm.host.line
        if (line === null) break         // end of input
        if (line.trim()) {
            try {
                yield* vm.evaluate(line)
            } catch (error) {
                if (!(error instanceof KernelError)) throw error
                vm._discard()            // drop a half-typed ': ...' definition
                out('  KernelError: ' + error.message + '\n')
            }
            yield* vm.evaluate('render')
        } else {
            out('\n')
        }
    }
    out('Thanks for playing.\n')
end-code

: cave  new-game help render play ;
`;

/** Start the game. `out` receives text; returns the task so the caller can feed it lines. */
export function startCave(out) {
  const vm = new VM({ out });
  vm.host.line = null;
  vm.dictate(FORTH);
  const task = vm.dictate("cave");     // runs until `play` first pauses for input
  return { vm, task };
}

/** Give a paused game one line of input (null = end of input). */
export function feed({ vm, task }, line) {
  vm.host.line = line;
  task.resume();
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  const game = startCave((text) => process.stdout.write(text));
  const rl = readline.createInterface({ input: process.stdin });
  for await (const line of rl) {
    feed(game, line);
    if (game.task.status !== "paused") break;
  }
  if (game.task.status === "paused") feed(game, null);   // stdin ended early
  rl.close();
}
