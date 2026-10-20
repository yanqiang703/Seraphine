# coding: utf-8
"""对局计时悬浮窗。

对局进行中显示敌方 5 人的大招(R)与召唤师技能（闪现/点燃等）冷却，
点击技能图标开始倒计时，右键重置。数据来自 Live Client API 与 DDragon。
"""
import asyncio

from qasync import asyncSlot
from qframelesswindow.titlebar.title_bar_buttons import MaximizeButton
from PyQt5.QtCore import Qt, QTimer, pyqtSignal, QSize
from PyQt5.QtGui import QColor, QIcon, QPainter, QPen, QPixmap
from PyQt5.QtWidgets import (QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget, QInputDialog, QMessageBox)

from app.common.config import cfg
from app.common.logger import logger
from app.common.qfluentwidgets import (FluentIcon, FramelessWindow, TransparentToolButton)
from app.common.signals import signalBus
from app.components.champion_icon_widget import RoundIcon
from app.lol.connector import connector
from app.lol.live_client import liveClient

TAG = "TimerWindow"

ICON_SIZE = 40
POLL_INTERVAL = 2000  # 轮询间隔（毫秒）

# 对局进行中的 gameflow 阶段
INGAME_PHASES = ("GameStart", "InProgress")


class SkillTimerButton(QFrame):
    """技能图标 + 倒计时覆盖。左键开始冷却，右键重置。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(ICON_SIZE, ICON_SIZE)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("左键：开始倒计时\n右键：重置\n双击：编辑冷却秒数")

        self.image = None  # QPixmap
        self.cd = None     # 冷却秒数
        self._remaining = 0
        self._active = False

        self._timer = QTimer(self)
        self._timer.setInterval(1000)
        self._timer.timeout.connect(self._tick)

    def setIcon(self, path):
        self.image = QPixmap(path) if path else None
        self.update()

    def setCd(self, seconds):
        self.cd = int(seconds) if seconds and seconds > 0 else None

    def isActive(self):
        return self._active

    def start(self, seconds=None):
        if seconds is not None:
            self.setCd(seconds)
        if not self.cd or self.cd <= 0:
            return
        self._remaining = self.cd
        self._active = True
        self._timer.start()
        self.update()

    def reset(self):
        self._active = False
        self._remaining = 0
        self._timer.stop()
        self.update()

    def _tick(self):
        self._remaining -= 1
        if self._remaining <= 0:
            self.reset()
            return
        self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            if not self._active:
                self.start()
        elif event.button() == Qt.RightButton:
            if self._active:
                self.reset()
        return super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.editCd()
        return super().mouseDoubleClickEvent(event)

    def editCd(self):
        """双击弹出输入框，手动设置冷却秒数并开始倒计时。"""
        cur = self.cd or 0
        value, ok = QInputDialog.getInt(
            self, "编辑冷却", "冷却秒数（0 表示清除）:", cur, 0, 999, 1)
        if ok:
            if value <= 0:
                self.reset()
            else:
                self.start(value)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self.image and not self.image.isNull():
            img = self.image.scaled(
                self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(self.rect(), img)
        else:
            painter.fillRect(self.rect(), QColor(255, 255, 255, 12))

        # 边框
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRect(0, 0, self.width() - 1, self.height() - 1)

        if self._active:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 150))
            text = str(self._remaining)
            if self._remaining >= 60:
                m, s = divmod(self._remaining, 60)
                text = f"{m}:{s:02}"
            painter.setPen(QColor(255, 255, 255))
            font = painter.font()
            font.setPixelSize(15 if len(text) <= 2 else 12)
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(self.rect(), Qt.AlignCenter, text)

        return super().paintEvent(event)


class EnemyRow(QWidget):
    """一名敌方玩家：英雄头像 + 大招 + 召唤师技能×2。"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.championName = ""

        self.avatar = RoundIcon(None, ICON_SIZE, borderWidth=1, drawBackground=True)
        self.ultButton = SkillTimerButton()
        self.spellButtons = [SkillTimerButton(), SkillTimerButton()]

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(4, 4, 4, 4)

        self.rowLayout = QHBoxLayout()
        self.rowLayout.setSpacing(6)
        self.rowLayout.setContentsMargins(0, 0, 0, 0)

        self.nameLabel = QLabel("")
        self.nameLabel.setObjectName("timerChampName")
        self.nameLabel.setAlignment(Qt.AlignCenter)

        self.vBoxLayout.addWidget(self.nameLabel)
        self.vBoxLayout.addLayout(self.rowLayout)

        self.rowLayout.addWidget(self.avatar)
        self.rowLayout.addWidget(self.ultButton)
        for btn in self.spellButtons:
            self.rowLayout.addWidget(btn)


