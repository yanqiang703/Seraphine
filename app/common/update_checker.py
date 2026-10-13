# coding:utf-8
"""推送弹窗检查模块

软件启动后请求 notice.json，对比版本号决定是否弹窗提示更新。
你只需修改 GitHub 仓库的 notice.json 即可推送消息，无需发新版软件。
"""
import asyncio
import aiohttp
import json
from PyQt5.QtCore import QObject, pyqtSignal, QUrl
from PyQt5.QtWidgets import QApplication
from app.common.config import VERSION, BETA
from app.common.logger import logger

TAG = "UpdateChecker"

# 推送地址（GitHub raw，有 5 分钟缓存）
NOTICE_URL = "https://raw.githubusercontent.com/yanqiang703/Seraphine/main/notice.json"

# 请求超时（秒）
TIMEOUT = 8


class UpdateChecker(QObject):
    """检查更新/推送通知，通过信号通知主窗口弹窗"""
    # 信号参数: title, content, url, password
    updateAvailable = pyqtSignal(str, str, str, str)

    def __init__(self, parent=None):
        super().__init__(parent)

    async def check(self):
        """启动后异步检查，失败静默"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    NOTICE_URL,
                    timeout=aiohttp.ClientTimeout(total=TIMEOUT),
                    ssl=False
                ) as resp:
                    if resp.status != 200:
                        logger.info(f"Update check: HTTP {resp.status}", TAG)
                        return
                    text = await resp.text()
                    data = json.loads(text)

            # 推送开关
            if not data.get("enabled", True):
                logger.info("Update check: disabled by notice.json", TAG)
                return

            # 对比版本号
            latest = data.get("latestVersion", "").strip()
            current = (BETA or VERSION).strip()
            if not latest or latest == current:
                logger.info(
                    f"Update check: same version ({current})", TAG)
                return

            # 新版本更高 → 弹窗
            title = data.get("title", "发现新版本")
            content = data.get(
                "content",
                f"Seraphine {latest} 已发布，点击立即下载。")
            url = data.get("url", "")
            password = data.get("password", "")

            logger.info(
                f"Update check: new version {latest} (current {current})",
                TAG)
            self.updateAvailable.emit(title, content, url, password)

        except asyncio.TimeoutError:
            logger.info("Update check: timeout (network)", TAG)
        except json.JSONDecodeError as e:
            logger.info(f"Update check: invalid JSON ({e})", TAG)
        except Exception as e:
            logger.info(f"Update check: failed ({e})", TAG)
