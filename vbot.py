import logging
import shutil
import sys
from os.path import abspath, isfile

import requests


def check_settings():
    """Создаём файл настроек, если надо и загружаем бота, если всё хорошо."""
    # Если нет файла настроек
    if (isfile('settings.py.sample') or isfile('settings.py.sample.ru')) and not isfile('settings.py'):
        try:
            if isfile('settings.py.sample.ru'):
                shutil.copy('settings.py.sample', 'settings.py')
            else:
                shutil.copy('settings.py.sample', 'settings.py')
        except Exception:
            fatal('Я не могу копировать файлы в текущей папке, '
                  'проверьте ваши права на неё!')
        hues.info('Был создан файл settings.py, '
                  'не забудьте добавить данные для авторизации!')

        exit()
    # Если у нас уже есть settings.py
    elif isfile('settings.py'):
        import settings
        try:
            v = settings.WHITELIST_MESSAGE
            v = settings.BLACKLIST_MESSAGE

            v = settings.PREFIXES

            v = settings.LOG_MESSAGES
            v = settings.LOG_COMMANDS

            v = settings.APP_ID
            v = settings.SCOPE

            v = settings.FLOOD_INTERVAL

            v = settings.USERS
            v = settings.PROXIES

            v = settings.CHAT_ENABLE
            v = settings.CHAT_ONLY
            v = settings.CHAT_CHATTER
            v = settings.CHAT_IGNORE_PREFIX

            v = settings.GROUP_ID
            v = settings.READ_OUT

            v = settings.ADMINS
            v = settings.BLACKLIST
            v = settings.WHITELIST

            v = settings.REQUEST_INTERVAL
            v = settings.REQUESTS_QUANTITY

            settings.ENABLED_PLUGINS += ("default_utils",)
            settings.DISABLED_PLUGINS = [p for p in settings.DISABLED_PLUGINS if p != "default_utils"]

            if not settings.USERS:
                hues.error("Проверьте, что у есть LOGIN и PASSWORD, или же TOKEN в файле settings.py!"
                           "Без них бот работать НЕ СМОЖЕТ.")
                exit()

        except (ValueError, AttributeError, NameError):
            hues.error('Проверьте содержимое файла settings.py, возможно вы удалили что-то нужное!')
            exit()
    # Если не нашли ни settings.py, ни settings.py.sample
    else:
        hues.error("settings.py и settings.py.sample не найдены, возможно вы их удалили?")
        exit()


check_settings()

from utils import *
from chat.chatter import normalize, ChatterBot
from command import Command
from plugin_system import PluginSystem
from vkplus import *