class TimerTitleBar(QFrame):
    """精简标题栏：标题 + 置顶 + 关闭，可拖动。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(36)

        self.titleLabel = QLabel("对局计时")
        self.titleLabel.setObjectName("TimerTitleLabel")

        self.helpButton = TransparentToolButton(FluentIcon.HELP)
        self.pinButton = TransparentToolButton(FluentIcon.PIN)
        self.closeButton = TransparentToolButton(FluentIcon.CLOSE)

        for btn in (self.helpButton, self.pinButton, self.closeButton):
            btn.setFixedSize(30, 30)

        self.helpButton.setToolTip("使用说明")

        self.pinButton.setCheckable(True)
        self.pinButton.setChecked(cfg.get(cfg.timerWindowOnTop))
        self.pinButton.setToolTip("窗口置顶")

        # FramelessWindow.nativeEvent 会访问 titleBar.maxBtn，给一个隐藏占位防 AttributeError
        self.maxBtn = MaximizeButton()
        self.maxBtn.setVisible(False)

        self.hBoxLayout = QHBoxLayout(self)
        self.hBoxLayout.setContentsMargins(10, 0, 4, 0)
        self.hBoxLayout.setSpacing(2)
        self.hBoxLayout.addWidget(self.titleLabel)
        self.hBoxLayout.addStretch(1)
        self.hBoxLayout.addWidget(self.helpButton)
        self.hBoxLayout.addWidget(self.pinButton)
        self.hBoxLayout.addWidget(self.closeButton)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            handle = self.window().windowHandle()
            if handle:
                handle.startSystemMove()
                return
        super().mousePressEvent(event)


class TimerWindow(FramelessWindow):
    """对局计时悬浮窗。"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._built = False
        self._polling = False
        self._enemyRows = []

        self.setTitleBar(TimerTitleBar(self))

        self.contentLabel = QLabel("等待对局开始…")
        self.contentLabel.setObjectName("TimerHintLabel")
        self.contentLabel.setAlignment(Qt.AlignCenter)

        self.enemiesWidget = QWidget()
        self.enemiesLayout = QVBoxLayout(self.enemiesWidget)
        self.enemiesLayout.setContentsMargins(2, 2, 2, 2)
        self.enemiesLayout.setSpacing(0)

        self.stackedOuter = QVBoxLayout(self)
        self.stackedOuter.setContentsMargins(0, 0, 0, 0)
        self.stackedOuter.setSpacing(0)
        self.stackedOuter.addWidget(self.titleBar)
        self.stackedOuter.addWidget(self.contentLabel)
        self.stackedOuter.addWidget(self.enemiesWidget)
        self.stackedOuter.addStretch(1)

        self.pollTimer = QTimer(self)
        self.pollTimer.setInterval(POLL_INTERVAL)
        self.pollTimer.timeout.connect(self.__onPoll)

        self.__initWindow()
        self.__connectSignalToSlot()

        # 诊断自检：启动后验证 DDragon 数据/图标下载，结果写入 ERROR 日志（无对局也可触发）
        QTimer.singleShot(4000, lambda: asyncio.create_task(self.__selfTest()))

    def __initWindow(self):
        self.setObjectName("timerWindow")
        self.setWindowTitle("对局计时")
        self.setWindowIcon(QIcon("app/resource/images/logo.png"))
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.resize(240, 60)

        if cfg.get(cfg.timerWindowOnTop):
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)

        self.setStyleSheet(
            """
            QLabel { background: transparent; }
            #TimerTitleLabel {
                color: #f2f2f2;
                font: 600 13px 'Microsoft YaHei', 'Segoe UI';
            }
            #TimerHintLabel {
                color: #9a9a9a;
                font: 13px 'Microsoft YaHei', 'Segoe UI';
                padding: 16px;
            }
            #timerChampName {
                color: #d7d7d7;
                font: 500 11px 'Microsoft YaHei', 'Segoe UI';
            }
            QToolButton {
                border-radius: 6px;
                background: transparent;
            }
            QToolButton:hover { background: rgba(255, 255, 255, 0.10); }
            QToolButton:checked { background: rgba(255, 255, 255, 0.18); }
            """
        )

    def __connectSignalToSlot(self):
        self.titleBar.closeButton.clicked.connect(self.hide)
        self.titleBar.pinButton.toggled.connect(self.__onPinToggled)
        self.titleBar.helpButton.clicked.connect(self.__showHelp)
        signalBus.gameStatusChanged.connect(self.__onGameStatusChanged)
        signalBus.lolClientEnded.connect(self.__onLolClientEnded)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(32, 32, 32, 180))
        painter.drawRect(self.rect())

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    # ------------------------------------------------------------------
    # 状态处理
    # ------------------------------------------------------------------
    @asyncSlot(str)
    async def __onGameStatusChanged(self, phase):
        if phase in INGAME_PHASES:
            if not cfg.get(cfg.enableTimerWindow):
                return
            if not self.isVisible():
                self.show()
                self.raise_()
            self.pollTimer.start()
            if not self._built:
                asyncio.create_task(self.__tryBuild())
        else:
            self.pollTimer.stop()

    @asyncSlot()
    async def __onLolClientEnded(self):
        self.pollTimer.stop()
        self.hide()
        self.__reset()

    def __onPoll(self):
        if not self.isVisible():
            return
        if self._polling:
            return
        if not self._built:
            asyncio.create_task(self.__tryBuild())

    async def __tryBuild(self):
        if self._built or self._polling:
            return
        self._polling = True
        try:
            await liveClient.ensure_data()
            enemies = await liveClient.fetch_enemy_players()
            if enemies:
                await self.__build(enemies)
        except Exception as e:
            logger.error(f"构建计时界面失败: {e}", TAG)
        finally:
            self._polling = False

    async def __selfTest(self):
        """诊断自检：验证 DDragon 数据与图标下载是否正常。"""
        try:
            await liveClient.ensure_data()
            logger.error(f"[SELFTEST] version={liveClient._version!r} "
                         f"summonerKeys={len(liveClient._summoner_data.get('data', {}))} "
                         f"championKeys={len(liveClient._champion_data.get('data', {}))}", TAG)
            for champ in ("Vex", "Ziggs"):
                key = liveClient._find_champion_key(champ)
                full = await liveClient._load_champion_full(champ)
                spells = (full.get("data") or {}).get(key or champ, {}).get("spells") or []
                icon = await liveClient.get_ultimate_icon(champ)
                logger.error(f"[SELFTEST] {champ}: key={key} spells={len(spells)} icon={icon}", TAG)
            for raw in ("SummonerFlash", "SummonerHeal"):
                sid = liveClient.get_summoner_id(raw)
                cd = liveClient.get_summoner_cd(raw)
                logger.error(f"[SELFTEST] {raw}: id={sid} cd={cd}", TAG)
        except Exception as e:
            logger.error(f"[SELFTEST] 异常: {e}", TAG)

    async def __build(self, enemies):
        # 已构建过则不再重建，保留进行中的倒计时
        if self._built:
            return

        self.contentLabel.hide()

        for enemy in enemies:
            row = EnemyRow()
            row.championName = enemy.champion_name
            row.nameLabel.setText(enemy.champion_name)

            # 英雄头像
            await self.__setAvatar(row, enemy.champion_name)

            # 大招（用 DDragon 英文 key 查询）
            ult_cd = await liveClient.get_ultimate_cd(enemy.champion_key)
            row.ultButton.setCd(ult_cd) if ult_cd else row.ultButton.setCd(0)
            ult_icon = await liveClient.get_ultimate_icon(enemy.champion_key)
            row.ultButton.setIcon(ult_icon)

            # 召唤师技能
            for i in range(2):
                if i < len(enemy.summoner_spells):
                    raw = enemy.summoner_spells[i]
                    cd = liveClient.get_summoner_cd(raw)
                    row.spellButtons[i].setCd(cd or 0)
                    row.spellButtons[i].setIcon(await self.__getSummonerIcon(raw))
                else:
                    row.spellButtons[i].setIcon(None)

            self.enemiesLayout.addWidget(row)
            self._enemyRows.append(row)

        self._built = True
        self.__adjustSize()

    async def __setAvatar(self, row: EnemyRow, champion_name: str):
        try:
            champion_id = connector.manager.getChampionIdByName(champion_name)
            path = await connector.getChampionIcon(champion_id)
            row.avatar.setIcon(path)
        except Exception:
            row.avatar.setIcon("app/resource/images/champion-0.png")

    async def __getSummonerIcon(self, raw_name: str) -> str:
        """召唤师技能图标：优先走 LCU 本地缓存，失败再回退 DDragon。"""
        spell_id = liveClient.get_summoner_id(raw_name)
        if spell_id is not None:
            try:
                return await connector.getSummonerSpellIcon(spell_id)
            except Exception:
                pass
        return await liveClient.get_summoner_icon(raw_name)

    def __adjustSize(self):
        count = max(len(self._enemyRows), 1)
        height = self.titleBar.height() + count * (ICON_SIZE + 36)
        self.resize(240, height)

    def __reset(self):
        self._built = False
        self._polling = False
        for row in self._enemyRows:
            row.setParent(None)
            row.deleteLater()
        self._enemyRows = []
        self.contentLabel.setText("等待对局开始…")
        self.contentLabel.show()
        self.resize(240, 60)

    # ------------------------------------------------------------------
    # 置顶
    # ------------------------------------------------------------------
    def __onPinToggled(self, checked):
        cfg.set(cfg.timerWindowOnTop, checked)
        if checked:
            self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowStaysOnTopHint)
        self.show()
        self.raise_()
        self.activateWindow()

    def showWindow(self):
        self.show()
        self.raise_()
        self.activateWindow()

    def __showHelp(self):
        QMessageBox.information(
            self, "对局计时 · 使用说明",
            "· 左键点击技能图标：开始冷却倒计时\n"
            "· 右键点击技能图标：重置（取消倒计时）\n"
            "· 双击技能图标：手动编辑冷却秒数（填 0 清除）\n"
            "· 图钉按钮：窗口置顶\n"
            "· × 按钮：隐藏窗口\n\n"
            "说明：\n"
            "敌方英雄与召唤师技能在对局中自动识别显示。\n"
            "冷却时长取自官方数据（满级大招 / 召唤师技能基础值）。\n"
            "倒计时为本地计时，从点击图标那一刻开始，不读取游戏内实时冷却。")