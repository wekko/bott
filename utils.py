# Various helpers
import asyncio
import datetime
import html
import os
from configparser import ConfigParser
from enum import Enum
from typing import Iterator, Coroutine, Iterable

import hues
from dateutil.relativedelta import relativedelta

from plugin_system import Plugin


class SenderGroup:
    USER = False
    GROUP = True

    __slots__ = ('target',)

    def __init__(self, target):
        self.target = target


class SenderUser:
    USER = True
    GROUP = False

    __slots__ = ('target', )

    def __init__(self, target):
        self.target = target


class Wait(Enum):
    NO = 0
    YES = 1
    CUSTOM = 2


class Attachment(object):
    __slots__ = ('type', 'owner_id', 'id', 'access_key', 'url')

    def __init__(self, attach_type: str, owner_id: int, aid: int, access_key: str, url: str):
        self.type = attach_type
        self.owner_id = owner_id
        self.id = aid
        self.access_key = access_key
        self.url = url

    @staticmethod
    def from_raw(raw_attach):
        a_type = raw_attach['type']  # Тип аттача
        attach = raw_attach[a_type]  # Получаем сам аттач

        # Ищём ссылку на фото
        url = ""
        for k, v in attach.items():
            if "photo_" in k:
                url = v

        key = attach.get('access_key')  # Получаем access_key для аттача

        return Attachment(a_type, attach['owner_id'], attach['id'], key, url)

    def as_str(self):
        """Возвращает приложение в формате ownerid_id_accesskey"""
        if self.access_key:
            return f'{self.owner_id}_{self.id}_{self.access_key}'

        return f'{self.owner_id}_{self.id}'

    def __repr__(self):
        return f'{self.type}{self.as_str()}'


class RequestFuture(asyncio.Future):
    __slots__ = ["key", "data", "send_from"]

    def __init__(self, key, data, send_from=None):
        self.key = key
        self.data = data
        self.send_from = send_from

        super().__init__()


def schedule_coroutine(target: Coroutine):
    """Schedules target coroutine in the given event loop
    If not given, *loop* defaults to the current thread's event loop
    Returns the scheduled task.
    """
    if asyncio.iscoroutine(target):
        return asyncio.ensure_future(target, loop=asyncio.get_event_loop())
    else:
        raise TypeError("target must be a coroutine, "
                        "not {!r}".format(type(target)))


# http://stackoverflow.com/questions/312443/how-do-you-split-a-list-into-evenly-sized-chunks
def chunks(l: Iterable, n: int):
    """Yield successive n-sized chunks from l."""
    for i in range(0, len(l), n):
        yield l[i:i + n]


tree_types = (list, tuple)


def traverse(o) -> Iterator:
    if isinstance(o, tree_types):
        for value in o:
            for subvalue in traverse(value):
                yield subvalue
    else:
        yield o


def fatal(*args):
    """Отправляет args в hues.error() и выходит"""
    hues.error(*args)
    exit()


cases = (2, 0, 1, 1, 1, 2)


def plural_form(n: int, v: (list, tuple)):
    """Функция возвращает число и просклонённое слово после него

    Аргументы:
    :param n: число
    :param v: варианты слова в формате (для 1, для 2, для 5)

    Пример:
    plural_form(difference.days, ("день", "дня", "дней"))

    :return: Число и просклонённое слово после него
    """

    return f"{n}  {v[2 if (4 < n % 100 < 20) else cases[min(n % 10, 5)]]}"


def load_settings(plugin: Plugin):
    """Функция возвращает словарь с настройками из файла настроек "settings.ini" плагина plugin.

    Аргументы:
    :param plugin: плагин, чьи настройки надо получить

    :return: словарь с настройками
    """

    values = {}

    file = f"{plugin.folder}/settings.ini"

    if not os.path.exists(file):
        return values

    config = ConfigParser()
    config.read(file)

    for n, v in config.items("DEFAULT"):
        if v in ("True", "False"):
            values[n] = (v == "True")
        else:
            values[n] = v

    return values


def age(date: datetime.datetime):
    """Возвращает возраст в годах по дате рождения

    Функция
    :param date: дата рождения
    :return: возраст
    """

    # Get the current date
    now = datetime.datetime.utcnow()
    now = now.date()

    # Get the difference between the current date and the birthday
    age = relativedelta(now, date)
    age = age.years

    return age


keys = [
    'unread',
    'outbox',
    'replied',
    'important',
    'chat',
    'friends',
    'spam',
    'deleted',
    'fixed',
    'media'
]


def parse_msg_flags(bitmask: int) -> dict:
    """Функция для чтения битовой маски и возврата словаря значений"""

    start = 1
    values = []
    for x in range(1, 11):
        result = bitmask & start
        start *= 2
        values.append(bool(result))
    return dict(zip(keys, values))


def unquote(data: (str, dict, list)):
    """Функция, раскодирующая ответ от ВК

    :param data: строка для раскодировки
    :return: раскодированный ответ
    """

    temp = data

    if issubclass(temp.__class__, str):
        return html.unescape(html.unescape(temp))

    if issubclass(temp.__class__, dict):
        for k, v in temp.items():
            temp[k] = unquote(v)

    if issubclass(temp.__class__, list):
        for i in range(len(temp)):
            temp[i] = unquote(temp[i])

    return temp
