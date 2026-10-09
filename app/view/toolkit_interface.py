import asyncio
import os
import random
import time
from datetime import datetime

import pyperclip
from qasync import asyncSlot
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QStackedWidget,
                             QTableWidgetItem, QAbstractItemView, QSizePolicy,
                             QLabel, QFrame, QGridLayout)
from qfluentwidgets import TransparentToolButton, HyperlinkButton

from app.common.qfluentwidgets import (Pivot, TableWidget, SimpleCardWidget,
                                       SearchLineEdit, CheckBox, PrimaryPushButton,
                                       PushButton, BodyLabel, StrongBodyLabel,
                                       CaptionLabel, InfoBar, InfoBarPosition,
                                       MessageBox, FluentIcon)
from app.common.signals import signalBus
from app.common.logger import logger
from app.common.style_sheet import StyleSheet
from app.components.seraphine_interface import SeraphineInterface
from app.components.champion_icon_widget import RoundIcon
from app.lol.connector import connector


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def makeChoices(items, count):
    """
    等权重随机选择 count 个不重复元素 (对应 Akari 的 ChoiceMaker)
    """
    if not items or count <= 0:
        return []
    if count >= len(items):
        return list(items)
    return random.sample(items, count)


def formatDate(ms):
    try:
        return time.strftime("%Y-%m-%d", time.localtime(ms / 1000))
    except Exception:
        return "-"


def isoToMs(s):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000
    except Exception:
        return None


def friendDisplayName(f):
    gameName = f.get("gameName")
    if gameName:
        tag = f.get("gameTag")
        return f"{gameName}#{tag}" if tag else gameName
    return f.get("name") or f.get("summonerName") or "?"


def nameCell(title, subtitle=""):
    """表格里的「粗体标题 + 灰色副标题」单元格"""
    w = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(10, 4, 10, 4)
    lay.setSpacing(2)

    t = StrongBodyLabel(str(title))
    t.setWordWrap(True)
    lay.addWidget(t)

    if subtitle:
        s = CaptionLabel(str(subtitle))
        s.setWordWrap(True)
        lay.addWidget(s)

    lay.addStretch()
    return w


def checkItem():
    item = QTableWidgetItem()
    item.setFlags(Qt.ItemIsEnabled | Qt.ItemIsUserCheckable)
    item.setCheckState(Qt.Unchecked)
    item.setTextAlignment(Qt.AlignCenter)
    return item


