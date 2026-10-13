# coding:utf-8
"""推送弹窗检查模块

软件启动后请求 notice.json，对比版本号决定是否弹窗提示更新。
你只需修改 GitHub 仓库的 notice.json 即可推送消息，无需发新版软件。
"""
import asyncio
import aiohttp
import json
from PyQt5.QtCore import QObject, pyqtSignal
from app.common.config import VERSION, BETA
from app.common.logger import logger

TAG = "UpdateChecker"

# 推送地址（自己的服务器，无缓存，改完立刻生效）
NOTICE_URL = "http://154.12.94.96:99/notice.json"

# 请求超时（秒）
TIMEOUT = 8


class UpdateChecker(QObject):
    """检查更新/推送通知，通过信号通知主窗口弹窗"""
    # 发现新版本: title, content, url, password
    updateAvailable = pyqtSignal(str, str, str, str)
    # 当前已是最新版本
    noUpdate = pyqtSignal()
    # 检查失败（网络等）
    checkFailed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

    async def check(self):
        """异步检查，通过信号通知结果"""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    NOTICE_URL,
                    timeout=aiohttp.ClientTimeout(total=TIMEOUT),
                    ssl=False
                ) as resp:
                    if resp.status != 200:
                        logger.info(f"Update check: HTTP {resp.status}", TAG)
                        self.checkFailed.emit(f"服务器返回 {resp.status}")
                        return
                    # 优先用 Content-Type 里的 charset，否则按 utf-8 解码（避免中文乱码）
                    text = await resp.text(encoding="utf-8")
                    data = json.loads(text)

            # 推送开关
            if not data.get("enabled", True):
                logger.info("Update check: disabled by notice.json", TAG)
                self.noUpdate.emit()
                return

            # 对比版本号
            latest = data.get("latestVersion", "").strip()
            current = (BETA or VERSION).strip()
            if not latest or latest == current:
                logger.info(
                    f"Update check: same version ({current})", TAG)
                self.noUpdate.emit()
                return

            # 新版本更高 → 弹窗
            title = data.get("title", "发现新版本").replace(
                "{latest}", latest).replace("{current}", current)
            content = data.get(
                "content",
                f"Seraphine {latest} 已发布，点击立即下载。").replace(
                "{latest}", latest).replace("{current}", current)
            url = data.get("url", "")
            password = data.get("password", "")

            logger.info(
                f"Update check: new version {latest} (current {current})",
                TAG)
            self.updateAvailable.emit(title, content, url, password)

        except asyncio.TimeoutError:
            logger.info("Update check: timeout (network)", TAG)
            self.checkFailed.emit("网络超时，请检查网络连接")
        except json.JSONDecodeError as e:
            logger.info(f"Update check: invalid JSON ({e})", TAG)
            self.checkFailed.emit("服务器返回数据格式错误")
        except Exception as e:
            logger.info(f"Update check: failed ({e})", TAG)
            self.checkFailed.emit(f"检查失败：{e}")
