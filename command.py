import traceback

import hues

from plugin_system import PluginSystem
from vkplus import Message

try:
    import settings
except ImportError:
    pass


class Command(object):
    __slots__ = ('has_prefix', 'text', 'bot',
                 'command', 'args', "msg")

    def __init__(self, msg: Message):
        self.has_prefix = True  # переменная для обозначения, есть ли у команды префикс
        self.msg = msg
        self.text = msg.body
        self._get_prefix()
        self.command = ""
        self.args = []

        if self.has_prefix:
            msg.prefix = True

        else:
            msg.prefix = False

    def check_command(self, command_system):
        text = self.text.lower()

        if self.has_prefix:
            for command in command_system.commands:
                if text.startswith(command + " ") or text == command or text.startswith(command + "\n"):
                    self.command = command
                    self.msg.command = command
                    self.msg.text = self.text[len(command):]
                    self.args = self.msg.text.split()
                    return True

        if command_system.on_messages:
            self.args = self.text.split()
            self.msg.text = self.text
            return True

        return False

    def log(self):
        """Отправка сообщения в лог о том, что была распознана команда"""

        pid = self.msg.peer_id
        who = ("конференции {}" if self.msg.conf else "ЛС {}").format(pid)
        hues.info(f"Команда '{self.command}' из {who} с аргументами {self.args}")

    def _get_prefix(self):
        """Попытка получить префикс из текста команды"""

        for prefix in settings.PREFIXES:
            # Если команда начинается с префикса
            if self.text.startswith(prefix):
                # Убираем префикс из текста
                self.text = self.text.replace(prefix, '', 1).lstrip()
                self.msg.text = self.text
                break

        else:
            self.has_prefix = False


class CommandSystem(object):
    def __init__(self, commands, plugin_system: PluginSystem):
        # Система плагинов
        self.system = plugin_system

        # self.commands - список с командами
        self.commands = commands
        self.on_messages = bool(plugin_system.on_messages)

    async def process_command(self, msg_obj: Message, cmd: Command):
        """Обрабатка команды"""

        if not cmd.check_command(self):
            return False

        if cmd.has_prefix and settings.LOG_COMMANDS:
            cmd.log()

        try:
            return await self.system.call_command(cmd, msg_obj, cmd.args)

        except Exception as e:  # Если в плагине произошла какая-то ошибка
            code = msg_obj.vk.anti_flood()

            await msg_obj.answer(f"{code}.\n"
                                 f"Произошла ошибка при выполнении команды <{cmd.command}> "
                                 "пожалуйста, сообщите об этом разработчику!")

            hues.error(
                f"{code}.\n"
                f"Произошла ошибка при вызове команды '{cmd.command}' с аргументами {cmd.args}.\n"
                f"Текст сообщения: '{cmd.text}'.\n"
                f"Ошибка:\n{traceback.format_exc()}")

            return True
