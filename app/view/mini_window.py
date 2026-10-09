import asyncio
import time

from qasync import asyncSlot
from qframelesswindow.titlebar.title_bar_buttons import MinimizeButton
from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import (QFrame, QGraphicsOpacityEffect, QGridLayout,
                             QHBoxLayout, QLabel, QStackedWidget, QVBoxLayout,
                             QWidget, QApplication)
from qfluentwidgets import SwitchButton, SpinBox

from app.common.config import cfg
from app.common.logger import logger
from app.common.qfluentwidgets import (FramelessWindow, FluentIcon,
                                       PrimaryPushButton, PushButton,
                                       TransparentToolButton)
from app.common.signals import signalBus
from app.components.champion_icon_widget import RoundIcon
from app.lol.connector import connector

TAG = 'MiniWindow'

PLACEHOLDER_PAGE = 0
LOUNGE_PAGE = 1
CHAMP_SELECT_PAGE = 2

PLACEHOLDER_PHASES = (
    None, 'None', 'EndOfGame', 'PreEndOfGame', 'WatchInProgress',
    'GameStart', 'InProgress', 'WaitingForStats', 'WaitingForStatus',
    'Reconnect'
)
LOUNGE_PHASES = ('Lobby', 'Matchmaking', 'ReadyCheck')

CHAMP_PHASE_TEXT = {
    'PLANNING': "备战阶段",
    'BAN_PICK': "禁用 / 选择阶段",
    'FINALIZATION': "最终确认",
}

POSITION_TEXT = {
    'top': "上路",
    'jungle': "打野",
    'middle': "中路",
    'bottom': "下路",
    'utility': "辅助",
}


