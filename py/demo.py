"""Project K Python lab, demonstration vocabulary, and contract tests.

python -m demo: run tests, then open a Python shell with vm ready.
python -i demo.py: run the same setup, using Python's own interactive mode.
python -m unittest demo: run tests only, without opening a shell.
"""
import code
import contextlib
import sys
import io
import inspect
import re
import unittest
from unittest.mock import patch

from projectk import Input, KernelError, VM, Task


EXPLORER = '''
code :
    vm.begin(vm.input.read())
end-code
code immediate
    vm.latest.immediate = True
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
    right, left = vm.pop(), vm.pop()
    vm.push(left + right)
end-code
code *
    right, left = vm.pop(), vm.pop()
    vm.push(left * right)
end-code
code .
    print(vm.pop())
end-code
code pause
    yield vm.pause()
end-code
code .s
    print(vm.dstack)
end-code
code words
    print(' '.join(vm.words))
end-code
code see
    name = vm.input.read()
    word = vm.tick(name)
    if word is None:
        raise KernelError(f'Unknown word: {name}')
    print(word)
    print(word.source or word.action)
end-code
code resume
    tasks = vm.host.setdefault('paused_tasks', [])
    if not tasks:
        raise KernelError('No paused task')
    task = tasks.pop()
    try:
        task.resume()
    finally:
        if task.status == 'paused':
            tasks.append(task)
end-code
code abort
    vm.abort()
end-code
code (bye)
    vm.host['exit_requested'] = True
end-code
: bye (bye) abort ;
code s"
    text = vm.input.read(until='"')
    if text.startswith(' '):
        text = text[1:]
    if vm.compiling:
        vm.literal(text)
    else:
        vm.push(text)
end-code
immediate
: help s" Type numbers and words, then press Enter. Stack top is on the right.
  3 4 + .                 print 7
  10 20 over .s           show [10, 20, 10]
  : square dup * ;        define a colon word
  12 square .             print 144
  .s                      show the data stack without changing it
  words                   list available words
  see NAME               show a word's source or colon definition
  1 pause 2               pause before pushing 2
  resume                  continue the most recently paused task
  bye                     exit
Host definitions can be entered on one line:
  code answer vm.push(42) end-code
Basic words are already loaded. All commands are vocabulary words." . ;

'''


