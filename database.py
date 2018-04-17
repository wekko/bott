import time

import hues
import peewee
import peewee_async

try:
    from settings import DATABASE_SETTINGS, DATABASE_DRIVER, DATABASE_CHARSET
    s = True

except:
    DATABASE_SETTINGS, DATABASE_DRIVER, DATABASE_CHARSET = (), None, "utf8mb4"
    s = False

_additional_values = {}
if DATABASE_DRIVER == "mysql":
    driver = peewee_async.MySQLDatabase
    _additional_values['charset'] = DATABASE_CHARSET
elif DATABASE_DRIVER == "postgresql":
    driver = peewee_async.PostgresqlDatabase
else:
    driver = None

if len(DATABASE_SETTINGS) == 0:
    database = False
elif len(DATABASE_SETTINGS) == 1:
    _name, = DATABASE_SETTINGS
    database = driver(_name)
else:
    _name, _host, _port, _user, _password = DATABASE_SETTINGS
    _port = int(_port)
    database = driver(_name,
                      host=_host,
                      port=_port,
                      user=_user,
                      password=_password,
                      **_additional_values)


async def get_or_none(model, *args, **kwargs):
    try:
        return await db.get(model, *args, **kwargs)

    except peewee.DoesNotExist:
        return None

async def set_up_roles(bot):
    from settings import BLACKLIST, WHITELIST, ADMINS

    if WHITELIST:
        bot.WHITELISTED = True

    for u in WHITELIST:
        await db.get_or_create(Role, user_id=u, role="whitelisted")

    for u in BLACKLIST:
        await db.get_or_create(Role, user_id=u, role="blacklisted")

    for u in ADMINS:
        await db.get_or_create(Role, user_id=u, role="admin")

    await check_white_list(bot)


async def check_white_list(bot):
    if await db.count(Role.select().where(Role.role == "whitelisted")) > 0:
        bot.WHITELISTED = True

    else:
        bot.WHITELISTED = False


#############################################################################################
class BaseModel(peewee.Model):
    class Meta:
        database = database


class Role(BaseModel):
    user_id = peewee.BigIntegerField()
    role = peewee.TextField()


class User(BaseModel):
    user_id = peewee.BigIntegerField(primary_key=True, unique=True)
    message_date = peewee.BigIntegerField(default=0)
    in_group = peewee.BooleanField(default=False)

    status = peewee.TextField(default="")
    status_locked_message = peewee.TextField(default="")

    chatter_id = peewee.TextField(null=True)
    chat_data = peewee.TextField(default="")


class Status(BaseModel):
    user_id = peewee.BigIntegerField()
    plugin_id = peewee.TextField()

    value = peewee.BigIntegerField()


class BotStatus(BaseModel):
    photos = peewee.IntegerField(default=0)
    timestamp = peewee.IntegerField(default=time.time)


if database:
    db = peewee_async.Manager(database)

    User.create_table(True)
    BotStatus.create_table(True)
    Role.create_table(True)
    Status.create_table(True)

elif s:
    hues.error("Не удалось создать базу данных! Проверьте настройки и попробуйте снова!")