class BenchChampionCell(QFrame):
    """ 备战席单个英雄格子：方形可点击图标 """
    clicked = pyqtSignal(int)

    def __init__(self, championId=0, parent=None):
        super().__init__(parent)
        self.championId = championId
        self.image = None
        self.isHover = False
        self.isPressed = False
        self._enabled = True
        self.setFixedSize(38, 38)

    def setChampion(self, championId, iconPath=None):
        self.championId = championId
        if iconPath:
            self.image = QPixmap(iconPath)
        else:
            self.image = None
        self.update()

    def setCellEnabled(self, enabled):
        self._enabled = enabled
        self.setCursor(Qt.PointingHandCursor if enabled else Qt.ArrowCursor)
        self.update()

    def enterEvent(self, e):
        self.isHover = True
        self.update()
        return super().enterEvent(e)

    def leaveEvent(self, e):
        self.isHover = False
        self.update()
        return super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.isPressed = True
            self.update()
        return super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if self.isPressed and self._enabled and self.image:
            self.clicked.emit(self.championId)
        self.isPressed = False
        self.update()
        return super().mouseReleaseEvent(e)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        path = QPainterPath()
        path.addRoundedRect(0, 0, self.width(), self.height(), 4, 4)
        painter.setClipPath(path)

        if self.image and not self.image.isNull():
            img = self.image.scaled(
                self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation)
            painter.drawPixmap(self.rect(), img)
        else:
            painter.fillRect(self.rect(), QColor(255, 255, 255, 10))

        if not self._enabled:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 100))

        if self.isHover and self._enabled and self.image:
            painter.fillRect(self.rect(), QColor(255, 255, 255, 40))
        elif self.isPressed and self._enabled and self.image:
            painter.fillRect(self.rect(), QColor(0, 0, 0, 60))

        painter.setPen(QPen(QColor(255, 255, 255, 30), 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(0, 0, self.width(), self.height(), 4, 4)


class MiniTitleBar(QFrame):
    """ 自定义标题栏：标题 + 图钉置顶 + 最小化 + 关闭 """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(42)

        self.titleLabel = QLabel("Seraphine Mini")
        self.titleLabel.setObjectName("MiniTitleLabel")

        self.pinButton = TransparentToolButton(FluentIcon.PIN)
        # 该版本 FluentIcon.MINIMIZE 不是横线图标，改用系统风格的自绘按钮
        self.minButton = MinimizeButton()
        self.closeButton = TransparentToolButton(FluentIcon.CLOSE)

        for btn in (self.pinButton, self.minButton, self.closeButton):
            btn.setFixedSize(34, 34)

        # MinimizeButton 默认是黑色图标，改成深色标题栏用的白色系
        self.minButton.setNormalColor(QColor("#f2f2f2"))
        self.minButton.setHoverColor(QColor("#ffffff"))
        self.minButton.setPressedColor(QColor("#ffffff"))
        self.minButton.setHoverBackgroundColor(QColor(255, 255, 255, 26))
        self.minButton.setPressedBackgroundColor(QColor(255, 255, 255, 51))

        self.pinButton.setCheckable(True)
        self.pinButton.setChecked(cfg.get(cfg.miniWindowOnTop))
        self.pinButton.setToolTip("窗口置顶")

        self.hBoxLayout = QHBoxLayout(self)
        self.hBoxLayout.setContentsMargins(14, 0, 6, 0)
        self.hBoxLayout.setSpacing(2)
        self.hBoxLayout.addWidget(self.titleLabel)
        self.hBoxLayout.addStretch(1)
        self.hBoxLayout.addWidget(self.pinButton)
        self.hBoxLayout.addWidget(self.minButton)
        self.hBoxLayout.addWidget(self.closeButton)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            handle = self.window().windowHandle()
            if handle:
                handle.startSystemMove()
                return

        super().mousePressEvent(event)


class PlaceholderPage(QWidget):
    """ 空闲状态：Logo + 提示文字 """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.logoLabel = QLabel()
        self.logoLabel.setPixmap(QPixmap(
            "app/resource/images/logo.png").scaled(
                88, 88, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        self.logoLabel.setStyleSheet("background: transparent;")

        logoEffect = QGraphicsOpacityEffect()
        logoEffect.setOpacity(0.45)
        self.logoLabel.setGraphicsEffect(logoEffect)

        self.hintLabel = QLabel("当前没有进行中的活动")
        self.hintLabel.setObjectName("MiniHintLabel")
        self.hintLabel.setAlignment(Qt.AlignCenter)

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(20, 0, 20, 12)
        self.vBoxLayout.setSpacing(16)
        self.vBoxLayout.addStretch(1)
        self.vBoxLayout.addWidget(self.logoLabel, 0, Qt.AlignHCenter)
        self.vBoxLayout.addWidget(self.hintLabel, 0, Qt.AlignHCenter)
        self.vBoxLayout.addStretch(1)

    def setHint(self, text: str):
        self.hintLabel.setText(text)


class LoungePage(QWidget):
    """ 房间 / 匹配中 / 找到对局 + 自动接受/自动匹配开关 """
    autoAcceptToggled = pyqtSignal(bool)
    autoMatchToggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.bigLabel = QLabel()
        self.bigLabel.setObjectName("MiniBigLabel")
        self.bigLabel.setAlignment(Qt.AlignCenter)
        self.bigLabel.setWordWrap(True)

        self.subLabel = QLabel()
        self.subLabel.setObjectName("MiniSubLabel")
        self.subLabel.setAlignment(Qt.AlignCenter)
        self.subLabel.setWordWrap(True)

        self.acceptButton = PrimaryPushButton("接受")
        self.declineButton = PushButton("拒绝")
        self.cancelButton = PushButton("取消寻找")

        for btn in (self.acceptButton, self.declineButton, self.cancelButton):
            btn.setFixedHeight(32)
            btn.setMinimumWidth(88)

        self.buttonLayout = QHBoxLayout()
        self.buttonLayout.setSpacing(10)
        self.buttonLayout.addStretch(1)
        self.buttonLayout.addWidget(self.acceptButton)
        self.buttonLayout.addWidget(self.declineButton)
        self.buttonLayout.addWidget(self.cancelButton)
        self.buttonLayout.addStretch(1)

        # 自动接受开关
        self.autoAcceptSwitch = SwitchButton()
        self.autoAcceptSwitch.setChecked(cfg.get(cfg.enableAutoAcceptMatching))
        self.autoAcceptLabel = QLabel("自动接受")
        self.autoAcceptLabel.setObjectName("MiniSubLabel")

        autoRow = QHBoxLayout()
        autoRow.setContentsMargins(16, 0, 16, 0)
        autoRow.addWidget(self.autoAcceptLabel)
        autoRow.addStretch()
        autoRow.addWidget(self.autoAcceptSwitch)

        # 自动匹配开关 + 延迟
        self.autoMatchSwitch = SwitchButton()
        self.autoMatchSwitch.setChecked(cfg.get(cfg.enableAutoMatchmaking))
        delayVal = cfg.get(cfg.autoMatchmakingDelay)
        self.autoMatchLabel = QLabel(f"自动匹配 ({delayVal}秒)")
        self.autoMatchLabel.setObjectName("MiniSubLabel")
        self.autoMatchDelay = SpinBox()
        self.autoMatchDelay.setRange(0, 30)
        self.autoMatchDelay.setValue(delayVal)
        self.autoMatchDelay.setFixedWidth(60)

        autoMatchRow = QHBoxLayout()
        autoMatchRow.setContentsMargins(16, 0, 16, 0)
        autoMatchRow.addWidget(self.autoMatchLabel)
        autoMatchRow.addWidget(self.autoMatchDelay)
        autoMatchRow.addStretch()
        autoMatchRow.addWidget(self.autoMatchSwitch)

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(22, 10, 22, 14)
        self.vBoxLayout.setSpacing(10)
        self.vBoxLayout.addStretch(1)
        self.vBoxLayout.addWidget(self.bigLabel)
        self.vBoxLayout.addWidget(self.subLabel)
        self.vBoxLayout.addSpacing(6)
        self.vBoxLayout.addLayout(self.buttonLayout)
        self.vBoxLayout.addStretch(1)
        self.vBoxLayout.addLayout(autoRow)
        self.vBoxLayout.addLayout(autoMatchRow)

        self.setButtons(accept=False, decline=False, cancel=False)
        self.autoAcceptSwitch.checkedChanged.connect(self.autoAcceptToggled.emit)
        self.autoMatchSwitch.checkedChanged.connect(self.autoMatchToggled.emit)
        self.autoMatchDelay.valueChanged.connect(self._onMatchDelayChanged)

    def _onMatchDelayChanged(self, value):
        cfg.set(cfg.autoMatchmakingDelay, value)
        self.autoMatchLabel.setText(f"自动匹配 ({value}秒)")

    def setContent(self, big: str, sub: str = ""):
        self.bigLabel.setText(big)
        self.subLabel.setText(sub)

    def setButtons(self, accept=None, decline=None, cancel=None):
        if accept is not None:
            self.acceptButton.setVisible(accept)
        if decline is not None:
            self.declineButton.setVisible(decline)
        if cancel is not None:
            self.cancelButton.setVisible(cancel)

    def setAutoAcceptChecked(self, checked):
        self.autoAcceptSwitch.blockSignals(True)
        self.autoAcceptSwitch.setChecked(checked)
        self.autoAcceptSwitch.blockSignals(False)

    def setAutoMatchChecked(self, checked):
        self.autoMatchSwitch.blockSignals(True)
        self.autoMatchSwitch.setChecked(checked)
        self.autoMatchSwitch.blockSignals(False)
        delay = cfg.get(cfg.autoMatchmakingDelay)
        self.autoMatchDelay.blockSignals(True)
        self.autoMatchDelay.setValue(delay)
        self.autoMatchDelay.blockSignals(False)
        self.autoMatchLabel.setText(f"自动匹配 ({delay}秒)")


class ChampSelectPage(QWidget):
    """ 英雄选择中：阶段倒计时 + 自己的英雄 + 备战席网格 """

    benchChampionClicked = pyqtSignal(int)
    rerollClicked = pyqtSignal()
    autoSelectToggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.titleLabel = QLabel("英雄选择中")
        self.titleLabel.setObjectName("MiniBigLabel")
        self.titleLabel.setAlignment(Qt.AlignCenter)

        self.phaseLabel = QLabel()
        self.phaseLabel.setObjectName("MiniSubLabel")
        self.phaseLabel.setAlignment(Qt.AlignCenter)

        # 当前英雄
        self.champIcon = RoundIcon(
            "app/resource/images/champion-0.png", 64, borderWidth=0)

        self.champNameLabel = QLabel("尚未选择英雄")
        self.champNameLabel.setObjectName("MiniChampNameLabel")
        self.champNameLabel.setAlignment(Qt.AlignCenter)

        self.positionLabel = QLabel("")
        self.positionLabel.setObjectName("MiniSubLabel")
        self.positionLabel.setAlignment(Qt.AlignCenter)

        # 备战席网格 2×5
        self.benchGrid = QGridLayout()
        self.benchGrid.setSpacing(4)
        self.benchGrid.setContentsMargins(0, 0, 0, 0)
        self.benchCells = []
        for i in range(10):
            cell = BenchChampionCell()
            self.benchCells.append(cell)
            row, col = divmod(i, 5)
            self.benchGrid.addWidget(cell, row, col, Qt.AlignCenter)

        self.benchContainer = QWidget()
        self.benchContainer.setLayout(self.benchGrid)

        self.benchLabel = QLabel("备战席")
        self.benchLabel.setObjectName("MiniSubLabel")
        self.benchLabel.setAlignment(Qt.AlignCenter)

        # 摇骰按钮
        self.rerollButton = TransparentToolButton(FluentIcon.SYNC)
        self.rerollButton.setFixedSize(30, 30)
        self.rerollButton.setToolTip("摇骰子")
        self.rerollButton.setVisible(False)
        self.rerollCount = QLabel("0")
        self.rerollCount.setObjectName("MiniSubLabel")
        self.rerollCount.setAlignment(Qt.AlignCenter)
        self.rerollCount.setVisible(False)

        rerollRow = QHBoxLayout()
        rerollRow.setAlignment(Qt.AlignCenter)
        rerollRow.setSpacing(6)
        rerollRow.addWidget(self.rerollButton)
        rerollRow.addWidget(self.rerollCount)

        # 自动选择开关
        self.autoSelectSwitch = SwitchButton()
        self.autoSelectSwitch.setChecked(cfg.get(cfg.enableAutoSelectChampion))
        self.autoSelectLabel = QLabel("自动选择")
        self.autoSelectLabel.setObjectName("MiniSubLabel")

        autoRow = QHBoxLayout()
        autoRow.setContentsMargins(30, 0, 30, 0)
        autoRow.addWidget(self.autoSelectLabel)
        autoRow.addStretch()
        autoRow.addWidget(self.autoSelectSwitch)

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(16, 12, 16, 14)
        self.vBoxLayout.setSpacing(6)
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addWidget(self.phaseLabel)
        self.vBoxLayout.addSpacing(4)
        self.vBoxLayout.addWidget(self.champIcon, 0, Qt.AlignHCenter)
        self.vBoxLayout.addWidget(self.champNameLabel)
        self.vBoxLayout.addWidget(self.positionLabel)
        self.vBoxLayout.addSpacing(6)
        self.vBoxLayout.addWidget(self.benchLabel)
        self.vBoxLayout.addWidget(self.benchContainer, 0, Qt.AlignHCenter)
        self.vBoxLayout.addLayout(rerollRow)
        self.vBoxLayout.addSpacing(6)
        self.vBoxLayout.addLayout(autoRow)

        # 信号
        for cell in self.benchCells:
            cell.clicked.connect(self.benchChampionClicked.emit)
        self.rerollButton.clicked.connect(self.rerollClicked.emit)
        self.autoSelectSwitch.checkedChanged.connect(self.autoSelectToggled.emit)

    def setPhase(self, text: str):
        self.phaseLabel.setText(text)

    def setChampion(self, iconPath: str = None, name: str = None,
                    position: str = ""):
        if iconPath is not None:
            self.champIcon.image = QPixmap(iconPath)
            self.champIcon.havePic = True
            self.champIcon.update()

        if name is not None:
            self.champNameLabel.setText(name)

        self.positionLabel.setText(position or "")

    def setBenchVisible(self, visible):
        self.benchLabel.setVisible(visible)
        self.benchContainer.setVisible(visible)

    def updateBench(self, benchChampions, currentChampionId, iconPaths):
        """ 更新备战席网格
        benchChampions: list of {championId: int, isPriority: bool}
        currentChampionId: int — 当前已选英雄，不可点击
        iconPaths: dict {championId: path}
        """
        for i, cell in enumerate(self.benchCells):
            if i < len(benchChampions):
                cid = benchChampions[i].get('championId', 0)
                path = iconPaths.get(cid, "app/resource/images/champion-0.png")
                cell.setChampion(cid, path)
                cell.setCellEnabled(cid != currentChampionId and cid != 0)
            else:
                cell.setChampion(0, None)
                cell.setCellEnabled(False)

    def setRerollInfo(self, remaining, visible):
        self.rerollButton.setVisible(visible)
        self.rerollCount.setVisible(visible)
        self.rerollCount.setText(str(remaining))

    def setAutoSelectChecked(self, checked):
        self.autoSelectSwitch.blockSignals(True)
        self.autoSelectSwitch.setChecked(checked)
        self.autoSelectSwitch.blockSignals(False)


class MiniWindow(FramelessWindow):
    """ 仿 LeagueAkari Mini 的迷你状态悬浮窗 """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.phase = None
        self._prevPhase = None
        self._polling = False
        self.champDeadlineMs = None
        self.champPhaseBase = ""

        # 必须通过 setTitleBar 替换 qframelesswindow 自带的标题栏，
        # 否则自带的 min/max/close 按钮会浮动叠加在自定义标题栏上
        self.setTitleBar(MiniTitleBar(self))
        self.placeholderPage = PlaceholderPage()
        self.loungePage = LoungePage()
        self.champSelectPage = ChampSelectPage()

        self.stackedWidget = QStackedWidget(self)
        self.stackedWidget.addWidget(self.placeholderPage)
        self.stackedWidget.addWidget(self.loungePage)
        self.stackedWidget.addWidget(self.champSelectPage)

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setSpacing(0)
        self.vBoxLayout.addWidget(self.titleBar)
        self.vBoxLayout.addWidget(self.stackedWidget, 1)

        self.timer = QTimer(self)
        self.timer.setInterval(500)
        self.timer.timeout.connect(self.__onTick)

        self.__initWindow()
        self.__connectSignalToSlot()

    def __initWindow(self):
        self.setObjectName("miniWindow")
        self.setFixedSize(320, 460)
        self.setWindowTitle("Seraphine Mini")
        self.setWindowIcon(QIcon("app/resource/images/logo.png"))

        if cfg.get(cfg.miniWindowOnTop):
            self.setWindowFlags(
                self.windowFlags() | Qt.WindowStaysOnTopHint)

        self.setStyleSheet(
            """
            QLabel { background: transparent; }
            #MiniTitleLabel {
                color: #f2f2f2;
                font: 600 13px 'Microsoft YaHei', 'Segoe UI';
            }
            QToolButton {
                border-radius: 6px;
                background: transparent;
            }
            QToolButton:hover { background: rgba(255, 255, 255, 0.10); }
            QToolButton:checked { background: rgba(255, 255, 255, 0.18); }
            #MiniHintLabel, #MiniSubLabel {
                color: #9a9a9a;
                font: 13px 'Microsoft YaHei', 'Segoe UI';
            }
            #MiniBigLabel {
                color: #ffffff;
                font: 600 16px 'Microsoft YaHei', 'Segoe UI';
            }
            #MiniChampNameLabel {
                color: #ffffff;
                font: 600 14px 'Microsoft YaHei', 'Segoe UI';
            }
            QStackedWidget { background: #202020; }
            """
        )

        self.__moveLeftCenter()

    def __connectSignalToSlot(self):
        self.titleBar.minButton.clicked.connect(self.showMinimized)
        self.titleBar.closeButton.clicked.connect(self.hide)
        self.titleBar.pinButton.toggled.connect(self.__onPinToggled)

        self.loungePage.acceptButton.clicked.connect(self.__onAcceptClicked)
        self.loungePage.declineButton.clicked.connect(self.__onDeclineClicked)
        self.loungePage.cancelButton.clicked.connect(self.__onCancelSearchClicked)
        self.loungePage.autoAcceptToggled.connect(self.__onAutoAcceptToggled)
        self.loungePage.autoMatchToggled.connect(self.__onAutoMatchToggled)

        self.champSelectPage.benchChampionClicked.connect(self.__onBenchChampionClicked)
        self.champSelectPage.rerollClicked.connect(self.__onRerollClicked)
        self.champSelectPage.autoSelectToggled.connect(self.__onAutoSelectToggled)

        signalBus.gameStatusChanged.connect(self.__onGameStatusChanged)
        signalBus.champSelectChanged.connect(self.__onChampSelectChanged)
        signalBus.lolClientStarted.connect(self.__onLolClientStarted)
        signalBus.lolClientEnded.connect(self.__onLolClientEnded)

    def __moveLeftCenter(self):
        desktop = QApplication.desktop().availableGeometry()
        self.move(24,
                  desktop.height() // 2 - self.height() // 2)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor("#202020"))
        painter.drawRect(self.rect())

    def showEvent(self, event):
        super().showEvent(event)

        if self.phase is None and connector.lcuSess is not None:
            asyncio.create_task(self.__syncCurrentPhase())

        self.timer.start()

    def hideEvent(self, event):
        super().hideEvent(event)
        self.timer.stop()

    def closeEvent(self, event):
        event.ignore()
        self.hide()

    # ------------------------------------------------------------------
    # 状态切换
    # ------------------------------------------------------------------

    def __pageForPhase(self, phase):
        if phase in LOUNGE_PHASES:
            return LOUNGE_PAGE
        if phase == 'ChampSelect':
            return CHAMP_SELECT_PAGE
        return PLACEHOLDER_PAGE

    @asyncSlot(str)
    async def __onGameStatusChanged(self, phase):
        logger.debug(f"mini window gameflow phase: {phase}", TAG)
        self.phase = phase
        self.champDeadlineMs = None
        self.champPhaseBase = ""

        page = self.__pageForPhase(phase)
        self.stackedWidget.setCurrentIndex(page)

        # 进入房间/匹配/选择 → 自动弹出（受开关控制）
        if phase in LOUNGE_PHASES or phase == 'ChampSelect':
            if not self.isVisible() and cfg.get(cfg.enableMiniWindow):
                self.show()
                self.raise_()
                self.activateWindow()
            elif not cfg.get(cfg.enableMiniWindow) and self.isVisible():
                self.hide()

        # 仅从房间/匹配/选择退出到空闲时 → 自动隐藏
        # 不在空闲时手动打开就藏
        wasInRoom = self._prevPhase in LOUNGE_PHASES or self._prevPhase == 'ChampSelect'
        nowIdle = page == PLACEHOLDER_PAGE and phase not in (
            'InProgress', 'GameStart', 'Reconnect')
        if wasInRoom and nowIdle:
            if self.isVisible():
                self.hide()

        self._prevPhase = phase

        if page == PLACEHOLDER_PAGE:
            if phase in ('InProgress', 'GameStart', 'Reconnect'):
                self.placeholderPage.setHint("游戏进行中")
            elif phase in ('EndOfGame', 'PreEndOfGame', 'WaitingForStats'):
                self.placeholderPage.setHint("对局已结束")
            else:
                self.placeholderPage.setHint("当前没有进行中的活动")

        elif page == LOUNGE_PAGE:
            self.loungePage.setAutoAcceptChecked(
                cfg.get(cfg.enableAutoAcceptMatching))
            self.loungePage.setAutoMatchChecked(
                cfg.get(cfg.enableAutoMatchmaking))
            await self.__refreshLounge()
            if (self.phase == 'Lobby'
                    and cfg.get(cfg.enableAutoMatchmaking)):
                asyncio.create_task(self.__autoStartMatchmaking())

        else:
            self.champSelectPage.setAutoSelectChecked(
                cfg.get(cfg.enableAutoSelectChampion))
            await self.__refreshChampSelect()

    @asyncSlot(int)
    async def __onLolClientStarted(self, _):
        await self.__syncCurrentPhase()

    @asyncSlot()
    async def __onLolClientEnded(self):
        self.phase = None
        self.champDeadlineMs = None
        self.timer.stop()
        self.stackedWidget.setCurrentIndex(PLACEHOLDER_PAGE)
        self.placeholderPage.setHint("等待英雄联盟客户端启动")

    async def __syncCurrentPhase(self):
        try:
            phase = await connector.getGameStatus()
        except Exception as e:
            logger.debug(f"sync game status failed: {e}", TAG)
            self.placeholderPage.setHint("等待英雄联盟客户端启动")
            return

        await self.__onGameStatusChanged(phase)

    # ------------------------------------------------------------------
    # 房间 / 匹配 / 确认
    # ------------------------------------------------------------------

    async def __refreshLounge(self):
        phase = self.phase

        try:
            if phase == 'Lobby':
                await self.__showLobby()
            elif phase == 'Matchmaking':
                await self.__showMatchmaking()
            elif phase == 'ReadyCheck':
                await self.__showReadyCheck()
        except Exception as e:
            logger.debug(f"refresh lounge failed: {e}", TAG)

    async def __showLobby(self):
        page = self.loungePage
        page.setButtons(accept=False, decline=False, cancel=False)
        page.setContent("房间中")

        try:
            session = await connector.getGameflowSession()
            queueName = session['gameData']['queue'].get('name') or ''
            mapName = session.get('map', {}).get('name') or ''
            title = " · ".join(x for x in (queueName, mapName) if x)
            if title:
                page.setContent(title, "房间中")
        except Exception:
            pass

    async def __showMatchmaking(self):
        page = self.loungePage
        page.setButtons(accept=False, decline=False, cancel=True)
        page.setContent("正在寻找对局")

        try:
            search = await connector.getMatchmakingSearch()
            elapsed = search.get('timeInQueue', 0)
            estimated = search.get('estimatedQueueTime', 0)
            sub = f"已等待 {elapsed:.1f} 秒 / 预计 {estimated:.1f} 秒"

            low = search.get('lowPriorityData') or {}
            if low.get('penaltyTime'):
                sub = (f"低优先队列：剩余 {low.get('penaltyTimeRemaining', 0):.0f} 秒"
                       f"（共 {low.get('penaltyTime', 0):.0f} 秒）")

            page.setContent("正在寻找对局", sub)
        except Exception:
            pass

    async def __showReadyCheck(self):
        page = self.loungePage

        try:
            status = await connector.getReadyCheckStatus()
        except Exception:
            return

        if status.get('errorCode'):
            return

        response = status.get('playerResponse', 'None')

        if response == 'Accepted':
            page.setContent("已接受匹配", "等待其他玩家接受…")
            page.setButtons(accept=False, decline=True, cancel=False)
        elif response == 'Declined':
            page.setContent("已拒绝匹配", "可重新接受对局")
            page.setButtons(accept=True, decline=False, cancel=False)
        else:
            page.setContent("对局已找到！", "请选择接受或拒绝")
            page.setButtons(accept=True, decline=True, cancel=False)

    @asyncSlot()
    async def __onAcceptClicked(self):
        try:
            await connector.acceptMatchMaking()
        except Exception as e:
            logger.debug(f"accept failed: {e}", TAG)
        await self.__refreshLounge()

    @asyncSlot()
    async def __onDeclineClicked(self):
        try:
            await connector.declineMatchMaking()
        except Exception as e:
            logger.debug(f"decline failed: {e}", TAG)
        await self.__refreshLounge()

    @asyncSlot()
    async def __onCancelSearchClicked(self):
        try:
            await connector.cancelMatchmakingSearch()
        except Exception as e:
            logger.debug(f"cancel search failed: {e}", TAG)
        # 取消寻找时关闭自动匹配开关
        self.loungePage.setAutoMatchChecked(False)
        cfg.set(cfg.enableAutoMatchmaking, False)

    def __onAutoAcceptToggled(self, checked):
        cfg.set(cfg.enableAutoAcceptMatching, checked)

    def __onAutoMatchToggled(self, checked):
        cfg.set(cfg.enableAutoMatchmaking, checked)
        if checked and self.phase == 'Lobby':
            asyncio.create_task(self.__autoStartMatchmaking())

    async def __autoStartMatchmaking(self):
        delay = cfg.get(cfg.autoMatchmakingDelay)
        if delay > 0:
            logger.debug(f"auto matchmaking waiting {delay}s", TAG)
            await asyncio.sleep(delay)

        # 等待期间如果用户取消了（开关已关），不再开始
        if not cfg.get(cfg.enableAutoMatchmaking):
            return
        if self.phase != 'Lobby':
            return

        try:
            await connector.startMatchmaking()
            logger.debug("auto matchmaking started", TAG)
        except Exception as e:
            logger.debug(f"auto matchmaking failed: {e}", TAG)
        await self.__refreshLounge()

    # ------------------------------------------------------------------
    # 英雄选择
    # ------------------------------------------------------------------

    @asyncSlot(dict)
    async def __onChampSelectChanged(self, event):
        data = event.get('data') or {}
        if not data:
            return

        await self.__applyChampSelectData(data)

    async def __refreshChampSelect(self):
        try:
            data = await connector.getChampSelectSession()
        except Exception as e:
            logger.debug(f"get champ select session failed: {e}", TAG)
            return

        if not data or data.get('errorCode'):
            return

        await self.__applyChampSelectData(data)

    async def __applyChampSelectData(self, data):
        page = self.champSelectPage

        timer = data.get('timer') or {}
        phaseName = CHAMP_PHASE_TEXT.get(
            timer.get('phase'), timer.get('phase', ''))
        leftMs = timer.get('adjustedTimeLeftInPhase')
        if isinstance(leftMs, (int, float)):
            self.champDeadlineMs = int(time.time() * 1000) + int(leftMs)

        self.champPhaseBase = phaseName
        self.__renderChampPhase()
        page.titleLabel.setText("英雄选择中")

        cellId = data.get('localPlayerCellId')
        me = next((p for p in data.get('myTeam', [])
                   if p.get('cellId') == cellId), None)

        currentChampionId = 0
        if me is not None:
            championId = me.get('championId') or me.get(
                'championPickIntent') or 0
            position = POSITION_TEXT.get(me.get('assignedPosition', ''), '')
            currentChampionId = championId

            if not championId:
                page.setChampion(
                    iconPath="app/resource/images/champion-0.png",
                    name="尚未选择英雄", position=position)
            else:
                name = ""
                try:
                    name = connector.manager.getChampionNameById(championId)
                except Exception:
                    pass

                try:
                    iconPath = await connector.getChampionIcon(championId)
                except Exception:
                    iconPath = "app/resource/images/champion-0.png"

                page.setChampion(iconPath=iconPath,
                                 name=name or "已选择英雄",
                                 position=position)
        else:
            page.setChampion(
                iconPath="app/resource/images/champion-0.png",
                name="尚未选择英雄", position="")

        # 备战席网格
        benchEnabled = data.get('benchEnabled', False)
        benchChampions = data.get('benchChampions') or []

        page.setBenchVisible(benchEnabled)

        if benchEnabled and benchChampions:
            iconPaths = {}
            for bc in benchChampions:
                cid = bc.get('championId', 0)
                if cid:
                    try:
                        iconPaths[cid] = await connector.getChampionIcon(cid)
                    except Exception:
                        iconPaths[cid] = "app/resource/images/champion-0.png"

            page.updateBench(benchChampions, currentChampionId, iconPaths)

            # 摇骰子
            rerolls = data.get('rerollsRemaining', 0)
            allowReroll = data.get('allowRerolling', False)
            showReroll = rerolls > 0 or allowReroll
            page.setRerollInfo(rerolls, showReroll)

    def __renderChampPhase(self):
        if self.champDeadlineMs is None:
            self.champSelectPage.setPhase(self.champPhaseBase)
            return

        remainMs = max(
            self.champDeadlineMs - int(time.time() * 1000), 0)
        seconds = remainMs // 1000
        self.champSelectPage.setPhase(
            f"{self.champPhaseBase} · {seconds} 秒")

    # ------------------------------------------------------------------
    # 备战席 / 摇骰 / 开关
    # ------------------------------------------------------------------

    @asyncSlot(int)
    async def __onBenchChampionClicked(self, championId):
        if not championId:
            return
        try:
            await connector.benchSwap(championId)
        except Exception as e:
            logger.debug(f"bench swap failed: {e}", TAG)
        await self.__refreshChampSelect()

    @asyncSlot()
    async def __onRerollClicked(self):
        try:
            await connector.reroll()
        except Exception as e:
            logger.debug(f"reroll failed: {e}", TAG)
        await self.__refreshChampSelect()

    def __onAutoSelectToggled(self, checked):
        cfg.set(cfg.enableAutoSelectChampion, checked)

    # ------------------------------------------------------------------
    # 轮询
    # ------------------------------------------------------------------

    def __onTick(self):
        if not self.isVisible():
            return

        page = self.stackedWidget.currentIndex()

        if page == CHAMP_SELECT_PAGE and self.champDeadlineMs is not None:
            self.__renderChampPhase()

        elif page == LOUNGE_PAGE and self.phase in ('Matchmaking',
                                                     'ReadyCheck'):
            if self._polling:
                return
            self._polling = True

            async def run():
                try:
                    await self.__refreshLounge()
                finally:
                    self._polling = False

            asyncio.create_task(run())

    # ------------------------------------------------------------------
    # 置顶
    # ------------------------------------------------------------------

    def __onPinToggled(self, checked):
        cfg.set(cfg.miniWindowOnTop, checked)

        if checked:
            self.setWindowFlags(
                self.windowFlags() | Qt.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(
                self.windowFlags() & ~Qt.WindowStaysOnTopHint)

        # setWindowFlags 会隐藏窗口，必须重新显示
        self.show()
        self.raise_()
        self.activateWindow()

    def showWindow(self):
        """ 供主窗口导航按钮调用 """
        self.show()
        self.showNormal()
        self.raise_()
        self.activateWindow()
