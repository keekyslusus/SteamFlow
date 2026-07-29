import threading


def wait_for_worker_result(process):
    wait = getattr(process, "wait", None)
    if not callable(wait):
        raise TypeError("Worker process does not support waiting")
    return wait() == 0


def start_worker_feedback_monitor(
    plugin,
    process,
    on_complete,
    thread_factory=threading.Thread,
):
    show_msg = getattr(plugin, "show_msg", None)
    wait = getattr(process, "wait", None)
    if not callable(show_msg) or not callable(wait):
        return None

    def monitor():
        try:
            succeeded = wait_for_worker_result(process)
        except Exception:
            succeeded = False
        try:
            on_complete(succeeded)
        except Exception:
            log_exception = getattr(plugin, "log_exception", None)
            if callable(log_exception):
                log_exception("Failed to report Steam worker result")

    thread = thread_factory(target=monitor, daemon=False)
    thread.start()
    return thread