class Bot(object):
    """Bot object"""
    __slots__ = ["WHITELISTED",
                 "messages_date", "plugin_system", "cmd_system",
                 "last_ts", "scheduled_funcs", "longpoll_server", "longpoll_key",
                 "chatter", "longpoll_values", "event_loop", "last_message_id", "vk"]

    def __init__(self):
        self.WHITELISTED = False

        self.longpoll_values = {}
        self.longpoll_server = ""
        self.longpoll_key = ""
        self.last_ts = 0

        self.vk_init()

        if sys.argv and "-nu" in sys.argv:
            self.plugin_download(f"https://vkbots.github.io/vbot-plugins")
            self.plugin_clear()

            if sys.argv and "-ou" in sys.argv:
                hues.success("Плагины обновлены")
                exit()

        self.plugin_init()

        if settings.CHAT_ENABLE:
            if settings.CHAT_CHATTER:
                self.chatter = ChatterBot()
            else:
                from chat.chat import chatter
                self.chatter = chatter

    def vk_init(self):
        hues.warn("Авторизация в ВКонтакте...")

        self.messages_date = {}  # Словарь вида ID -> время

        self.vk = VkPlus(users_data=settings.USERS,
                         proxies=settings.PROXIES,
                         bot=self,
                         scope=settings.SCOPE,
                         app_id=settings.APP_ID)
        if self.vk:
            hues.success("Успешная авторизация")

    @staticmethod
    def plugin_clear():
        hues.info("Удаление лишних плагинов...")

        for file in os.listdir("plugins"):
            if (file not in settings.ENABLED_PLUGINS and "all" not in settings.ENABLED_PLUGINS) or \
                    file in settings.DISABLED_PLUGINS:
                shutil.rmtree(f"plugins/{file}")

    @staticmethod
    def plugin_download(repository_url):
        if not os.path.exists("plugins"):
            os.mkdir("plugins")

        hues.info("Обновление и загрузка плагинов...")

        base = repository_url

        for i in requests.get(f"{base}/dir").text.splitlines():
            file_type, file_name = i.split(";")

            plugin_name = file_name

            if file_type == "dir":
                if ("all" in settings.ENABLED_PLUGINS or file_name in settings.ENABLED_PLUGINS) and \
                                file_name not in settings.DISABLED_PLUGINS:
                    plugin_folder = f"{base}/{file_name}"

                    info = requests.get(f"{plugin_folder}/info.txt").text.strip().splitlines()

                    version, bot_version, name, description, authors = info
                    bot_version = bot_version.split(";")

                    if VERSION not in bot_version:
                        old_version_n = 0

                        while True:
                            p_plugin_folder = f"{plugin_folder}/old{old_version_n}"
                            response = requests.get(f"{p_plugin_folder}/info.txt")

                            if response.status_code == 404:
                                plugin_folder = ""
                                hues.warn(f"Для плагина {plugin_name} необходим бот "
                                          f"версии (одной из): {', '.join(bot_version)}")

                                break

                            version, bot_version, *other = response.text.splitlines()

                            if VERSION not in bot_version:
                                old_version_n += 1
                                continue

                            plugin_folder = p_plugin_folder
                            break

                    if plugin_folder:
                        if os.path.exists(f"plugins/{plugin_name}/info.txt"):
                            with open(f"plugins/{plugin_name}/info.txt") as f:
                                v, bv, n, d, a = f.read().strip().splitlines()

                                if v != version:
                                    hues.warn(f"Обновление плагина {plugin_name} с версии {v} до {version}")
                                    shutil.rmtree(f"plugins/{plugin_name}/")

                                else:
                                    continue

                        else:
                            hues.warn(f"Загрузка плагина {plugin_name} версии {version}")

                        for j in requests.get(f"{plugin_folder}/dir").text.splitlines():
                            file_type, file_name = j.split(";")

                            if file_type == "dir" and file_name.startswith("old"):
                                continue

                            if not os.path.exists(f"plugins/{plugin_name}"):
                                os.mkdir(f"plugins/{plugin_name}")

                            with open(f"plugins/{plugin_name}/{file_name}", "wb") as f:
                                f.write(requests.get(f"{plugin_folder}/{file_name}").content)

    def plugin_init(self):
        hues.info("Активация плагинов...")

        # Загружаем плагины
        self.plugin_system = PluginSystem(self.vk, folder=abspath('plugins'))
        self.plugin_system.register_commands()
        self.vk.get_plugins = self.plugin_system.get_plugins

        # Для парсинга команд с пробелом используется
        # обратная сортировка, для того, чтобы самые
        # длинные команды были первыми в списке
        command_names = list(self.plugin_system.commands.keys())
        command_names.sort(key=len, reverse=True)

        from command import CommandSystem

        self.cmd_system = CommandSystem(command_names,
                                        self.plugin_system)
        self.scheduled_funcs = self.plugin_system.scheduled_events

        hues.success("Загрузка плагинов завершена")

    @staticmethod
    async def get_long_poll_server(retries: int, vk: VkPlus) -> dict:
        result = ""

        for x in range(retries):
            result = await vk.method('messages.getLongPollServer', {'use_ssl': 1})

            if result:
                break

            time.sleep(1)

        return result

    async def init_long_polling(self, update: int=0):
        """Функция для инициализации Long Polling"""

        result = await self.get_long_poll_server(10, self.vk)

        if not result:
            time.sleep(30)

            result = await self.get_long_poll_server(10, self.vk)

            if not result:
                fatal("Не удалось получить значения Long Poll сервера!")

        try:
            self.last_ts = self.longpoll_values['ts']
            self.longpoll_key = self.longpoll_values['key']
        except (AttributeError, ValueError, KeyError):
            pass

        if update == 0:
            # Если нам нужно инициализировать с нуля, меняем сервер
            self.longpoll_server = "https://" + result['server']

        if update in (0, 3):
            # Если нам нужно инициализировать с нуля, или ошибка 3
            self.longpoll_key = result['key']
            self.last_ts = result['ts']  # Последний timestamp

        elif update == 2:
            # Если ошибка 2 - то нужен новый ключ
            self.longpoll_key = result['key']

        self.longpoll_values = {
            'act': 'a_check',
            'key': self.longpoll_key,
            'ts': self.last_ts,
            'wait': 25,  # Тайм-аут запроса
            'mode': 10,
            'version': 1
        }

    async def check_event(self, new_event: List):
        if not new_event:
            return

        event_id = new_event.pop(0)

        if event_id != 4:  # Если событие - не новое сообщение
            return

        msg_id, flags, peer_id, ts, subject, text, attaches = new_event

        # Получаем параметры сообщения
        # https://vk.com/dev/using_longpoll_2
        flags = parse_msg_flags(flags)

        # Если сообщение - исходящее
        if flags['outbox'] and not settings.READ_OUT:
            return

        # Тип сообщения - конференция или ЛС
        try:  # Пробуем получить ID пользователя, который отправил сообщение в беседе
            user_id = attaches['from']
            peer_id -= 2000000000
            conf = True

        except KeyError:  # Если ключа from нет - это ЛС
            user_id = peer_id
            conf = False

        user_id = int(user_id)

        # Если ID находится в чёрном списке
        if await get_or_none(Role, user_id=user_id, role="blacklisted") or \
                await get_or_none(Role, user_id=peer_id, role="blacklisted"):
            if settings.BLACKLIST_MESSAGE:
                await self.vk.method("messages.send", {"user_id": peer_id, "message": settings.BLACKLIST_MESSAGE})

            return

        # Если ID моет писать боту или белый список отключён
        if self.WHITELISTED and not await get_or_none(Role, user_id=peer_id, role="whitelisted"):
            if settings.WHITELIST_MESSAGE:
                await self.vk.method("messages.send", {"user_id": peer_id, "message": settings.WHITELIST_MESSAGE})

            return

        cleaned_body = text.replace('<br>', '\n')

        forwarded = []
        if "fwd" in attaches:
            forwarded = self.parse_forwarded_messages(attaches["fwd"])

            del attaches['fwd']

        data = MessageEventData(conf, peer_id, user_id, cleaned_body, ts, msg_id, flags['outbox'], attaches, forwarded)

        user = await get_or_none(User, user_id=user_id)
        if user:
            if not flags['outbox']:
                if ts - user.message_date <= settings.FLOOD_INTERVAL:
                    user.message_date = ts
                    await db.update(user)
                    return

                user.message_date = ts

                await db.update(user)

        else:
            user = await db.create(User, user_id=user_id)

        # Обработка команды
        await self.check_if_command(data, user)

    async def do_chat(self, msg: Message, user: User):
        if not settings.CHAT_ENABLE:
            return

        if user.chat_data:
            chat_data = json.loads(user.chat_data)
            chat_data.append(normalize(msg.text))
            chat_data = chat_data[::-1]
        else:
            chat_data = [normalize(msg.text)]

        answer = await self.chatter.parse_message(user, chat_data)

        if answer is not None:
            chat_data = chat_data[::-1]
            chat_data.append(normalize(answer))

            user.chat_data = json.dumps(chat_data)

            await db.update(user)

            await msg.answer(answer)

    def parse_forwarded_messages(self, forwarded: str) -> List:
        result = []

        msgs = forwarded.split(",")

        for i in range(len(msgs)):
            sep_pos = msgs[i].find(":")

            if sep_pos == -1:
                result.append((msgs[i].replace(")", ""), []))

            else:
                result.append((msgs[i][:sep_pos], self.parse_forwarded_messages(msgs[i][sep_pos + 2:-1])))

        return result

    async def check_if_command(self, data: MessageEventData, user: User) -> None:
        if settings.LOG_MESSAGES:
            who = f"{'конференции' if data.conf else 'ЛС'} {data.peer_id}"
            hues.info(f"Сообщение из {who} > {data.body}")

        msg_obj = await create_message(self.vk, data, user)

        if not settings.CHAT_ONLY or not settings.CHAT_ENABLE:
            messages_to_check = [msg_obj]
            done = False

            if settings.CHECK_FORWARDED_MESSAGES:
                for msg in traverse(await msg_obj.full_forwarded):
                    if msg is None:
                        continue

                    messages_to_check.append(msg)

            for msg in messages_to_check:
                cmd = Command(msg)
                result = await self.cmd_system.process_command(msg, cmd)

                done = True if done else result

                if result and not settings.CHECK_FORWARDED_MESSAGES_ALL:
                    break

            if done:
                return

        if settings.CHAT_ENABLE and (settings.CHAT_IGNORE_PREFIX or msg_obj.prefix):
            await self.do_chat(msg_obj, user)

    async def run(self, event_loop: asyncio.AbstractEventLoop) -> None:
        """Главная функция бота - тут происходит ожидание новых событий (сообщений)"""
        self.event_loop = event_loop  # Нужен для шедулинга функций

        await self.init_long_polling()

        with aiohttp.ClientSession(loop=event_loop) as session:
            while True:
                try:
                    resp = await session.get(self.longpoll_server,
                                             params=self.longpoll_values)
                except (aiohttp.ClientOSError, asyncio.TimeoutError):
                    hues.warn('Сервер Long Polling не отвечает, подключаюсь к другому...')
                    await self.init_long_polling()
                    continue

                events_text = await resp.text()  # text(), а не json() из-за плохого mimetype у вк

                try:
                    events = json.loads(events_text)
                except ValueError:
                    continue

                failed = events.get('failed')
                if failed:
                    err_num = int(failed)

                    if err_num == 1:  # Код 1 - Нам нужно обновить timestamp
                        self.longpoll_values['ts'] = events['ts']

                    elif err_num in (2, 3):  # Коды 2 и 3 - нужно запросить данные нового Long Polling сервера
                        await self.init_long_polling(err_num)

                    continue

                # Обновление времени, чтобы не приходили старые события
                self.longpoll_values['ts'] = events['ts']

                # Обработка сообщений
                for event in events['updates']:
                    schedule_coroutine(self.check_event(event))

VERSION = "6.0"

if __name__ == '__main__':
    hues.info("Приступаю к запуску VBot " + VERSION)

    bot = Bot()

    main_loop = asyncio.get_event_loop()
    main_loop.run_until_complete(set_up_roles(bot))

    hues.success("Приступаю к приему сообщений")

    try:
        main_loop.run_until_complete(bot.run(main_loop))
    except (KeyboardInterrupt, SystemExit):
        hues.warn("Бот выключен!")

    except Exception as ex:
        import traceback

        logging.warning("Fatal error:\n")
        traceback.print_exc()
