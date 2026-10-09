import contextlib
import importlib.machinery
import importlib.util
import io
import pathlib
import unittest

from projectk import VM, Input, ForthError, DEMO
import repl as _f_mod
Constant = _f_mod.Constant
Value = _f_mod.Value


class KernelTests(unittest.TestCase):
    def boot(self):
        vm = VM(host={'ForthError': ForthError})
        with contextlib.redirect_stdout(io.StringIO()):
            vm.dictate(DEMO).resume()
        return vm

    def test_seed_and_independent_instances(self):
        a, b = VM(), VM()
        self.assertEqual(set(a.words), {'code', 'end-code'})
        a.push(1)
        self.assertEqual(b.stack, [])

    def test_tick_and_callable_constant(self):
        vm = self.boot()
        self.assertIsNone(vm.tick('missing'))
        ten = vm.tick('ten')
        self.assertEqual(ten.value, 10)
        vm.dictate('ten')
        self.assertEqual(vm.pop(), 10)

    def test_exact_integers_and_literals(self):
        vm = VM()
        vm.dictate('9007199254740993 -0x10 2.5 0b11')
        self.assertEqual(vm.stack, [9007199254740993, -16, 2.5, 3])

    def test_host_objects(self):
        resource = {'name': 'resource'}
        vm = VM(host={'resource': resource})
        vm.dictate('code resource\n    vm.push(resource)\nend-code\nresource')
        self.assertIs(vm.pop(), resource)

    def test_input_regions(self):
        source = Input(' name first line\nseveral\nlines| tail')
        self.assertEqual(source.read(), 'name')
        self.assertEqual(source.read(until='\n'), ' first line')
        self.assertEqual(source.read(until='|'), 'several\nlines')
        self.assertEqual(source.read(), 'tail')
        self.assertIsNone(source.read())

    def test_input_tib_itib_and_pad(self):
        # 1. Normal single-string input initially has tib=[string], itib=0
        source = Input(": square dup * ; 5 square")
        self.assertEqual(source.tib, [": square dup * ; 5 square"])
        self.assertEqual(source.itib, 0)

        # 2. Reading triggers dynamic split into consumed tib[0] and pending tib[1] (itib=1)
        self.assertEqual(source.read(), ":")
        self.assertEqual(source.itib, 1)
        self.assertEqual(source.tib[0], ":")
        self.assertTrue(source.tib[1].startswith(" square"))

        # Consume up to '5'
        while source.read() != "5":
            pass

        # 3. Dynamic PAD injection behind itib: tib[2]
        source.tib.append(". cr")
        self.assertEqual(len(source.tib), 3)

        # 4. Finish current element, then seamlessly advance into PAD
        self.assertEqual(source.read(), "square")
        self.assertEqual(source.read(), ".")
        self.assertEqual(source.read(), "cr")
        self.assertIsNone(source.read())

    def test_composition_and_capture(self):
        vm = self.boot()
        vm.dictate(': old 6 square ;')
        vm.define('square', lambda v: v.push(99))
        vm.dictate('old square')
        self.assertEqual(vm.stack, [36, 99])

    def test_immediate_string_and_null_literal(self):
        vm = self.boot()
        vm.dictate(': message s" hello\nworld" ; message')
        self.assertEqual(vm.pop(), 'hello\nworld')
        vm.begin('nothing'); vm.literal(None); vm.finish()
        vm.execute('nothing')
        self.assertIsNone(vm.pop())

    def test_comma(self):
        vm = self.boot()
        vm.begin('calc')
        vm.literal(10)
        vm.comma(vm.tick('*'))
        vm.comma(vm.tick('square'))
        vm.finish()
        calc = vm.tick('calc')
        self.assertEqual(len(calc.action), 3)

        # Outside compiling raises error
        with self.assertRaisesRegex(ForthError, 'No definition is being built'):
            vm.comma(vm.tick('*'))

    def test_pause_inside_composition_and_source(self):
        vm = self.boot()
        vm.dictate(': step 1 pause 2 ;')
        task = vm.dictate('step 3')
        self.assertEqual((task.status, vm.stack), ('paused', [1]))
        self.assertEqual(task.resume().status, 'done')
        self.assertEqual(vm.stack, [1, 2, 3])
        self.assertFalse(task.inputs)

    def test_nested_resumable_work(self):
        vm = self.boot()
        def nested(v):
            yield from v.evaluate('5 pause 6')
            v.push(7)
        vm.define('nested', nested)
        task = vm.dictate('nested 8')
        self.assertEqual(vm.stack, [5])
        task.resume()
        self.assertEqual(vm.stack, [5, 6, 7, 8])

    def test_host_reentry(self):
        vm = VM()
        vm.define('nested', lambda v: v.dictate('20'))
        vm.dictate('10 nested 30')
        self.assertEqual(vm.stack, [10, 20, 30])

    def test_generator_continuation(self):
        vm = VM()
        def word(v):
            v.push('before')
            yield v.pause()
            v.push('after')
        vm.define('work', word)
        task = vm.execute('work')
        self.assertEqual(vm.stack, ['before'])
        task.resume()
        self.assertEqual(vm.stack, ['before', 'after'])

    def test_definition_across_inputs(self):
        vm = self.boot()
        vm.dictate(': twice dup')
        self.assertTrue(vm.compiling)
        vm.dictate('* ; 7 twice')
        self.assertEqual(vm.stack, [49])

    def test_bad_definition_preserves_old_word(self):
        vm = VM()
        vm.define('keep', lambda v: v.push(1))
        with self.assertRaises(ForthError):
            vm.dictate('code keep\n    this is invalid syntax!\nend-code')
        vm.dictate('keep')
        self.assertEqual(vm.pop(), 1)

    def test_definition_errors_recover(self):
        vm = self.boot()
        with self.assertRaises(ForthError):
            vm.dictate(': broken missing ;')
        self.assertFalse(vm.compiling)
        self.assertNotIn('broken', vm.words)
        vm.dictate('8 square')
        self.assertEqual(vm.pop(), 64)

    def test_abort_and_cancel(self):
        vm = self.boot()
        vm.define('abort', lambda v: v.abort())
        self.assertEqual(vm.dictate('1 abort 2').status, 'aborted')
        self.assertEqual(vm.stack, [1])
        task = vm.dictate('3 pause 4')
        task.cancel()
        self.assertEqual(task.status, 'aborted')
        self.assertFalse(task.inputs)
        vm.dictate('5')
        self.assertEqual(vm.stack, [1, 3, 5])

    def test_string_terminator_is_data(self):
        vm = VM()
        vm.dictate('code message\n    vm.push("""hello\nend-code\nworld""")\nend-code\nmessage 7')
        self.assertEqual(vm.stack, ['hello\nend-code\nworld', 7])

    def test_code_single_line_and_inline_end_code(self):
        vm = VM()
        vm.dictate("code inc vm.push(vm.pop() + 1) end-code 5 inc")
        self.assertEqual(vm.stack, [6])
        vm.dictate("code double vm.push(vm.pop() * 2) end-code 7 double")
        self.assertEqual(vm.stack, [6, 14])
        vm.dictate("code triple\n    x = vm.pop()\n    vm.push(x * 3) end-code\n10 triple")
        self.assertEqual(vm.stack, [6, 14, 30])
        vm.dictate("code with_comment\n    # end-code in comment\n    vm.push(99) end-code\nwith_comment")
        self.assertEqual(vm.stack, [6, 14, 30, 99])


    def test_diagnostics_and_retry(self):
        vm = VM()
        with self.assertRaisesRegex(ForthError, 'empty'):
            vm.pop()
        for text in ['unknown', 'end-code', 'code', 'code broken\n vm.push(1)']:
            with self.assertRaises(ForthError):
                vm.dictate(text)
            vm.dictate('42')
            self.assertEqual(vm.pop(), 42)
        self.assertFalse(vm._active)

    def test_failure_after_pause(self):
        vm = VM()
        def bad(v):
            yield v.pause()
            raise ValueError('oops')
        vm.define('bad', bad)
        task = vm.dictate('bad 9')
        with self.assertRaisesRegex(ForthError, 'oops'):
            task.resume()
        self.assertEqual(task.status, 'failed')
        self.assertFalse(task.inputs)
        vm.dictate('10')
        self.assertEqual(vm.pop(), 10)

    def test_invalid_yield_closes_continuation(self):
        vm = VM()
        def bad(v):
            yield 'unexpected'
        vm.define('bad', bad)
        with self.assertRaises(ForthError):
            vm.dictate('bad 9')
        self.assertFalse(vm._active)
        vm.dictate('10')
        self.assertEqual(vm.pop(), 10)

    def test_pop_with_depth(self):
        vm = VM()
        vm.push(10, 20, 30)
        self.assertEqual(vm.pop(0), 30)
        self.assertEqual(vm.pop(1), 10)
        self.assertEqual(vm.pop(), 20)
        with self.assertRaisesRegex(ForthError, 'empty'):
            vm.pop()
        vm.push(10)
        with self.assertRaisesRegex(ForthError, 'depth'):
            vm.pop(1)

    def test_word_help_and_comment_fields(self):
        vm = VM()
        word = vm.define('greet', lambda v: None, help='say hello', comment='\tnote\n')
        self.assertEqual(word.help, 'say hello')
        self.assertEqual(word.comment, '\tnote\n')
        word2 = vm.define('bye', lambda v: None)
        self.assertEqual(word2.help, '')
        self.assertEqual(word2.comment, '')

    def test_value_class_and_property(self):
        vm = VM()
        word = vm.define('total', Value(10), type='value')
        self.assertEqual(word.value, 10)
        word.value = 25
        self.assertEqual(word.value, 25)
        self.assertEqual(word.action.value, 25)
        vm.execute('total')
        self.assertEqual(vm.pop(), 25)

        const_word = vm.define('limit', Constant(100), type='constant')
        self.assertEqual(const_word.value, 100)


