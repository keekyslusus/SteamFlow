import threading
import time


class BackgroundTaskManager:
    def __init__(self, thread_factory=threading.Thread, sleeper=time.sleep):
        self.thread_factory = thread_factory
        self.sleeper = sleeper

    def start(self, target, *args, **kwargs):
        if args or kwargs:
            def thread_target():
                target(*args, **kwargs)
        else:
            thread_target = target

        thread = self.thread_factory(target=thread_target, daemon=True)
        thread.start()
        return thread

    def start_delayed(self, delay_seconds, target, *args, **kwargs):
        def worker():
            if delay_seconds > 0:
                self.sleeper(delay_seconds)
            target(*args, **kwargs)

        return self.start(worker)

    def start_flagged_refresh(self, plugin, pending_flag_name, refresh_method):
        with plugin.state_lock:
            if getattr(plugin, pending_flag_name):
                return False
            setattr(plugin, pending_flag_name, True)
        self.start(refresh_method)
        return True

    def finish_flagged_refresh(self, plugin, pending_flag_name):
        with plugin.state_lock:
            setattr(plugin, pending_flag_name, False)

    def start_keyed_refresh(self, plugin, pending_set_name, key, refresh_method):
        key = str(key)
        with plugin.state_lock:
            pending_refreshes = getattr(plugin, pending_set_name)
            if key in pending_refreshes:
                return False
            pending_refreshes.add(key)
        self.start(refresh_method, key)
        return True

    def finish_keyed_refresh(self, plugin, pending_set_name, key):
        with plugin.state_lock:
            getattr(plugin, pending_set_name).discard(str(key))


DEFAULT_BACKGROUND_TASK_MANAGER = BackgroundTaskManager()


def get_background_task_manager(plugin=None):
    if plugin is not None:
        manager = getattr(plugin, "background_task_manager", None)
        if manager is not None:
            return manager
    return DEFAULT_BACKGROUND_TASK_MANAGER


def start_daemon_task(target, *args, **kwargs):
    return DEFAULT_BACKGROUND_TASK_MANAGER.start(target, *args, **kwargs)


def start_delayed_daemon_task(delay_seconds, target, *args, **kwargs):
    return DEFAULT_BACKGROUND_TASK_MANAGER.start_delayed(delay_seconds, target, *args, **kwargs)


def start_flagged_refresh(plugin, pending_flag_name, refresh_method):
    return get_background_task_manager(plugin).start_flagged_refresh(plugin, pending_flag_name, refresh_method)


def finish_flagged_refresh(plugin, pending_flag_name):
    get_background_task_manager(plugin).finish_flagged_refresh(plugin, pending_flag_name)


def start_keyed_refresh(plugin, pending_set_name, key, refresh_method):
    return get_background_task_manager(plugin).start_keyed_refresh(plugin, pending_set_name, key, refresh_method)


def finish_keyed_refresh(plugin, pending_set_name, key):
    get_background_task_manager(plugin).finish_keyed_refresh(plugin, pending_set_name, key)