def styleTable(table, headers, widths, height):
    table.setColumnCount(len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(46)
    table.setEditTriggers(QAbstractItemView.NoEditTriggers)
    table.setSelectionMode(QAbstractItemView.NoSelection)
    table.setFocusPolicy(Qt.NoFocus)
    table.setWordWrap(True)
    table.setAlternatingRowColors(False)
    table.horizontalHeader().setStretchLastSection(True)
    table.setFixedHeight(height)

    for col, w in enumerate(widths):
        table.setColumnWidth(col, w)


def showInfo(parent, title, content, success=True):
    if success:
        InfoBar.success(title, content, orient=Qt.Horizontal, isClosable=True,
                        position=InfoBarPosition.TOP_RIGHT, duration=3000,
                        parent=parent)
    else:
        InfoBar.error(title, content, orient=Qt.Horizontal, isClosable=True,
                      position=InfoBarPosition.TOP_RIGHT, duration=4000,
                      parent=parent)


# ---------------------------------------------------------------------------
# 领取工具
# ---------------------------------------------------------------------------

class ClaimPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.grantsData = []      # 原始 grant 列表
        self.eventsData = []      # [(event, [rewardName, ...]), ...]
        self.busy = False
        self.cancelClaim = False
        self.cancelEvent = False

        self.vBox = QVBoxLayout(self)
        self.vBox.setContentsMargins(0, 0, 0, 0)
        self.vBox.setSpacing(12)

        self.grantsCard = self.__buildGrantsCard()
        self.eventsCard = self.__buildEventsCard()

        self.vBox.addWidget(self.grantsCard)
        self.vBox.addWidget(self.eventsCard)
        self.vBox.addStretch()

        # 同步一次按钮文本与全选框状态
        self.__onSelectionChanged(self.grantsTable, self.selectAllGrants,
                                  self.claimBtn, "领取选中")
        self.__onSelectionChanged(self.eventsTable, self.selectAllEvents,
                                  self.claimEventsBtn, "一键领取")

    # ---------------- UI ----------------

    def __buildGrantsCard(self):
        card = SimpleCardWidget()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 16)
        lay.setSpacing(10)

        header = QHBoxLayout()
        title = StrongBodyLabel("奖励领取（二选一 / 多选奖励）")
        self.selectAllGrants = CheckBox("全选")
        self.claimBtn = PrimaryPushButton(FluentIcon.ACCEPT, "领取选中")
        self.cancelClaimBtn = PushButton(FluentIcon.CANCEL, "取消领取")
        self.refreshGrantsBtn = PushButton(FluentIcon.SYNC, "刷新")
        self.cancelClaimBtn.setVisible(False)

        self.claimBtn.clicked.connect(self.__onClaimGrants)
        self.cancelClaimBtn.clicked.connect(self.__onCancelClaim)
        self.refreshGrantsBtn.clicked.connect(lambda: self.refreshGrants(True))
        self.selectAllGrants.toggled.connect(
            lambda checked: self.__toggleAll(self.grantsTable, checked))

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.selectAllGrants)
        header.addWidget(self.claimBtn)
        header.addWidget(self.cancelClaimBtn)
        header.addWidget(self.refreshGrantsBtn)
        lay.addLayout(header)

        self.grantsTable = TableWidget(card)
        styleTable(self.grantsTable, ["", "可领取奖励"], [44, 0], 280)
        self.grantsTable.itemChanged.connect(
            lambda: self.__onSelectionChanged(self.grantsTable,
                                              self.selectAllGrants,
                                              self.claimBtn, "领取选中"))
        lay.addWidget(self.grantsTable)
        return card

    def __buildEventsCard(self):
        card = SimpleCardWidget()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 16)
        lay.setSpacing(10)

        header = QHBoxLayout()
        title = StrongBodyLabel("事件中心（活动奖励一键领取）")
        self.selectAllEvents = CheckBox("全选")
        self.claimEventsBtn = PrimaryPushButton(FluentIcon.ACCEPT, "一键领取")
        self.cancelEventsBtn = PushButton(FluentIcon.CANCEL, "取消领取")
        self.refreshEventsBtn = PushButton(FluentIcon.SYNC, "刷新")
        self.cancelEventsBtn.setVisible(False)

        self.claimEventsBtn.clicked.connect(self.__onClaimEvents)
        self.cancelEventsBtn.clicked.connect(self.__onCancelEvents)
        self.refreshEventsBtn.clicked.connect(lambda: self.refreshEvents(True))
        self.selectAllEvents.toggled.connect(
            lambda checked: self.__toggleAll(self.eventsTable, checked))

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.selectAllEvents)
        header.addWidget(self.claimEventsBtn)
        header.addWidget(self.cancelEventsBtn)
        header.addWidget(self.refreshEventsBtn)
        lay.addLayout(header)

        self.eventsTable = TableWidget(card)
        styleTable(self.eventsTable, ["", "活动 / 未领取奖励"], [44, 0], 280)
        self.eventsTable.itemChanged.connect(
            lambda: self.__onSelectionChanged(self.eventsTable,
                                              self.selectAllEvents,
                                              self.claimEventsBtn, "一键领取"))
        lay.addWidget(self.eventsTable)
        return card

    # ---------------- 通用选择逻辑 ----------------

    def __toggleAll(self, table, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        for row in range(table.rowCount()):
            table.item(row, 0).setCheckState(state)

    def __onSelectionChanged(self, table, selectAllBox, actionBtn, actionText):
        total = table.rowCount()
        checked = sum(1 for i in range(total)
                      if table.item(i, 0).checkState() == Qt.Checked)

        selectAllBox.blockSignals(True)
        if checked == 0:
            selectAllBox.setCheckState(Qt.Unchecked)
        elif checked == total and total > 0:
            selectAllBox.setCheckState(Qt.Checked)
        else:
            selectAllBox.setCheckState(Qt.PartiallyChecked)
        selectAllBox.blockSignals(False)

        actionBtn.setText(f"{actionText}（{checked}）" if checked else actionText)

    def __checkedData(self, table, data):
        return [data[i] for i in range(table.rowCount())
                if table.item(i, 0).checkState() == Qt.Checked]

    def __setGrantsBusy(self, busy):
        self.busy = busy
        self.claimBtn.setVisible(not busy)
        self.cancelClaimBtn.setVisible(busy)
        self.refreshGrantsBtn.setEnabled(not busy)
        self.eventsCard.setEnabled(not busy)

    def __setEventsBusy(self, busy):
        self.busy = busy
        self.claimEventsBtn.setVisible(not busy)
        self.cancelEventsBtn.setVisible(busy)
        self.refreshEventsBtn.setEnabled(not busy)
        self.grantsCard.setEnabled(not busy)

    # ---------------- 奖励选择领取 ----------------

    @asyncSlot()
    async def refreshGrants(self, manual=False):
        if self.busy:
            return
        if not connector.lcuSess:
            if manual:
                showInfo(self.window(), "无法刷新", "请确认英雄联盟客户端已启动", False)
            return

        self.grantsCard.setEnabled(False)
        try:
            grants = await connector.getRewardGrants()
            self.grantsData = grants or []

            self.grantsTable.setRowCount(len(self.grantsData))
            for row, grant in enumerate(self.grantsData):
                rg = grant.get("rewardGroup", {})
                groupTitle = rg.get("localizations", {}).get("title", "") or "待选择奖励"
                rewards = rg.get("rewards", [])
                names = [r.get("localizations", {}).get("title", "奖励")
                         for r in rewards]

                self.grantsTable.setItem(row, 0, checkItem())
                self.grantsTable.setCellWidget(
                    row, 1, nameCell(groupTitle, "、".join(names)))
                self.grantsTable.resizeRowToContents(row)
        except Exception as e:
            logger.error(f"refreshGrants failed: {e}")
            if manual:
                showInfo(self.window(), "刷新失败", str(e), False)
        finally:
            self.grantsCard.setEnabled(True)

    def __onCancelClaim(self):
        self.cancelClaim = True

    @asyncSlot()
    async def __onClaimGrants(self):
        grants = self.__checkedData(self.grantsTable, self.grantsData)
        if not grants:
            showInfo(self.window(), "未选择奖励", "请先勾选需要领取的奖励", False)
            return

        self.cancelClaim = False
        self.__setGrantsBusy(True)
        ok, fail = 0, 0

        try:
            for grant in grants:
                if self.cancelClaim:
                    break

                info = grant.get("info", {})
                rg = grant.get("rewardGroup", {})
                grantId = info.get("id")
                rewardGroupId = rg.get("id")
                rewards = rg.get("rewards", [])

                maxSel = rg.get("selectionStrategyConfig", {}) \
                    .get("maxSelectionsAllowed", 1) or 1
                chosen = makeChoices(
                    [r.get("id") for r in rewards if r.get("id") is not None],
                    maxSel)
                nameMap = {r.get("id"): r.get("localizations", {}).get("title", "奖励")
                           for r in rewards}

                try:
                    await connector.selectRewardGrant(
                        grantId, rewardGroupId, chosen)
                    ok += 1
                    showInfo(self.window(), "领取成功",
                             "、".join(nameMap.get(i, "奖励") for i in chosen))
                except Exception as e:
                    fail += 1
                    logger.error(f"selectRewardGrant failed: {e}")
                    showInfo(self.window(), "领取失败", str(e), False)
        finally:
            self.__setGrantsBusy(False)

        showInfo(self.window(), "奖励领取完成",
                 f"成功 {ok} 项，失败 {fail} 项" +
                 ("，已取消" if self.cancelClaim else ""),
                 fail == 0)
        await self.refreshGrants()

    # ---------------- 事件中心 ----------------

    async def __eventUnselectedNames(self, eventId):
        names = []
        for getter in (connector.getEventRewardTrackItems,
                       connector.getEventRewardTrackBonusItems):
            try:
                items = await getter(eventId) or []
                for item in items:
                    for opt in item.get("rewardOptions", []):
                        if opt.get("state") == "Unselected":
                            n = opt.get("rewardName")
                            if n:
                                names.append(n)
            except Exception as e:
                logger.warning(f"get reward track items failed: {e}")
        return names

    @asyncSlot()
    async def refreshEvents(self, manual=False):
        if self.busy:
            return
        if not connector.lcuSess:
            if manual:
                showInfo(self.window(), "无法刷新", "请确认英雄联盟客户端已启动", False)
            return

        self.eventsCard.setEnabled(False)
        try:
            events = await connector.getEventHubEvents() or []
            events = [e for e in events
                      if e.get("eventInfo", {}).get("unclaimedRewardCount", 0) > 0]

            sem = asyncio.Semaphore(5)

            async def work(e):
                async with sem:
                    return e, await self.__eventUnselectedNames(e.get("eventId"))

            self.eventsData = await asyncio.gather(
                *[work(e) for e in events])

            self.eventsTable.setRowCount(len(self.eventsData))
            for row, (event, names) in enumerate(self.eventsData):
                info = event.get("eventInfo", {})
                title = info.get("eventName", "未知活动")
                subtitle = f"未领取 {info.get('unclaimedRewardCount', 0)} 项：" \
                           f"{'、'.join(names) if names else '...'}"
                self.eventsTable.setItem(row, 0, checkItem())
                self.eventsTable.setCellWidget(row, 1, nameCell(title, subtitle))
                self.eventsTable.resizeRowToContents(row)
        except Exception as e:
            logger.error(f"refreshEvents failed: {e}")
            if manual:
                showInfo(self.window(), "刷新失败", str(e), False)
        finally:
            self.eventsCard.setEnabled(True)

    def __onCancelEvents(self):
        self.cancelEvent = True

    @asyncSlot()
    async def __onClaimEvents(self):
        events = self.__checkedData(self.eventsTable, self.eventsData)
        if not events:
            showInfo(self.window(), "未选择活动", "请先勾选需要领取奖励的活动", False)
            return

        self.cancelEvent = False
        self.__setEventsBusy(True)
        ok, fail = 0, 0

        try:
            for event, _ in events:
                if self.cancelEvent:
                    break

                eventId = event.get("eventId")
                name = event.get("eventInfo", {}).get("eventName", "未知活动")
                try:
                    await connector.claimEventRewards(eventId)
                    ok += 1
                    showInfo(self.window(), "领取成功", name)
                except Exception as e:
                    fail += 1
                    logger.error(f"claimEventRewards failed: {e}")
                    showInfo(self.window(), f"领取失败：{name}", str(e), False)

                # 客户端需要一点时间处理领取结果
                await asyncio.sleep(2)
        finally:
            self.__setEventsBusy(False)

        showInfo(self.window(), "事件中心领取完成",
                 f"成功 {ok} 个活动，失败 {fail} 个" +
                 ("，已取消" if self.cancelEvent else ""),
                 fail == 0)
        await self.refreshEvents()

    def refreshAll(self):
        self.refreshGrants()
        self.refreshEvents()


# ---------------------------------------------------------------------------
# 好友工具
# ---------------------------------------------------------------------------

class FriendPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.friends = []
        self.groupMap = {}          # groupId -> name
        self.lastGame = {}          # puuid -> ms
        self.friendSince = {}       # puuid -> ms
        self.iconPaths = {}         # iconId -> local path
        self.extraEpoch = 0
        self.busy = False

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)

        card = SimpleCardWidget()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 16)
        lay.setSpacing(10)

        header = QHBoxLayout()
        title = StrongBodyLabel("好友管理")
        self.selectAllBox = CheckBox("全选")
        self.deleteBtn = PushButton(FluentIcon.DELETE, "删除选中")
        self.refreshBtn = PushButton(FluentIcon.SYNC, "刷新")
        self.searchBox = SearchLineEdit()
        self.searchBox.setPlaceholderText("搜索好友名称或标签")
        self.searchBox.setClearButtonEnabled(True)
        self.searchBox.setFixedWidth(240)

        self.selectAllBox.toggled.connect(self.__toggleAll)
        self.deleteBtn.clicked.connect(self.__onDelete)
        self.refreshBtn.clicked.connect(lambda: self.refresh(True))
        self.searchBox.textChanged.connect(self.__renderFriends)

        header.addWidget(title)
        header.addStretch()
        header.addWidget(self.selectAllBox)
        header.addWidget(self.deleteBtn)
        header.addWidget(self.refreshBtn)
        header.addSpacing(8)
        header.addWidget(self.searchBox)
        lay.addLayout(header)

        self.table = TableWidget(card)
        styleTable(self.table,
                   ["", "好友", "分组", "最后对局日期", "成为好友时间"],
                   [44, 300, 130, 140, 140], 520)
        self.table.itemChanged.connect(self.__onItemChanged)
        lay.addWidget(self.table)

        root.addWidget(card)
        root.addStretch()

        # 同步一次按钮文本与全选框状态
        self.__onItemChanged()

    def __toggleAll(self, checked):
        state = Qt.Checked if checked else Qt.Unchecked
        for row in range(self.table.rowCount()):
            self.table.item(row, 0).setCheckState(state)

    def __onItemChanged(self):
        total = self.table.rowCount()
        checked = sum(1 for i in range(total)
                      if self.table.item(i, 0).checkState() == Qt.Checked)

        self.selectAllBox.blockSignals(True)
        if checked == 0:
            self.selectAllBox.setCheckState(Qt.Unchecked)
        elif checked == total and total > 0:
            self.selectAllBox.setCheckState(Qt.Checked)
        else:
            self.selectAllBox.setCheckState(Qt.PartiallyChecked)
        self.selectAllBox.blockSignals(False)

        self.deleteBtn.setText(f"删除选中（{checked}）" if checked else "删除选中")

    def __filteredFriends(self):
        query = self.searchBox.text().strip().lower()
        result = []
        for f in self.friends:
            name = friendDisplayName(f)
            if query and query not in name.lower():
                continue
            result.append((f, name))
        return result

    def __renderFriends(self):
        rows = self.__filteredFriends()

        self.table.blockSignals(True)
        self.table.setRowCount(len(rows))

        for row, (f, name) in enumerate(rows):
            self.table.setItem(row, 0, checkItem())

            # 头像 + 名称
            cell = QWidget()
            h = QHBoxLayout(cell)
            h.setContentsMargins(10, 0, 10, 0)
            h.setSpacing(10)
            iconId = f.get("icon")
            path = self.iconPaths.get(iconId) if iconId else None
            if path:
                icon = RoundIcon(path, 32, borderWidth=0)
            else:
                icon = QWidget()
                icon.setFixedSize(32, 32)
            h.addWidget(icon)

            label = BodyLabel(name)
            h.addWidget(label)
            h.addStretch()
            self.table.setCellWidget(row, 1, cell)

            groupItem = QTableWidgetItem(self.groupMap.get(f.get("groupId"), ""))
            groupItem.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 2, groupItem)

            puuid = f.get("puuid")
            last = self.lastGame.get(puuid)
            since = self.friendSince.get(puuid)

            lastItem = QTableWidgetItem(
                formatDate(last) if last else "查询中…" if puuid else "-")
            lastItem.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 3, lastItem)

            sinceItem = QTableWidgetItem(formatDate(since) if since else "-")
            sinceItem.setFlags(Qt.ItemIsEnabled)
            self.table.setItem(row, 4, sinceItem)

            self.table.resizeRowToContents(row)

        self.table.blockSignals(False)
        self.__onItemChanged()

    @asyncSlot()
    async def refresh(self, manual=False):
        if self.busy:
            return
        if not connector.lcuSess:
            if manual:
                showInfo(self.window(), "无法刷新", "请确认英雄联盟客户端已启动", False)
            return

        self.busy = True
        self.refreshBtn.setEnabled(False)
        self.deleteBtn.setEnabled(False)
        try:
            groups, friends = await asyncio.gather(
                connector.getFriendGroups(),
                connector.getFriends())

            self.groupMap = {g.get("id"): g.get("name", "") for g in (groups or [])}
            priority = {g.get("id"): g.get("priority", 0) for g in (groups or [])}
            self.friends = sorted(
                friends or [],
                key=lambda f: -priority.get(f.get("groupId"), 0))

            self.lastGame = {}
            self.friendSince = {}
            self.iconPaths = {}
            self.extraEpoch += 1
            epoch = self.extraEpoch

            self.__renderFriends()
            asyncio.ensure_future(self.__loadExtras(epoch))
        except Exception as e:
            logger.error(f"refresh friends failed: {e}")
            if manual:
                showInfo(self.window(), "刷新失败", str(e), False)
        finally:
            self.busy = False
            self.refreshBtn.setEnabled(True)
            self.deleteBtn.setEnabled(True)

    async def __loadExtras(self, epoch):
        """后台批量加载：成为好友时间、最后对局时间、头像"""
        try:
            giftable = await connector.getGiftableFriends() or []
        except Exception as e:
            logger.warning(f"getGiftableFriends failed: {e}")
            giftable = []

        sinceBySid = {g.get("summonerId"): isoToMs(g.get("friendsSince"))
                      for g in giftable}
        for f in self.friends:
            ms = sinceBySid.get(f.get("summonerId"))
            if ms:
                self.friendSince[f.get("puuid")] = ms

        sem = asyncio.Semaphore(8)

        async def loadLast(f):
            async with sem:
                try:
                    ms = await connector.getLastGameTimeByPuuid(f.get("puuid"))
                    if ms:
                        self.lastGame[f.get("puuid")] = ms
                except Exception:
                    pass

        async def loadIcon(iid):
            async with sem:
                try:
                    self.iconPaths[iid] = await connector.getProfileIcon(iid)
                except Exception:
                    pass

        iconIds = {f.get("icon") for f in self.friends if f.get("icon")}
        await asyncio.gather(
            *[loadLast(f) for f in self.friends],
            *[loadIcon(iid) for iid in iconIds],
            return_exceptions=True)

        if epoch == self.extraEpoch:
            self.__renderFriends()

    @asyncSlot()
    async def __onDelete(self):
        rows = self.__filteredFriends()
        selected = [f for i, (f, _) in enumerate(rows)
                    if self.table.item(i, 0).checkState() == Qt.Checked]

        if not selected:
            showInfo(self.window(), "未选择好友", "请先勾选要删除的好友", False)
            return

        box = MessageBox(
            f"确定删除选中的 {len(selected)} 位好友吗？此操作不可恢复。",
            "删除好友", self.window())
        if not box.exec():
            return

        ok, fail = 0, 0
        self.table.setEnabled(False)
        try:
            for f in selected:
                try:
                    await connector.deleteFriend(str(f.get("id")))
                    ok += 1
                except Exception as e:
                    fail += 1
                    logger.error(f"deleteFriend failed: {e}")
        finally:
            self.table.setEnabled(True)

        showInfo(self.window(), "删除好友完成",
                 f"成功删除 {ok} 位，失败 {fail} 位", fail == 0)
        await self.refresh()