class ConceptualContract(unittest.TestCase):
    def test_canonical_names_and_shared_colon_code(self):
        vm = make_vm()
        vm.dictate(': work 1 pause 2 ;')
        task = vm.execute('work')
        word = vm.tick('work')
        frame = task.frames[-1]
        self.assertIs(frame.word, word)
        self.assertIs(frame.colon_code, word.action)
        self.assertEqual(frame.ip, 2)
        self.assertEqual(vm.dstack, [1])
        self.assertEqual(task.rstack, [])
        self.assertEqual(task.tstack, [])
        for name in ('stack', 'return_stack', 'temporary_stack', 'lookup', 'record', 'start'):
            self.assertFalse(hasattr(vm, name), name)
        for name in ('operations', 'position'):
            self.assertFalse(hasattr(frame, name), name)
        task.resume()
        self.assertEqual(vm.dstack, [1, 2])

    def test_generator_creation_is_lazy_and_needs_active_task(self):
        vm = make_vm()
        generator = vm.evaluate('3 4 +')
        self.assertEqual(inspect.getgeneratorstate(generator), 'GEN_CREATED')
        self.assertEqual(vm.dstack, [])
        with self.assertRaisesRegex(KernelError, 'No active task'):
            next(generator)
        self.assertEqual(inspect.getgeneratorstate(generator), 'GEN_CLOSED')
        task = vm.dictate('3 4 +')
        self.assertEqual(task.status, 'done')
        self.assertEqual(vm.dstack, [7])

    def test_activity_continuation_prints_after_only_on_resume(self):
        vm = make_vm()
        vm.define('activity', activity)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            task = vm.execute('activity')
        self.assertEqual(output.getvalue(), 'before\n')
        self.assertEqual(task.status, 'paused')
        self.assertEqual(vm.dstack, [1])
        self.assertEqual(len(task.inputs), 1)
        with contextlib.redirect_stdout(output):
            task.resume()
        self.assertEqual(output.getvalue(), 'before\nafter\n')
        self.assertEqual(task.status, 'done')
        self.assertEqual(vm.dstack, [1, 2])
        self.assertEqual(task.inputs, [])

    def test_task_handle_reassignment_does_not_cancel_old_work(self):
        vm = make_vm()
        task = vm.dictate('1 pause 2')
        retained = task
        task = vm.dictate('3 pause 4')
        self.assertIsNot(task, retained)
        self.assertEqual(retained.status, 'paused')
        self.assertEqual(task.status, 'paused')
        retained.resume()
        task.cancel()
        self.assertEqual(vm.dstack, [1, 3, 2])
        self.assertEqual(task.status, 'aborted')

    def test_repl_has_no_command_dispatch_or_automatic_stack_output(self):
        output = io.StringIO()
        lines = ['3 4 +', '.s', 'see dup', 'help', 'bye']
        with patch('builtins.input', side_effect=lines), contextlib.redirect_stdout(output):
            repl()
        text = output.getvalue()
        self.assertEqual(text.count('[7]'), 1)
        self.assertIn("<Word 'dup' (colon)>", text)
        self.assertIn('All commands are vocabulary words.', text)

    def test_display_and_help_are_vocabulary_words(self):
        vm = self.explorer()
        vm.push(10, 20)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            vm.dictate('.s see dup help 30')
        self.assertEqual(vm.dstack, [10, 20, 30])
        self.assertIn('[10, 20]', output.getvalue())
        self.assertIn("<Word 'dup' (colon)>", output.getvalue())
        self.assertIn('All commands are vocabulary words.', output.getvalue())
        self.assertEqual(vm.tick('help').category, 'colon')
        self.assertEqual(vm.tick('see').category, 'code')
        self.assertIsNone(vm.tick(':help'))
        self.assertIsNone(vm.tick(':see'))
        self.assertIsNone(vm.tick('stack'))

    def test_resume_is_a_word_and_can_pause_again(self):
        vm = self.explorer()
        tasks = vm.host.setdefault('paused_tasks', [])
        task = vm.dictate('1 pause 2 pause 3')
        tasks.append(task)
        vm.dictate('resume 4')
        self.assertEqual(vm.dstack, [1, 2, 4])
        self.assertEqual(tasks, [task])
        vm.dictate('resume 5')
        self.assertEqual(vm.dstack, [1, 2, 4, 3, 5])
        self.assertEqual(tasks, [])
        for name in ('.s', 'words', 'resume', 'see'):
            self.assertEqual(vm.tick(name).category, 'code')
        with self.assertRaisesRegex(KernelError, 'No paused task'):
            vm.dictate('resume')

    def test_colon_stack_words_and_bye(self):
        vm = self.explorer()
        for name in ('dup', 'over', 'swap', 'bye'):
            self.assertEqual(vm.tick(name).category, 'colon')
        vm.dictate('10 20 over')
        self.assertEqual(vm.dstack, [10, 20, 10])
        vm.dictate('swap dup')
        self.assertEqual(vm.dstack, [10, 10, 20, 20])
        task = vm.dictate('bye 99')
        self.assertEqual(task.status, 'aborted')
        self.assertTrue(vm.host['exit_requested'])
        self.assertEqual(vm.dstack, [10, 10, 20, 20])

    def explorer(self):
        vm = VM()
        vm.dictate(EXPLORER)
        return vm

    def test_seed_growth_and_capture(self):
        vm = VM()
        self.assertEqual(set(vm.words), {"code", "end-code"})
        self.assertEqual(VM().dstack, [])
        vm.dictate(EXPLORER)
        vm.dictate(": square dup * ; : old 6 square ;")
        vm.dictate("code square vm.push(99) end-code old square")
        self.assertEqual(vm.dstack, [36, 99])

    def test_host_objects_numeric_precedence_and_precision(self):
        resource = object()
        vm = VM({"resource": resource})
        vm.dictate("code resource vm.push(resource) end-code resource")
        self.assertIs(vm.pop(), resource)
        vm.dictate("9007199254740993 -0x10 0o10 0b11 2.5")
        self.assertEqual(vm.dstack, [9007199254740993, -16, 8, 3, 2.5])
        vm.define("123", lambda m: m.push("word"))
        vm.dictate("123")
        self.assertEqual(vm.pop(), "word")

    def test_input_contract(self):
        named = Input(tib='12 34', itib=3)
        self.assertEqual(named.tib, '12 34')
        self.assertEqual(named.itib, 3)
        self.assertEqual(named.read(), '34')
        self.assertEqual(named.itib, 5)
        with self.assertRaises(KernelError):
            named.itib = 6
        source = Input(" one two|tail")
        self.assertEqual(source.read(), "one")
        self.assertEqual(source.itib, 4)
        original = source.tib
        source.append(" more")
        self.assertEqual(source.itib, 4)
        self.assertTrue(source.tib.startswith(original))
        self.assertEqual(source.read("|"), " two")
        position = source.itib
        for boundary in ("missing", "", re.compile(r"")):
            with self.assertRaises(KernelError):
                source.read(boundary)
            self.assertEqual(source.itib, position)
        self.assertEqual(source.rest(), "tail more")
        self.assertIsNone(source.read())
        self.assertEqual(source.consume(100), "")
        with self.assertRaises(KernelError):
            source.consume(-1)

    def test_pause_colon_append_and_terminal(self):
        vm = self.explorer()
        vm.dictate(": sequence 1 pause 2 ;")
        task = vm.dictate("sequence")
        self.assertEqual(task.status, "paused")
        self.assertEqual(vm.dstack, [1])
        task.append_input(" 3")
        task.resume()
        self.assertEqual(vm.dstack, [1, 2, 3])
        self.assertEqual(task.status, "done")
        self.assertEqual((task.inputs, task.frames), ([], []))
        with self.assertRaises(KernelError):
            task.append_input(" 4")
        with self.assertRaises(KernelError):
            task.resume()

    def test_task_private_stacks_and_separate_reentry(self):
        vm = self.explorer()
        vm.define("save", lambda m: (m.rstack.append(m.pop()),
                                          m.tstack.append("private")))
        first = vm.dictate("11 save pause")
        second = vm.dictate("22 save pause")
        self.assertEqual(first.rstack, [11])
        self.assertEqual(second.rstack, [22])
        self.assertIsNot(first.tstack, second.tstack)
        first.resume()
        second.cancel()
        seen = []
        def reentry(m):
            outer = m.task
            child = m.dictate("33")
            seen.extend((child is not outer, m.task is outer))
        vm.define("reentry", reentry)
        vm.dictate("reentry")
        self.assertEqual(seen, [True, True])
        self.assertEqual(vm.dstack, [33])

    def test_nested_continuation_restores_input(self):
        vm = self.explorer()
        seen = []
        def nested(m):
            outer = m.input
            yield from m.evaluate("10 pause 20")
            seen.append(m.input is outer)
            yield from m.call("dup")
        vm.define("nested", nested)
        task = vm.dictate("nested 30")
        self.assertEqual(len(task.inputs), 2)
        task.append_input(" 25")
        task.resume()
        self.assertEqual(vm.dstack, [10, 20, 25, 25, 30])
        self.assertEqual(seen, [True])

    def test_cross_input_definition_and_immediate(self):
        vm = self.explorer()
        vm.dictate(": result 40")
        self.assertTrue(vm.compiling)
        self.assertIsNone(vm.tick("result"))
        self.assertEqual(vm.latest.name, "result")
        vm.dictate("2 + ; result")
        self.assertEqual(vm.dstack, [42])
        vm.dictate(': message s" hello" ; message')
        self.assertEqual(vm.pop(), "hello")

    def test_partial_failure_abort_and_cancellation(self):
        vm = self.explorer()
        vm.dictate(": stable 7 ;")
        old = vm.tick("stable")
        task = Task(vm, vm.evaluate("5 : stable 9 unknown"))
        with self.assertRaises(KernelError):
            task.resume()
        self.assertEqual(task.status, "failed")
        self.assertIsInstance(task.error, KernelError)
        self.assertIs(vm.tick("stable"), old)
        self.assertIs(vm.latest, old)
        self.assertEqual(vm.dstack, [5])
        vm.dictate("code stop vm.abort() end-code")
        self.assertEqual(vm.dictate("6 stop 8").status, "aborted")
        self.assertEqual(vm.dstack, [5, 6])
        def building(m):
            m.begin("unfinished")
            yield m.pause()
        vm.define("building", building)
        suspended = vm.dictate("building")
        suspended.cancel()
        self.assertFalse(vm.compiling)
        self.assertIsNone(vm.tick("unfinished"))
        self.assertEqual(suspended.inputs, [])

    def test_host_lexical_boundaries_and_multiline_strings(self):
        vm = VM()
        vm.dictate('''code text
    # end-code is a comment
    vm.push("end-code")
    vm.push("""first
  end-code
last""")
end-code text''')
        self.assertEqual(vm.dstack, ["end-code", "first\n  end-code\nlast"])
        vm.dictate("code empty end-code empty")
        old = vm.tick("text")
        with self.assertRaises(KernelError):
            vm.dictate("code text this is invalid python ! end-code")
        self.assertIs(vm.tick("text"), old)

    def test_depth_errors_and_host_failure_cause(self):
        vm = VM()
        vm.push(1, 2, 3)
        self.assertEqual(vm.peek(1), 2)
        self.assertEqual(vm.pop(1), 2)
        self.assertEqual(vm.dstack, [1, 3])
        for depth in (-1, 2, "0"):
            with self.assertRaises(KernelError):
                vm.pop(depth)
        vm.define("broken", lambda m: 1 / 0)
        with self.assertRaises(KernelError) as caught:
            vm.execute("broken")
        self.assertIn("broken", str(caught.exception))
        self.assertIsInstance(caught.exception.__cause__, ZeroDivisionError)

    def test_invalid_yield_unwinds(self):
        vm = VM()
        def bad(m):
            yield "invalid signal"
        vm.define("bad", bad)
        task = Task(vm, vm.evaluate("bad"))
        with self.assertRaises(KernelError):
            task.resume()
        self.assertEqual(task.status, "failed")
        self.assertEqual(task.inputs, [])
        self.assertEqual(vm._active, [])

    def test_extension_can_change_execution_position(self):
        vm = VM()
        vm.define("skip", lambda m: setattr(m.frame, "ip", m.frame.ip + 1))
        vm.begin("jump")
        vm.comma("skip")
        vm.literal("skipped")
        vm.literal("kept")
        vm.finish()
        vm.execute("jump")
        self.assertEqual(vm.dstack, ["kept"])


