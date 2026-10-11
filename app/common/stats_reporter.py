# coding:utf-8
"""
匿名使用统计上报（心跳），用于作者在后台查看在线人数。

隐私说明：
- 仅在本地生成一个随机 UUID 作为匿名标识，不收集游戏账号、昵称、IP 等任何信息
- 所有网络请求静默失败，断网/服务不可用绝不影响软件正常使用
"""
import asyncio
import json
import os
import uuid

import aiohttp

from app.common.config import VERSION, LOCAL_PATH
from app.common.logger import logger

# 心跳服务地址（部署 Worker 后替换为实际的 workers.dev 地址）
REPORT_URL = "https://seraphine-stats.example.workers.dev/heartbeat"

# 上报密钥，需与 Cloudflare Worker 环境变量 REPORT_KEY 完全一致
REPORT_KEY = "Seraphine-Heartbeat-2026"

HEARTBEAT_INTERVAL = 90  # 秒；服务端按近 3 分钟判定在线
REQUEST_TIMEOUT = 8

_clientId = None
_task = None


def getClientId() -> str:
    """ 读取（首次运行时生成并持久化）匿名客户端 ID """
    global _clientId
    if _clientId:
        return _clientId

    path = os.path.join(LOCAL_PATH, ".install_id")
    try:
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                value = f.read().strip()
                if value:
                    _clientId = value
                    return _clientId

        _clientId = str(uuid.uuid4())
        with open(path, "w", encoding="utf-8") as f:
            f.write(_clientId)
    except Exception:
        # 文件不可写时退化为每次随机（仅影响统计准确性）
        _clientId = str(uuid.uuid4())

    return _clientId


async def __sendOnce(session: aiohttp.ClientSession):
    payload = {"id": getClientId(), "v": VERSION}
    async with session.post(
        REPORT_URL,
        data=json.dumps(payload),
        headers={
            "Content-Type": "application/json",
            "X-Report-Key": REPORT_KEY,
        },
        timeout=aiohttp.ClientTimeout(total=REQUEST_TIMEOUT),
    ) as resp:
        await resp.read()


async def __run():
    # trust_env=True：国内网络环境下自动走系统代理（Clash 等）访问 workers.dev
    async with aiohttp.ClientSession(trust_env=True) as session:
        while True:
            try:
                await __sendOnce(session)
            except asyncio.CancelledError:
                raise
            except Exception as e:
                # 静默处理，仅写本地日志，不给用户任何弹窗
                logger.debug(f"heartbeat failed: {e}")

            try:
                await asyncio.sleep(HEARTBEAT_INTERVAL)
            except asyncio.CancelledError:
                raise


def startStatsReporter():
    """ 在 qasync 事件循环中启动心跳协程 """
    global _task
    if _task is None:
        _task = asyncio.ensure_future(__run())
        logger.info("Stats reporter started", "Stats")
    return _task
