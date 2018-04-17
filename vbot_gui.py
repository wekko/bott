import os
import re
import signal
import subprocess
import sys
import threading
from configparser import ConfigParser

from PyQt5 import Qt
from PyQt5 import QtGui
from PyQt5.QtCore import *
from PyQt5.QtGui import *
from PyQt5.QtWidgets import *


class PipeLogger(threading.Thread):
    def __init__(self, log):
        threading.Thread.__init__(self)

        self.daemon = False

        self.fdRead, self.fdWrite = os.pipe()
        self.pipeReader = os.fdopen(self.fdRead)

        self.log = log

        self.start()

    def fileno(self):
        return self.fdWrite

    def run(self):
        for line in iter(self.pipeReader.readline, ''):
            self.log.emit(line)

        self.pipeReader.close()

    def close(self):
        os.close(self.fdWrite)


class VBotGui(QWidget):
    logger = pyqtSignal(str)
    button_setup = pyqtSignal()

    bot_process = None

    width, height = 840, 620

    def __init__(self, parent=None):
        super(QWidget, self).__init__(parent)

        self.layout = QVBoxLayout(self)

        self.tabs = QTabWidget()

        self.tab1 = QScrollArea()
        self.tab1.setWidget(QWidget())
        self.tab1.setWidgetResizable(True)

        self.tab2 = QScrollArea()
        self.tab2.setWidget(QWidget())
        self.tab2.setWidgetResizable(True)

        self.tab3 = QScrollArea()
        self.tab3.setWidget(QWidget())
        self.tab3.setWidgetResizable(True)

        self.tabs.resize(self.width, self.height)

        self.tabs.addTab(self.tab1, "Бот")
        self.tabs.addTab(self.tab2, "Настройки")
        self.tabs.addTab(self.tab3, "Плагины")

        self.init_tab1()
        self.init_tab2()
        self.init_tab3()

        self.setGeometry(self.width, self.height, self.width, self.height)
        self.setWindowTitle('VBot')

        self.layout.addWidget(self.tabs)

    def start_bot(self, *args):
        if self.bot_process is not None:
            return

        pipe = PipeLogger(self.logger)

        bot_process = subprocess.Popen(['python3.6', "vbot.py", *args], stdout=pipe, stderr=pipe)

        self.bot_process = bot_process

        def look_after():
            with bot_process as s:
                pipe.close()

            self.button_setup.emit()
            self.bot_process = None

        try:
            self.button_setup.disconnect()
        except Exception:
            pass

        self.button_setup.connect(lambda: self.setup_bot_starter())

        t = threading.Thread(target=look_after)
        t.start()

        self.start_btn.disconnect()
        self.start_btn.setText("Остановить бота")
        self.start_btn.clicked.connect(lambda: self.stop_bot(bot_process))

    def setup_bot_starter(self):
        self.label.setText('Вход выполнен:')

        self.start_btn.disconnect()
        self.start_btn.setText("Запустить бота")
        self.start_btn.clicked.connect(lambda: self.start_bot("-nu"))

    @staticmethod
    def stop_bot(bot_process):
        bot_process.send_signal(signal.SIGINT)

    def init_tab1(self):
        layout = QGridLayout(self.tab1.widget())

        self.log_output = QTextEdit()
        self.log_output.setReadOnly(True)
        self.log_output.setLineWrapMode(QTextEdit.WidgetWidth)
        self.log_output.setStyleSheet("background-color: #535353; color: #e8e8e8")
        self.log_output.setFont(QFont("Comfortaa", 10))
        layout.addWidget(self.log_output, 0, 0, 1, 4)

        self.label = QLabel('Вход выполнен:')
        self.label.linkActivated.connect(self.link)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        layout.addWidget(self.label, 1, 3)

        layout.setRowMinimumHeight(1, self.height * 0.2)

        def log_text(s):
            def my_replace(match):
                """39 - белый
                36 - голубой
                31 - красный
                33 - жёлтый
                32 - зелёный
                35 - фиолетовый"""

                try:
                    value = int(match.group("value"))
                except:
                    value = 0

                if value == 31:
                    return "<span style='color: #f96565'>"

                if value == 32:
                    return "<span style='color: #00ed65'>"

                if value == 33:
                    return "<span style='color: #f9ed65'>"

                if value == 35:
                    return "<span style='color: #de61ed'>"

                if value == 36:
                    return "<span style='color: #65dbf9'>"

                if value == 39:
                    return "<span style='color: #e8e8e8'>"

                return "</span>"

            test_string = "Вошёл как: "
            if test_string in s:
                l = len(test_string)
                logged_info = re.sub(r'\[([0-9]+)m', "", s[s.index(test_string) + l:])
                logged_name = logged_info[:logged_info.index(" (")]
                logged_url = logged_info[logged_info.index(" (") + 2: -2]

                client = f"<a href='{logged_url}'>{logged_name}</a>"

                text = self.label.text()
                if client not in text:
                    self.label.setText(f"{text}<br>{client}")

            s = "<span>" + re.sub(r'\[(?P<value>[0-9]+)m', my_replace, s)

            self.log_output.moveCursor(QTextCursor.End)

            cursor = self.log_output.textCursor()
            cursor.insertHtml(s + "<br>")

        self.logger.connect(log_text)

        self.start_btn = QPushButton('Запустить бота')
        self.start_btn.clicked.connect(lambda: self.start_bot("-nu"))
        layout.addWidget(self.start_btn, 1, 0)

        self.update_btn = QPushButton('Обновить плагины')
        self.update_btn.clicked.connect(lambda: self.start_bot("-ou"))
        layout.addWidget(self.update_btn, 1, 1)

    def init_tab2(self):
        offset = 0

        self.values_2 = {}

        layout = QGridLayout(self.tab2.widget())

        import settings_template
        import settings

        for name in (v for v in dir(settings_template) if not v.startswith('__')):
            try:
                value = getattr(settings, name)
            except:
                value = ""

            template = getattr(settings_template, name)

            label = QLabel("<b>" + name + "</b><br>" + template[1])
            label.setAlignment(Qt.AlignLeft)
            label.setWordWrap(True)
            label.setMaximumWidth(self.width * 0.4)
            layout.addWidget(label, offset, 0)

            if template[0] in (bool, ):
                edit = QCheckBox()
                edit.setChecked(value)
                layout.addWidget(edit, offset, 1)

            elif template[0] in (str, int):
                if isinstance(value, (list, tuple)):
                    value = ";".join(value)

                edit = QLineEdit(str(value))
                edit.setAlignment(Qt.AlignLeft)
                layout.addWidget(edit, offset, 1)

            elif template[0] in (list, tuple):
                edit = QListWidget()
                edit.setSelectionMode(QAbstractItemView.ExtendedSelection)

                def add_item(edit, s):
                    i = QListWidgetItem(str(s))
                    i.setBackground(QColor("#fdc086"))
                    i.setFlags(Qt.ItemIsEditable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
                    edit.addItem(i)

                def del_items(edit):
                    items = edit.selectedItems()
                    if not items:
                        return

                    for item in items:
                        edit.takeItem(edit.row(item))

                def setup_button_add(btn, edit):
                    btn.clicked.connect(lambda: add_item(edit, ""))

                def setup_button_remove(btn, edit):
                    btn.clicked.connect(lambda: del_items(edit))

                for v in value:
                    if isinstance(v, (list, tuple)):
                        add_item(edit, ";".join(v))

                    else:
                        add_item(edit, v)

                layout.addWidget(edit, offset, 1)

                offset += 1

                btn = QPushButton('Добавить')
                setup_button_add(btn, edit)
                layout.addWidget(btn, offset, 1)

                offset += 1

                btn = QPushButton('Удалить')
                setup_button_remove(btn, edit)
                layout.addWidget(btn, offset, 1)

            self.values_2[name] = edit

            offset += 1

            drop = QLabel()
            drop.setMaximumHeight(1)
            drop.setStyleSheet("width: 100%; background-color: black;")
            layout.addWidget(drop, offset, 0, 1, 2)

            offset += 1

        def update_settings():
            SETTINGS = ""

            for k, v in self.values_2.items():
                if isinstance(v, QListWidget):
                    new_list = ""

                    for i in range(v.count()):
                        text = v.item(i).text()

                        if k == "USERS":
                            parts = (f"\"{p}\"" for p in text.split(";"))

                            text = f"({','.join(parts)},)"

                        elif not text.isdigit():
                            text = f"\"{text}\""

                        new_list += text + ","

                    SETTINGS += f"{k} = ({new_list})\n"

                elif isinstance(v, QLineEdit):
                    text = v.text()

                    if k == "DATABASE_SETTINGS":
                        parts = text.split(";")

                        text = "("

                        for p in parts:
                            if p.isdigit():
                                text += f"{p},"

                            else:
                                text += f"\"{p}\","

                            text += ")"

                    elif not text.isdigit():
                        text = f"\"{text}\""

                    SETTINGS += f"{k} = {text}\n"

                elif isinstance(v, QCheckBox):
                    SETTINGS += f"{k} = {v.isChecked()}\n"

            with open("settings.py", "w") as f:
                f.write(SETTINGS)

        btn = QPushButton('Сохранить')
        btn.setStyleSheet("font-size: 25px;")
        btn.clicked.connect(update_settings)
        layout.addWidget(btn, offset, 0, 2, 2)

    def init_tab3(self):
        self.values_3 = {}

        layout = self.tab3.widget().layout()

        if not layout:
            layout = QGridLayout(self.tab3.widget())

        else:
            for i in reversed(range(layout.count())):
                layout.itemAt(i).widget().setParent(None)

        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)

        offset = 0

        btn = QPushButton('Обновить настройки')
        btn.setStyleSheet("font-size: 25px;")
        btn.clicked.connect(self.init_tab3)
        layout.addWidget(btn, offset, 0)

        def save_plugin_settings():
            for k, v in self.values_3.items():
                config = ConfigParser()
                config.read(v[0])

                if isinstance(v[1], QCheckBox):
                    config.set("DEFAULT", k, str(v[1].isChecked()))

                elif isinstance(v[1], QLineEdit):
                    config.set("DEFAULT", k, v[1].text())

                with open(v[0], "w") as f:
                    config.write(f)

        btn = QPushButton('Сохранить')
        btn.setStyleSheet("font-size: 25px;")
        btn.clicked.connect(save_plugin_settings)
        layout.addWidget(btn, offset, 1)

        offset += 1

        for plugin in os.listdir("plugins"):
            if os.path.isfile(f"plugins/{plugin}"):
                continue

            with open(f"plugins/{plugin}/info.txt") as f:
                version, bot_version, name, description, authors = f.readlines()

                def my_replace(match):
                    name = match.group("name")
                    link = match.group("link")

                    return f"<a href='{link}'>{name}</a>"

                authors = [re.sub(r'(?P<name>.+) \((?P<link>.+)\)', my_replace, a) for a in authors.split(";")]

                label = QLabel(f"<b>{name}</b><br>Версия: {version}<br>{'; '.join(authors)}<br>{description}")
                label.setAlignment(Qt.AlignLeft)
                label.linkActivated.connect(self.link)
                label.setWordWrap(True)
                layout.addWidget(label, offset, 0, 1, 2)

                offset += 1

                ini_path = f"plugins/{plugin}/settings.ini"
                if os.path.exists(ini_path):
                    config = ConfigParser()
                    config.read(ini_path)

                    for n, v in config.items("DEFAULT"):
                        if n.endswith("_description") or n.endswith("_type"):
                            continue

                        item_description = config.get("DEFAULT", n + "_description")
                        item_type = config.get("DEFAULT", n + "_type")

                        label = QLabel(item_description)
                        label.setAlignment(Qt.AlignLeft)
                        label.setWordWrap(True)
                        layout.addWidget(label, offset, 0)

                        if item_type == "bool":
                            edit = QCheckBox()
                            edit.setChecked(v == "True")
                            layout.addWidget(edit, offset, 1)

                        else:
                            edit = QLineEdit(str(v))
                            edit.setAlignment(Qt.AlignCenter)
                            layout.addWidget(edit, offset, 1)

                        self.values_3[n] = ini_path, edit

                        offset += 1

            drop = QLabel()
            drop.setMaximumHeight(1)
            drop.setStyleSheet("width: 100%; background-color: black;")
            layout.addWidget(drop, offset, 0, 1, 2)

            offset += 1

    @staticmethod
    def link(link):
        QDesktopServices.openUrl(QUrl(link))


if __name__ == '__main__':
    app = QApplication(sys.argv)

    QtGui.QFontDatabase.addApplicationFont("base_font.ttf")

    ex = VBotGui()

    ex.show()

    result = app.exec_()

    if ex.bot_process:
        ex.stop_bot(ex.bot_process)

    sys.exit(result)