# ---------------------------------------------------------------------------
# 国服换肤
# ---------------------------------------------------------------------------

HASAKEI_DOWNLOAD = "https://share.feijipan.com/s/SB76EiUS?code=1234"
HASAKEI_SITE = "https://mishi.550my.top/"
HASAKEI_SITE_BAK = "https://lmzhushou.550my.top/"
HASAKEI_QGROUP = "https://qm.qq.com/q/WRIS9Xo5GK"

SKIN_IMAGES = [
    ("app/resource/images/hasakei_3.png", "Hasakei 官网首页"),
    ("app/resource/images/hasakei_1.png", "客户端 · 崔丝塔娜皮肤选择"),
    ("app/resource/images/hasakei_2.png", "客户端 · 亚索皮肤选择"),
]

CAROUSEL_W = 720
CAROUSEL_H = 430


class ImageCarousel(QFrame):
    """图片轮播：自动轮流播放，左右按钮手动切换，悬停暂停"""

    def __init__(self, images, interval=4000, onChanged=None, parent=None):
        super().__init__(parent)
        self._slides = [(QPixmap(p), c) for p, c in images if os.path.exists(p)]
        self._index = 0
        self._onChanged = onChanged

        self.setFixedSize(CAROUSEL_W, CAROUSEL_H)
        self.setStyleSheet(
            "ImageCarousel {background-color: rgba(0,0,0,0.06);"
            "border-radius: 10px;}")

        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(0)

        self.imageLabel = QLabel()
        self.imageLabel.setAlignment(Qt.AlignCenter)
        grid.addWidget(self.imageLabel, 0, 0)

        self.prevBtn = TransparentToolButton(FluentIcon.CARE_LEFT_SOLID, self)
        self.nextBtn = TransparentToolButton(FluentIcon.CARE_RIGHT_SOLID, self)
        self.prevBtn.setFixedSize(38, 38)
        self.nextBtn.setFixedSize(38, 38)
        self.prevBtn.clicked.connect(lambda: self._show(self._index - 1, True))
        self.nextBtn.clicked.connect(lambda: self._show(self._index + 1, True))
        grid.addWidget(self.prevBtn, 0, 0,
                       Qt.AlignLeft | Qt.AlignVCenter)
        grid.addWidget(self.nextBtn, 0, 0,
                       Qt.AlignRight | Qt.AlignVCenter)

        self.dotsBar = QHBoxLayout()
        self.dotsBar.setAlignment(Qt.AlignCenter)
        self.dotsBar.setSpacing(8)
        self._dots = []
        for _ in self._slides:
            dot = QLabel("●")
            dot.setFixedSize(12, 12)
            self._dots.append(dot)
            self.dotsBar.addWidget(dot)
        dotsWrap = QWidget()
        dotsWrap.setLayout(self.dotsBar)
        grid.addWidget(dotsWrap, 0, 0, Qt.AlignBottom | Qt.AlignHCenter)
        grid.setRowStretch(0, 1)

        self.timer = QTimer(self)
        self.timer.setInterval(interval)
        self.timer.timeout.connect(lambda: self._show(self._index + 1))

        self._show(0)
        if len(self._slides) > 1:
            self.timer.start()

    def enterEvent(self, event):
        self.timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        if len(self._slides) > 1:
            self.timer.start()
        super().leaveEvent(event)

    def _show(self, index, manual=False):
        if not self._slides:
            return
        self._index = index % len(self._slides)
        pixmap, _caption = self._slides[self._index]
        scaled = pixmap.scaled(CAROUSEL_W - 20, CAROUSEL_H - 20,
                               Qt.KeepAspectRatio, Qt.SmoothTransformation)
        self.imageLabel.setPixmap(scaled)

        active = "#0078D4"
        normal = "rgba(0,0,0,0.25)"
        for i, dot in enumerate(self._dots):
            dot.setStyleSheet(
                f"color: {active if i == self._index else normal}; font-size: 12px;")

        if self._onChanged:
            self._onChanged(self._slides[self._index][1])

        if manual:
            self.timer.start()


