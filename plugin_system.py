# This code was originally taken from https://github.com/zeuxisoo/python-pluginplot
import asyncio
import os
import sys
import threading
import traceback
import types
from concurrent.futures import ThreadPoolExecutor
from importlib import machinery, util
from os.path import isfile

import settings
from database import *

try:
    from settings import ENABLED_PLUGINS, DATABASE_SETTINGS, IS_GROUP
except ImportError:
    ENABLED_PLUGINS, DATABASE_SETTINGS, IS_GROUP = None, None, False


class Stopper:
    __slots__ = ("stop", "sleep")

    def __init__(self, sleep):
        self.stop = False
        self.sleep = sleep


class Plugin(object):
    __slots__ = ("deferred_events", "scheduled_funcs", "name", "usage", "first_command",
                 "init_funcs", "data", "temp_data", "process_pool", "folder", "plugin_id")

    def __init__(self, name: str = "Пустота", usage: list = None, plugin_id: str=""):
        self.name = name
        self.first_command = ''
        self.process_pool = None

        self.plugin_id = plugin_id
        if not self.plugin_id:
            self.plugin_id = self.name

        self.folder = ''

        self.deferred_events = []
        self.scheduled_funcs = []
        self.init_funcs = []

        self.init_usage(usage)

        self.temp_data = {}

        hues.warn(self.name)

    def init_usage(self, usage):
        if usage is None:
            usage = []

        if isinstance(usage, str):
            usage = [usage]

        self.usage = usage

    async def is_mine(self, user):
        return user.status == self.plugin_id

    @staticmethod
    async def is_free(user):
        return not user.status

    async def lock(self, user, message=None):
        r = await self.is_mine(user)

        if r:
            return True, ""

        r = await self.is_free(user)

        if not r:
            return r, user.status_locked_message

        user.status = self.plugin_id

        if message is None:
            user.status_locked_message = f"Вы заняты в плагине: {self.name}"
        else:
            user.status_locked_message = message

        await db.update(user)

        return True, ""

    async def unlock(self, user):
        r = await self.is_free(user)
        if r:
            return True

        user.status = None
        user.status_locked_message = None

        await db.update(user)

        return True

    async def get_user_status(self, user):
        r = await db.execute(Status.select().where(
            (Status.user_id == user.user_id) &
            (Status.plugin_id == self.plugin_id))
        )

        if not r:
            return -1

        return r[0].value

    async def set_user_status(self, user, value):
        try:
            await db.execute(Status.delete().where(
                (Status.user_id == user.user_id) &
                (Status.plugin_id == self.plugin_id))
            )

            await db.create(Status, user_id=user.user_id, plugin_id=self.plugin_id, value=value)

        except Exception as e:
            import traceback
            traceback.print_exc()

            return False

        return True

    async def clear_user(self, user):
        await self.unlock(user)
        await self.set_user_status(user, 0)

    @staticmethod
    def log(message: str):
        hues.info(f'Плагин {self.name} -> {message}')

    def status_wrapper(self, func, status):
        if status is None:
            return func

        async def wrapper(*args, **kwargs):
            if args and hasattr(args[0], "user") and await self.get_user_status(args[0].user) == status:
                return await func(*args, **kwargs)

            return False

        return wrapper

    @staticmethod
    def schedule(seconds):
        def decorator(func):
            async def wrapper(*args, **kwargs):
                stopper = Stopper(seconds)
                while not stopper.stop:
                    # Спим указанное кол-во секунд
                    # При этом другие корутины могут работать
                    await asyncio.sleep(stopper.sleep)
                    # Выполняем саму функцию
                    await func(stopper, *args, **kwargs)

            return wrapper

        return decorator

    # Выполняется при инициализации
    def on_init(self):
        def decorator(func):
            self.init_funcs.append(func)

            return func

        return decorator

    def on_message(self, status=None):
        def decorator(func):
            wrapper = self.status_wrapper(func, status)

            if settings.READ_OUT:
                async def wrapper_twice(*args, **kwargs):
                    if args and hasattr(args[0], "is_out") and not args[0].is_out:
                        return await wrapper(*args, **kwargs)

            else:
                wrapper_twice = wrapper

            self.add_func("", wrapper_twice)

            return wrapper

        return decorator

    # Декоратор события (запускается при первом запуске)
    def on_command(self, *commands, status=None):
        def decorator(func):
            wrapper = self.status_wrapper(func, status)

            if commands:  # Если написали, какие команды используются
                # Первая команда - отображается в списке команд (чтобы не было много команд не было)
                self.first_command = commands[0]

                for command in commands:
                    self.add_func(command, wrapper)
            else:  # Если нет - используем имя плагина в качестве команды (в нижнем регистре)
                self.add_func(self.name.lower(), wrapper)

            return wrapper

        return decorator

    def after_command(self, priority=0):
        def decorator(func):
            self.add_middleware(func, False, priority)

            return func

        return decorator

    def before_command(self, priority=0):
        def decorator(func):
            self.add_middleware(func, True, priority)

            return func

        return decorator

    def add_middleware(self, func, before, priority=0):
        def event(system: PluginSystem):
            system.add_middleware(func, before, priority)

        self.deferred_events.append(event)

    def add_func(self, command, func):
        if command is None:
            raise ValueError("Command can not be None")

        def event(system: PluginSystem):
            system.add_command(command, func)

        self.deferred_events.append(event)

    # Register events for plugin
    def register(self, system):
        for deferred_event in self.deferred_events:
            deferred_event(system)

        system.scheduled_events += self.scheduled_funcs


