\ repl.f - Interactive REPL for Project K (v2.1.0)

code repl
    vm.host.pop("exit_requested", None)
    paused_tasks = vm.host.setdefault('paused_tasks', [])
    print("Project K Forth 2.1.0 (with AI support)")
    print("Type 'help' for instructions, 'ai: <prompt>' for AI assistance, 'bye' to exit.")
    try:
        while True:
            try:
                line = input("forth> ")
            except EOFError:
                break
            line_str = line.strip()
            if not line_str:
                continue
            try:
                task = vm.dictate(line)
                if vm.host.get("exit_requested"):
                    break
                if task.status == "paused":
                    if task not in paused_tasks:
                        paused_tasks.append(task)
                    if not vm.host.get("pending_ai_task"):
                        print("Task paused. Type 'resume' to continue.")
            except Exception as error:
                print(f"{type(error).__name__}: {error}")
    except KeyboardInterrupt:
        print()
    finally:
        for t in list(paused_tasks):
            if t.status in ("ready", "paused"):
                t.cancel()
    end-code
    // ( -- ) Start interactive Forth REPL loop.
    /// Run Forth prompt loop (forth>) until bye or EOF.
    last :: safe=True