class SkinPage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(12)
        root.addStretch()
        root.addWidget(self.__buildCard(), 0, Qt.AlignHCenter)
        root.addStretch()

    def __buildCard(self):
        card = SimpleCardWidget()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(24, 20, 24, 22)
        lay.setSpacing(12)
        lay.setAlignment(Qt.AlignHCenter)

        title = StrongBodyLabel("国服换肤")
        title.setStyleSheet("font-size: 20px;")
        title.setAlignment(Qt.AlignCenter)

        self.captionLabel = CaptionLabel("")
        self.captionLabel.setAlignment(Qt.AlignCenter)
        self.carousel = ImageCarousel(
            SKIN_IMAGES, onChanged=self.captionLabel.setText)

        urlRow = QHBoxLayout()
        urlRow.setAlignment(Qt.AlignCenter)
        urlRow.setSpacing(10)
        downloadBtn = HyperlinkButton()
        downloadBtn.setUrl(HASAKEI_DOWNLOAD)
        downloadBtn.setText("下载客户端")
        downloadBtn.setIcon(FluentIcon.DOWNLOAD)
        copyBtn = PushButton(FluentIcon.COPY, "复制下载链接")
        copyBtn.clicked.connect(self.__copyUrl)
        urlRow.addWidget(downloadBtn)
        urlRow.addWidget(copyBtn)

        recommendLabel = CaptionLabel(
            "牛牛推荐的！目前已实测几个月了，目前 0 封号！")
        recommendLabel.setAlignment(Qt.AlignCenter)
        recommendLabel.setStyleSheet(
            "color: #15A85E; font-size: 13px; font-weight: 600;")
        urlRow2 = QHBoxLayout()
        urlRow2.addStretch()
        urlRow2.addWidget(recommendLabel)
        urlRow2.addStretch()

        # 官网 / 备用网站 / QQ群
        siteRow = QHBoxLayout()
        siteRow.setAlignment(Qt.AlignCenter)
        siteRow.setSpacing(10)
        siteRow.addWidget(self.__linkButton(
            FluentIcon.LINK, "换肤官网", HASAKEI_SITE))
        siteRow.addWidget(self.__linkButton(
            FluentIcon.SYNC, "备用网站", HASAKEI_SITE_BAK))
        siteRow.addWidget(self.__linkButton(
            FluentIcon.PEOPLE, "加入QQ群", HASAKEI_QGROUP))

        lay.addWidget(title)
        lay.addWidget(self.carousel)
        lay.addWidget(self.captionLabel)
        lay.addLayout(urlRow)
        lay.addLayout(siteRow)
        lay.addLayout(urlRow2)

        return card

    @staticmethod
    def __linkButton(icon, text, url):
        btn = HyperlinkButton()
        btn.setUrl(url)
        btn.setText(text)
        btn.setIcon(icon)
        return btn

    def __copyUrl(self):
        pyperclip.copy(HASAKEI_DOWNLOAD)
        InfoBar.success("已复制", "下载链接已复制到剪贴板", orient=Qt.Horizontal,
                        isClosable=True, position=InfoBarPosition.TOP_RIGHT,
                        duration=2500, parent=self.window())