def repl(vm=None):
    if vm is None:
        vm = make_vm()
    vm.host.pop("exit_requested", None)
    paused_tasks = vm.host.setdefault('paused_tasks', [])
    print("Forth test vocabulary loaded; enter source at k>.")
    print("Enter help for instructions; bye exits.")
    try:
        while True:
            try:
                line = input("k> ")
            except EOFError:
                break
            try:
                if not line.strip():
                    continue
                task = vm.dictate(line)
                if vm.host.get('exit_requested'):
                    break
                if task.status == "paused":
                    paused_tasks.append(task)
                    print("Paused; enter resume to continue.")
            except Exception as error:
                print(f"{type(error).__name__}: {error}")
    except KeyboardInterrupt:
        print()
    finally:
        for task in paused_tasks:
            task.cancel()


def activity(vm):
    """Print before; evaluate 1 pause 2; then print after, in one Task.

    Register with vm.define('activity', activity), then use
    task = vm.execute('activity') and task.resume().
    """
    print("before")
    yield from vm.evaluate("1 pause 2")
    print("after")


def make_vm():
    """Construct a VM with the optional demonstration vocabulary."""
    vm = VM()
    vm.dictate(EXPLORER)
    return vm


if __name__ == "__main__":
    result = unittest.main(argv=[sys.argv[0]], exit=False).result
    if not result.wasSuccessful():
        raise SystemExit(1)
    vm = make_vm()
    banner = ("Project K Python lab: vm is ready, with the demo words loaded.\n"
              "Try vm.dictate('3 4 + .'), or help(activity).\n"
              "Use repl(vm) for the optional k> console; bye returns here.")
    print(banner)
    # With -i Python itself opens the shell using this module's globals.
    # Otherwise provide the same shell for `python -m demo`.
    if not sys.flags.interactive:
        code.interact(banner="", exitmsg="", local=globals())