local_data = threading.local()

shared_space = types.ModuleType(__name__ + '.shared_space')
shared_space.__path__ = []
sys.modules[shared_space.__name__] = shared_space


class PluginSystem(object):
    def __init__(self, vk, folder=None):
        self.commands = {}
        self.group_commands = {}
        self.on_messages = []
        self.folder = folder
        self.plugins = set()
        self.scheduled_events = []

        self.before_command = []
        self.after_command = []

        self.process_pool = ThreadPoolExecutor()
        self.vk = vk

    def get_plugins(self) -> set:
        return self.plugins

    def add_middleware(self, func, before, priority):
        if before:
            self.before_command.append((func, priority))
            self.before_command.sort(key=lambda x: x[1], reverse=True)

        else:
            self.after_command.append((func, priority))
            self.after_command.sort(key=lambda x: x[1], reverse=True)

    def add_command(self, name, func):
        name = name.lower()

        if name == '':
            self.on_messages.append(func)
            return

        if name in self.commands:  # если уже есть хоть 1 команда, добавляем к списку
            self.commands[name].append(func)

        else:  # если нет, создаём новый список
            self.commands[name] = [func]

    async def command_wrapper(self, func, *args, **kwargs):
        for b in self.before_command:
            if await b[0](*args, **kwargs) is False:
                return None

        result = await func(*args, **kwargs)

        for a in self.after_command:
            await a[0](result, *args, **kwargs)

        return result

    async def call_command(self, command, *args, **kwargs):
        commands_ = self.commands.get(command.command)

        result = False  # Флаг успешной обработки сообщения

        if command.has_prefix and command.command:  # Если есть смысл обработать команду
            for command_function in commands_:
                result = True if result else await self.command_wrapper(command_function, *args, **kwargs) is not False

        if not result and self.on_messages:  # Сообщение не обработано командами
            for func in self.on_messages:
                result = True if result else await self.command_wrapper(func, *args, **kwargs) is not False

        return result

    def init_variables(self, plugin_object: Plugin):
        plugin_object.process_pool = self.process_pool

    def init_plugin(self, plugin_object: Plugin):
        for func in plugin_object.init_funcs:
            if asyncio.iscoroutinefunction(func):
                loop = asyncio.get_event_loop()
                loop.run_until_complete(func(self.vk))

            else:
                func(self.vk)

    def register_plugin(self, plugin_object: Plugin):
        plugin_object.register(self)

    def register_commands(self):
        if not self.folder:
            raise ValueError("Plugin.folder can not be None")
        else:
            self._init_plugin_files()

    def _init_plugin_files(self):
        for folder_path, folder_names, filenames in os.walk(self.folder):
            for filename in filenames:
                if filename.endswith('.py') and filename != "__init__.py":
                    # path/to/plugins/plugin/foo.py
                    # > foo.py
                    # > foo
                    full_plugin_path = os.path.join(folder_path, filename)
                    base_plugin_path = os.path.relpath(full_plugin_path, self.folder)
                    base_plugin_name = os.path.splitext(base_plugin_path)[0].replace(os.path.sep, '.')

                    if base_plugin_name in settings.DISABLED_PLUGINS or \
                       ("all" not in settings.ENABLED_PLUGINS and base_plugin_name not in settings.ENABLED_PLUGINS):
                        continue

                    try:
                        loader = machinery.SourceFileLoader(base_plugin_name, full_plugin_path)
                        spec = util.spec_from_loader(loader.name, loader)
                        loaded_module = util.module_from_spec(spec)
                        loader.exec_module(loaded_module)

                    # Если при загрузке плагина произошла какая-либо ошибка
                    except Exception:
                        result = traceback.format_exc()
                        # если файла нет - создаём
                        if not isfile('log.txt'):
                            open('log.txt', 'w').close()

                        with open('log.txt', 'a') as log:
                            log.write(result)

                        hues.error(f"Ошибка при загрузке плагина: {filename}")
                        continue
                    try:
                        loaded_module.plugin.folder = full_plugin_path.replace(f"/{filename}", "")

                        self.plugins.add(loaded_module.plugin)
                        self.register_plugin(loaded_module.plugin)
                        self.init_variables(loaded_module.plugin)
                        self.init_plugin(loaded_module.plugin)

                    except AttributeError:  # Если возникла ошибка - значит плагин не имеет атрибута plugin
                        continue

    def __enter__(self):
        local_data.plugin_stacks = [self]
        return self

    def __exit__(self, exc_type, exc_value, tbc):
        try:
            local_data.plugin_stacks.pop()
        except Exception:
            pass