# ---------------------------------------------------------------------------
# 工具箱主界面
# ---------------------------------------------------------------------------

class ToolkitInterface(SeraphineInterface):
    def __init__(self, parent=None):
        super().__init__(parent)

        self.scrollWidget = QWidget()
        self.vBox = QVBoxLayout(self.scrollWidget)
        self.vBox.setContentsMargins(36, 0, 36, 12)
        self.vBox.setSpacing(12)

        self.titleLabel = StrongBodyLabel(self.tr("工具箱"), self)
        self.titleLabel.setObjectName("titleLabel")

        self.pivot = Pivot(self)
        self.stackedWidget = QStackedWidget(self)

        self.claimPage = ClaimPage(self)
        self.friendPage = FriendPage(self)
        self.skinPage = SkinPage(self)

        self.stackedWidget.addWidget(self.claimPage)
        self.stackedWidget.addWidget(self.friendPage)
        self.stackedWidget.addWidget(self.skinPage)

        self.pivot.addItem(
            routeKey="claimPage", text=self.tr("领取工具"),
            onClick=lambda: self.stackedWidget.setCurrentWidget(self.claimPage))
        self.pivot.addItem(
            routeKey="friendPage", text=self.tr("好友工具"),
            onClick=lambda: self.stackedWidget.setCurrentWidget(self.friendPage))
        self.pivot.addItem(
            routeKey="skinPage", text=self.tr("黑科技！"),
            onClick=lambda: self.stackedWidget.setCurrentWidget(self.skinPage))
        self.pivot.setCurrentItem("claimPage")
        self.stackedWidget.setCurrentIndex(0)

        self.vBox.addWidget(self.pivot)
        self.vBox.addWidget(self.stackedWidget)
        self.vBox.addStretch()

        self.scrollWidget.setObjectName("scrollWidget")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setViewportMargins(0, 90, 0, 20)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        StyleSheet.AUXILIARY_INTERFACE.apply(self)

        self._loaded = False
        signalBus.lolClientStarted.connect(self.__onClientStarted)

    def __onClientStarted(self, pid):
        self._loaded = True
        self.claimPage.refreshAll()
        self.friendPage.refresh()

    def showEvent(self, event):
        super().showEvent(event)

        if not self._loaded and connector.lcuSess:
            self._loaded = True
            self.claimPage.refreshAll()
            self.friendPage.refresh()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.titleLabel.move(36, 30)
