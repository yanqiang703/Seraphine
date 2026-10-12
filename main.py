# coding:utf-8
import ctypes
import os
os.chdir(os.path.dirname(os.path.abspath(__file__)))

from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QTranslator
from PyQt5.QtWidgets import QMessageBox
from app.common.qfluentwidgets import FluentTranslator
from qasync import QApplication, QEventLoop
import asyncio
import sys
from app.common.config import cfg, VERSION, BETA
from app.view.main_window import MainWindow
from qfluentwidgets import setTheme, Theme

# 单实例互斥锁，必须保持引用直到进程退出
singleInstanceMutex = None


def main():
    args = sys.argv
    if len(args) == 2 and args[1] in ['--version', '-v']:
        print(BETA or VERSION)
        return

    global singleInstanceMutex
    singleInstanceMutex = ctypes.windll.kernel32.CreateMutexW(
        None, False, "Seraphine-SingleInstance-Mutex")
    alreadyRunning = ctypes.windll.kernel32.GetLastError() == 183  # ERROR_ALREADY_EXISTS

    if cfg.get(cfg.dpiScale) == "Auto":
        QApplication.setHighDpiScaleFactorRoundingPolicy(
            Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
        QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    else:
        os.environ["QT_ENABLE_HIGHDPI_SCALING"] = "0"
        os.environ["QT_SCALE_FACTOR"] = str(cfg.get(cfg.dpiScale))
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    font = QFont()
    font.setStyleStrategy(QFont.PreferAntialias)
    font.setHintingPreference(QFont.PreferFullHinting)
    QApplication.setFont(font)

    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

    if alreadyRunning:
        QMessageBox.warning(None, "Seraphine", "Seraphine 已经在运行中，请勿重复启动。")
        sys.exit(0)

    # 默认深色主题
    if cfg.get(cfg.themeMode) == Theme.LIGHT:
        cfg.set(cfg.themeMode, Theme.DARK)
    setTheme(cfg.get(cfg.themeMode))

    eventLoop = QEventLoop(app)
    asyncio.set_event_loop(eventLoop)

    appCloseEvent = asyncio.Event()
    app.aboutToQuit.connect(appCloseEvent.set)

    locale = cfg.get(cfg.language).value
    fluentTranslator = FluentTranslator(locale)
    seraphineTranslator = QTranslator()
    seraphineTranslator.load(locale, "Seraphine", ".", "./app/resource/i18n")

    app.installTranslator(fluentTranslator)
    app.installTranslator(seraphineTranslator)

    w = MainWindow()
    w.show()

    eventLoop.run_until_complete(appCloseEvent.wait())
    eventLoop.close()


if __name__ == '__main__':
    main()