class ReplBootstrapTests(unittest.TestCase):
    def setUp(self):
        self.vm = _f_mod.create_vm()

    def test_multiline_editor_submission_runs_as_one_forth_buffer(self):
        state = {"in_code_block": False, "code_buffer": [], "ai_task": None}
        with contextlib.redirect_stdout(io.StringIO()):
            _f_mod._process_one_line(self.vm, ": square\n dup *\n;\n5 square", state)
        self.assertEqual(self.vm.pop(), 25)

    def test_multiline_ai_prompt_is_preserved_as_one_message(self):
        state = {"in_code_block": False, "code_buffer": [], "ai_task": None}
        received = []

        def fake_ask(vm, prompt):
            received.append(prompt)
            yield {"kind": "text", "text": "First line.\nSecond line."}
            yield {"kind": "text_done", "text": "First line.\nSecond line."}

        original_ask = _f_mod.ai_bridge.ask
        _f_mod.ai_bridge.ask = fake_ask
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                _f_mod._process_one_line(self.vm, "ai: First line.\nSecond line.", state)
        finally:
            _f_mod.ai_bridge.ask = original_ask

        self.assertEqual(received, ["First line.\nSecond line."])

    def test_multiline_key_bindings_submit_and_insert_newlines(self):
        class RecordingBindings:
            def __init__(self):
                self.handlers = {}

            def add(self, *keys):
                def register(handler):
                    self.handlers[keys] = handler
                    return handler
                return register

        bindings = _f_mod._make_multiline_key_bindings(RecordingBindings)

        class Buffer:
            def __init__(self):
                self.inserted = []
                self.submitted = False

            def insert_text(self, text):
                self.inserted.append(text)

            def validate_and_handle(self):
                self.submitted = True

        class Event:
            def __init__(self):
                self.current_buffer = Buffer()

        enter = Event()
        bindings.handlers[("c-m",)](enter)
        self.assertTrue(enter.current_buffer.submitted)

        for keys in (("c-j",), ("escape", "c-m")):
            event = Event()
            bindings.handlers[keys](event)
            self.assertEqual(event.current_buffer.inserted, ["\n"])

    def test_modified_enter_sequences_map_to_newline(self):
        sequences = {}
        _f_mod._map_extended_enter_sequences(sequences, "c-j")
        self.assertEqual(sequences["\x1b[27;2;13~"], "c-j")
        self.assertEqual(sequences["\x1b[13;2u"], "c-j")

    def test_help_and_comment(self):
        self.vm.dictate(': hi s" Hello!" . ; // ( -- ) Greeting\n/// Line 1\n/// Line 2\n')
        word = self.vm.tick('hi')
        self.assertEqual(word.help, '( -- ) Greeting')
        self.assertEqual(word.comment, 'Line 1\nLine 2\n')

    def test_help_and_comment_inside_colon_definition(self):
        prev_word = self.vm.last()
        self.vm.dictate(': greeting // a greeting\n/// Note 1\ns" hello world!" . ;\n')
        word = self.vm.tick('greeting')
        self.assertEqual(word.help, 'a greeting')
        self.assertEqual(word.comment, 'Note 1\n')
        self.assertNotEqual(prev_word.help, 'a greeting')

    def test_last_word(self):
        self.vm.dictate(': sample 42 . ; last')
        w = self.vm.pop()
        self.assertEqual(w.name, 'sample')

    def test_colon_colon_and_colon_greater(self):
        self.vm.dictate(": hi s\" Hello!\" . ; s\" Custom\" ' hi :: help=pop(1)")
        word = self.vm.tick('hi')
        self.assertEqual(word.help, 'Custom')
        self.vm.dictate("' hi :> help")
        self.assertEqual(self.vm.pop(), 'Custom')
        self.vm.dictate("' hi :> help.upper()")
        self.assertEqual(self.vm.pop(), 'CUSTOM')

    def test_colon_colon_and_colon_greater_in_colon_word(self):
        self.vm.dictate(": hi s\" Hello!\" . ;")
        self.vm.dictate(": set-h s\" GodHelps\" ' hi :: help=pop(1) ;")
        self.vm.dictate(": get-h ' hi :> help ;")
        self.vm.dictate("set-h get-h")
        self.assertEqual(self.vm.pop(), 'GodHelps')

    def test_dot_output(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate("123 . 456 .")
        self.assertEqual(buf.getvalue(), "123456")

    def test_see_output(self):
        self.vm.dictate(': hi s" Hello!" . ; // A greeting\n/// Note 1\n')
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate('see hi')
        output = buf.getvalue()
        self.assertIn('hi A greeting', output)
        self.assertIn('    Note 1', output)
        self.assertIn("'name': 'hi'", output)
        self.assertIn("'type': 'colon'", output)
        self.assertIn(': hi', output)

    def test_value_and_to(self):
        # Definition & interpret usage
        self.vm.dictate('10 value total total')
        self.assertEqual(self.vm.pop(), 10)
        self.vm.dictate('20 to total total')
        self.assertEqual(self.vm.pop(), 20)

        # Python reading & writing
        word = self.vm.tick('total')
        self.assertEqual(word.value, 20)
        word.value = 99
        self.vm.dictate('total')
        self.assertEqual(self.vm.pop(), 99)

        # In colon definitions
        self.vm.dictate(': inc total 1 + to total ; inc total')
        self.assertEqual(self.vm.pop(), 100)

        # see output
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate('see total')
        self.assertIn('100 value total', buf.getvalue())

        with contextlib.redirect_stdout(buf):
            self.vm.dictate('see inc')
        self.assertIn(': inc total 1 + to total ;', buf.getvalue())

        # Error when assigning to constant or non-existent
        self.vm.dictate('50 constant limit')
        with self.assertRaisesRegex(ForthError, 'not a value'):
            self.vm.dictate('60 to limit')
        with self.assertRaisesRegex(ForthError, 'Unknown word'):
            self.vm.dictate('60 to nonexistent')

    def test_forth_comma(self):
        # Define meta-compiling macro using comma
        self.vm.dictate(': compile-add [\'] + , ; immediate')
        self.vm.dictate(': calc 10 20 compile-add ; calc')
        self.assertEqual(self.vm.pop(), 30)

        # In interpret mode, comma raises ForthError
        with self.assertRaisesRegex(ForthError, 'No definition is being built'):
            self.vm.dictate("[\'] + ,")

    def test_return_stack(self):
        self.vm.dictate('10 >r 20 >r r@ r> r>')
        self.assertEqual(self.vm.pop(), 10)
        self.assertEqual(self.vm.pop(), 20)
        self.assertEqual(self.vm.pop(), 20)
        # A new task has its own empty return stack; r> must underflow
        with self.assertRaisesRegex(ForthError, 'Return stack underflow'):
            self.vm.dictate('r>')

    def test_return_stack_task_private_isolation(self):
        # Task 1 pushes to return stack and pauses
        task1 = self.vm.dictate('10 >r 20 >r pause r> r>')
        self.assertEqual(task1.status, 'paused')
        self.assertEqual(task1.rstack, [10, 20])

        # Task 2 runs independently with its own return stack
        self.vm.dictate('999 >r r@ r>')
        self.assertEqual(self.vm.pop(), 999)
        self.assertEqual(self.vm.pop(), 999)

        # Task 1's rstack was not touched by Task 2
        self.assertEqual(task1.rstack, [10, 20])

        # Resume Task 1 and verify it pops its own values
        task1.resume()
        self.assertEqual(task1.status, 'done')
        self.assertEqual(self.vm.pop(), 10)
        self.assertEqual(self.vm.pop(), 20)

    def test_for_next_task_isolation(self):
        # Task 1 pauses inside for...next loop
        task1 = self.vm.dictate(': pause-loop 2 for r@ pause next ; pause-loop')
        self.assertEqual(task1.status, 'paused')
        self.assertEqual(task1.rstack, [2])

        # Task 2 runs its own for...next loop to completion while Task 1 is paused
        self.vm.dictate(': other-loop 0 3 for r@ + next ; other-loop')
        self.assertEqual(self.vm.pop(), 6)  # 3+2+1 = 6

        # Task 1's loop counter is completely unharmed
        self.assertEqual(task1.rstack, [2])
        task1.resume()
        self.assertEqual(task1.status, 'paused')
        self.assertEqual(task1.rstack, [1])
        task1.resume()
        self.assertEqual(task1.status, 'done')

    def test_if_else_then(self):
        self.vm.dictate(': check-gt 10 > if 100 else 200 then ;')
        self.vm.dictate('15 check-gt')
        self.assertEqual(self.vm.pop(), 100)
        self.vm.dictate('5 check-gt')
        self.assertEqual(self.vm.pop(), 200)

        # Single if then
        self.vm.dictate(': check-pos dup 0 > if 1+ then ;')
        self.vm.dictate('5 check-pos')
        self.assertEqual(self.vm.pop(), 6)
        self.vm.dictate('-5 check-pos')
        self.assertEqual(self.vm.pop(), -5)

        # Nested if else then
        self.vm.dictate('''
        : nested-if
            dup 0 > if
                dup 10 > if
                    100
                else
                    50
                then
            else
                0
            then nip ;
        ''')
        self.vm.dictate('20 nested-if')
        self.assertEqual(self.vm.pop(), 100)
        self.vm.dictate('5 nested-if')
        self.assertEqual(self.vm.pop(), 50)
        self.vm.dictate('-3 nested-if')
        self.assertEqual(self.vm.pop(), 0)

        # Pause inside if
        self.vm.dictate(': pause-if 1 if 42 pause 99 then ;')
        task = self.vm.dictate('pause-if')
        self.assertEqual(task.status, 'paused')
        self.assertEqual(self.vm.stack, [42])
        task.resume()
        self.assertEqual(task.status, 'done')
        self.assertEqual(self.vm.stack, [42, 99])
        self.vm.stack.clear()

    def test_for_next(self):
        self.vm.dictate(': countdown 0 5 for r@ + next ; countdown')
        # 0 + 5 + 4 + 3 + 2 + 1 = 15
        self.assertEqual(self.vm.pop(), 15)

        # Early exit using return stack modification
        self.vm.dictate(': early-exit 0 10 for r@ + r@ 5 = if r> drop 0 >r then next ; early-exit')
        # 0 + 10 + 9 + 8 + 7 + 6 + 5 = 45
        self.assertEqual(self.vm.pop(), 45)

        # Nested for next
        self.vm.dictate(': nested-loop 0 3 for 2 for 1+ next next ; nested-loop')
        # 3 * 2 = 6
        self.assertEqual(self.vm.pop(), 6)

        # Pause inside for-next
        self.vm.dictate(': pause-for 2 for r@ pause next ;')
        task = self.vm.dictate('pause-for')
        self.assertEqual(task.status, 'paused')
        self.assertEqual(self.vm.stack, [2])
        task.resume()
        self.assertEqual(task.status, 'paused')
        self.assertEqual(self.vm.stack, [2, 1])
        task.resume()
        self.assertEqual(task.status, 'done')
        self.assertEqual(self.vm.stack, [2, 1])
        self.vm.stack.clear()

    def test_begin_loops(self):
        # begin ... until
        self.vm.dictate(': sum-until 0 1 begin swap over + swap 1+ dup 10 > until drop ; sum-until')
        self.assertEqual(self.vm.pop(), 55)

        # begin ... while ... repeat
        self.vm.dictate(': sum-while 0 1 begin dup 10 <= while swap over + swap 1+ repeat drop ; sum-while')
        self.assertEqual(self.vm.pop(), 55)

        # begin ... while ... until ... then
        self.vm.dictate(': sum-while-until 0 1 begin dup 20 <= while swap over + swap 1+ dup 10 > until then drop ; sum-while-until')
        self.assertEqual(self.vm.pop(), 55)

    def test_control_errors(self):
        with self.assertRaisesRegex(ForthError, 'No definition is being built'):
            self.vm.dictate('if')
        with self.assertRaisesRegex(ForthError, 'No definition is being built'):
            self.vm.dictate('for')
        with self.assertRaisesRegex(ForthError, 'Data stack is empty'):
            self.vm.dictate(': bad-then then ;')
        with self.assertRaisesRegex(ForthError, 'Data stack is empty'):
            self.vm.dictate(': bad-next next ;')
        with self.assertRaisesRegex(ForthError, 'Data stack is empty'):
            self.vm.dictate(': bad-repeat repeat ;')

    def test_words_command(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate('words')
        all_words_output = buf.getvalue().strip().split()
        self.assertEqual(set(all_words_output), set(self.vm.words.keys()))

        # Single pattern
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate('words drop')
        self.assertEqual(buf.getvalue().strip(), 'drop dropall rdrop')

        # Case-insensitive
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate('words DROP')
        self.assertEqual(buf.getvalue().strip(), 'drop dropall rdrop')

        # Multiple patterns (AND logic)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate('words py :')
        self.assertEqual(buf.getvalue().strip(), 'py: py::')

        # Non-matching pattern
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate('words no_such_word')
        self.assertEqual(buf.getvalue().strip(), '')

    def test_help_command(self):
        # Help on specific word with formatting
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate('help dup')
        dup_output = buf.getvalue().strip()
        expected_dup = (
            "dup ( x -- x x ) Duplicate the top item on the data stack.\n"
            "    Push a duplicate of TOS (top-of-stack) onto the data stack."
        )
        self.assertEqual(dup_output, expected_dup)

        # Help with custom word and multi-line comments
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate(': demo-fn ; // ( a -- b ) Custom demo\n/// Line 1\n/// Line 2\nhelp demo-fn')
        demo_output = buf.getvalue().strip()
        expected_demo = (
            "demo-fn ( a -- b ) Custom demo\n"
            "    Line 1\n"
            "    Line 2"
        )
        self.assertEqual(demo_output, expected_demo)

        # Help with multiple patterns (AND logic)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate('help for loop')
        out = buf.getvalue().strip()
        lines = out.split('\n\n')
        # Exact/primary word 'for' comes first
        self.assertTrue(lines[0].startswith('for '))
        self.assertTrue(any(e.startswith('next ') for e in lines))

        # Help with no patterns outputs entire dictionary manual
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate('help')
        all_help = buf.getvalue().strip()
        self.assertIn('code ( <name> -- )', all_help)
        self.assertIn('dup ( x -- x x )', all_help)
        self.assertIn('if ( flag -- )', all_help)

    def test_string_delimiters(self):
        # 1. Double quote s"
        self.vm.dictate('s" this is a book"')
        self.assertEqual(self.vm.pop(), "this is a book")

        # 2. Single quote s' (can embed double quotes)
        self.vm.dictate('s\' he said "hello"\'')
        self.assertEqual(self.vm.pop(), 'he said "hello"')

        # 3. Backtick s`
        self.vm.dictate('s` markdown code`')
        self.assertEqual(self.vm.pop(), 'markdown code')

        # 4. Pipe s|
        self.vm.dictate('s| path/to/file|')
        self.assertEqual(self.vm.pop(), 'path/to/file')

        # 5. Caret s^
        self.vm.dictate('s^ [0-9]+^')
        self.assertEqual(self.vm.pop(), '[0-9]+')

        # 6. Slash s/
        self.vm.dictate('s/ hello world from slash/')
        self.assertEqual(self.vm.pop(), 'hello world from slash')

        # Leading whitespace preservation: only the first separator space is stripped
        self.vm.dictate('s"   two leading spaces"')
        self.assertEqual(self.vm.pop(), '  two leading spaces')

        # Multi-line string
        self.vm.dictate('s" line 1\nline 2"')
        self.assertEqual(self.vm.pop(), 'line 1\nline 2')

        # Compilation mode inside colon definition
        self.vm.dictate(': greet s" Welcome!" ; greet')
        self.assertEqual(self.vm.pop(), 'Welcome!')

    def test_char_token(self):
        # Single char
        self.vm.dictate('char "')
        self.assertEqual(self.vm.pop(), '"')

        # Multi-character non-whitespace string token (enhanced char)
        self.vm.dictate('char hello')
        self.assertEqual(self.vm.pop(), 'hello')
        self.vm.dictate('char token_123')
        self.assertEqual(self.vm.pop(), 'token_123')

        # Compilation mode inside colon definition
        self.vm.dictate(': get-tag char <my-tag> ; get-tag')
        self.assertEqual(self.vm.pop(), '<my-tag>')

        # Missing token raises ForthError
        with self.assertRaisesRegex(ForthError, 'char expects a token'):
            self.vm.dictate('char')

    def test_create_does(self):
        # Custom defining word via create ... does>
        self.vm.dictate(': mk-adder create , does> @ + ;')
        self.vm.dictate('10 mk-adder add10')
        self.assertEqual(self.vm.tick('add10').type, 'mk-adder')

        self.vm.dictate('5 add10')
        self.assertEqual(self.vm.pop(), 15)
        self.vm.dictate('100 add10')
        self.assertEqual(self.vm.pop(), 110)

        # Another custom defining word: constant factory defined by user
        self.vm.dictate(': my-const create , does> @ ;')
        self.vm.dictate('999 my-const k999')
        self.vm.dictate('k999')
        self.assertEqual(self.vm.pop(), 999)

    def test_variable_and_store_fetch(self):
        self.vm.dictate('variable counter')
        # Initial value is 0
        self.vm.dictate('counter @')
        self.assertEqual(self.vm.pop(), 0)

        # Store new value
        self.vm.dictate('42 counter !')
        self.vm.dictate('counter @')
        self.assertEqual(self.vm.pop(), 42)

        # Modify inside colon definition
        self.vm.dictate(': inc counter @ 1 + counter ! ; inc inc counter @')
        self.assertEqual(self.vm.pop(), 44)

    def test_see_defining_words(self):
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate('see constant')
        self.assertIn(': constant create , does> @ ;', buf.getvalue())

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate('see value')
        self.assertIn(': value create , does> @ ;', buf.getvalue())

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate('see variable')
        self.assertIn(': variable create 0 , ;', buf.getvalue())

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate('see string-quote')
        self.assertIn(': string-quote create , immediate does> @ (s) ;', buf.getvalue())

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate('see s"')
        self.assertIn('char \'"\' string-quote s"', buf.getvalue())
        self.assertIn('Friends: s" s\' s` s| s^ s/', buf.getvalue())

    def test_see_code_and_created_words(self):
        # 1. see on code word (e.g. create)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate('see create')
        out_create = buf.getvalue()
        self.assertIn('create ( <name> -- )', out_create)
        self.assertIn("'name': 'create'", out_create)
        self.assertIn("'type': 'code'", out_create)
        self.assertIn("'help': '...'", out_create)
        self.assertIn("'comment': '...'", out_create)
        self.assertIn("'source': '...'", out_create)
        self.assertIn('code create', out_create)
        self.assertIn('end-code', out_create)

        # 2. see on created word with body (e.g. xx)
        self.vm.dictate('create xx 123 , 456 ,')
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate('see xx')
        out_xx = buf.getvalue()
        self.assertIn("'name': 'xx'", out_xx)
        self.assertIn("'type': 'created'", out_xx)
        self.assertIn("'body': [123, 456]", out_xx)
        self.assertIn('created xx (body: [123, 456])', out_xx)

        # 3. ' create . prints native dataclass _Word(...) representation
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            self.vm.dictate("' create .")
        out_tick = buf.getvalue()
        self.assertTrue(out_tick.startswith("_Word(name='create'"))
        self.assertIn("help='( <name> -- )", out_tick)


if __name__ == '__main__':
    unittest.main()
