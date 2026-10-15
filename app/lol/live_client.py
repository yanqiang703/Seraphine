# coding: utf-8
"""Live Client API 与 DDragon 数据提供者。

Live Client API 仅在 LOL 对局进行中可用（https://127.0.0.1:2999），
提供本局所有玩家（含敌方）的召唤师技能、英雄等信息。
DDragon 提供召唤师技能与英雄大招的冷却时间及图标。

数据全部缓存到 app/resource/game/liveclient/ 下，避免每次重复下载。
"""
import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import aiohttp

from app.common.logger import logger

TAG = "LiveClient"

LIVE_CLIENT_URL = "https://127.0.0.1:2999/liveclientdata/allgamedata"

DDRAGON_VER_URL = "https://ddragon.leagueoflegends.com/api/versions.json"
DDRAGON_SUMMONER_URL = "https://ddragon.leagueoflegends.com/cdn/{ver}/data/en_US/summoner.json"
DDRAGON_CHAMPION_URL = "https://ddragon.leagueoflegends.com/cdn/{ver}/data/en_US/champion.json"
DDRAGON_CHAMPION_FULL_URL = "https://ddragon.leagueoflegends.com/cdn/{ver}/data/en_US/champion/{name}.json"
DDRAGON_SPELL_ICON_URL = "https://ddragon.leagueoflegends.com/cdn/{ver}/img/spell/{name}"

CACHE_ROOT = "app/resource/game/liveclient"
SUMMONER_CACHE = os.path.join(CACHE_ROOT, "summoner.json")
CHAMPION_CACHE = os.path.join(CACHE_ROOT, "champion.json")
CHAMPION_FULL_DIR = os.path.join(CACHE_ROOT, "champions")
SUMMONER_ICON_DIR = os.path.join(CACHE_ROOT, "summoners")
ULT_ICON_DIR = os.path.join(CACHE_ROOT, "ultimates")

# 大招(R)冷却默认取满级（cooldown 数组末位）
ULT_LEVEL_INDEX = -1


@dataclass
class EnemyInfo:
    """一名敌方玩家的关键信息。"""
    champion_name: str                       # DDragon / LCU 英雄 key，如 "Ahri"
    summoner_spells: List[str] = field(default_factory=list)  # rawDisplayName，如 "SummonerFlash"


class LiveClientDataProvider:
    """从 Live Client API 抓取对局敌方信息，并经由 DDragon 提供冷却/图标。"""

    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._summoner_data: Dict = {}
        self._champion_data: Dict = {}
        self._version: str = ""

    # ------------------------------------------------------------------
    # Session
    # ------------------------------------------------------------------
    async def ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False))
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    # ------------------------------------------------------------------
    # 对局数据
    # ------------------------------------------------------------------
    async def fetch_enemy_players(self) -> Optional[List[EnemyInfo]]:
        """返回本局敌方玩家列表；当前不在对局（连接失败/无数据）时返回 None。"""
        try:
            session = await self.ensure_session()
            async with session.get(LIVE_CLIENT_URL, timeout=1.5) as resp:
                if resp.status != 200:
                    return None
                data = await resp.json()
        except Exception:
            return None

        if not data:
            return None

        all_players = data.get("allPlayers") or []
        active = data.get("activePlayer") or {}
        my_name = active.get("summonerName")

        # 在完整玩家列表中确定己方队伍
        my_team = None
        if my_name:
            for p in all_players:
                if p.get("summonerName") == my_name:
                    my_team = p.get("team")
                    break
        if not my_team:
            my_team = active.get("team", "ORDER")

        enemies: List[EnemyInfo] = []
        for p in all_players:
            if p.get("team") == my_team:
                continue

            spells = p.get("summonerSpells") or {}
            spells_list = [
                (spells.get("summonerSpellOne") or {}).get("rawDisplayName", ""),
                (spells.get("summonerSpellTwo") or {}).get("rawDisplayName", ""),
            ]
            spells_list = [s for s in spells_list if s]

            enemies.append(EnemyInfo(
                champion_name=self._extract_champion_name(p),
                summoner_spells=spells_list,
            ))

        return enemies

    @staticmethod
    def _extract_champion_name(player: Dict) -> str:
        name = player.get("championName") or player.get("rawChampionName") or ""
        # rawChampionName 形如 "Gameplay_Champion_Ahri"，取最后一段
        key = name.split("_")[-1] if "_" in name else name
        # 去掉常见的装饰前缀
        for prefix in ("Champion", "Hero"):
            if key.startswith(prefix) and len(key) > len(prefix):
                key = key[len(prefix):]
        return key or "Unknown"

    # ------------------------------------------------------------------
    # DDragon 数据加载（懒加载 + 本地缓存）
    # ------------------------------------------------------------------
    async def ensure_data(self):
        """确保 champion.json 与 summoner.json 已就绪。"""
        if self._champion_data and self._summoner_data:
            return

        os.makedirs(CHAMPION_FULL_DIR, exist_ok=True)
        os.makedirs(SUMMONER_ICON_DIR, exist_ok=True)
        os.makedirs(ULT_ICON_DIR, exist_ok=True)

        version = await self._get_version()
        if not version:
            return
        self._version = version

        self._summoner_data = await self._load_json(
            SUMMONER_CACHE, DDRAGON_SUMMONER_URL.format(ver=version))
        self._champion_data = await self._load_json(
            CHAMPION_CACHE, DDRAGON_CHAMPION_URL.format(ver=version))

    async def _get_version(self) -> str:
        try:
            session = await self.ensure_session()
            async with session.get(DDRAGON_VER_URL, timeout=3) as resp:
                if resp.status == 200:
                    return (await resp.json())[0]
        except Exception as e:
            logger.warning(f"获取 DDragon 版本失败: {e}", TAG)
        return ""

    async def _load_json(self, cache_path: str, url: str) -> Dict:
        if os.path.exists(cache_path):
            try:
                with open(cache_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        try:
            session = await self.ensure_session()
            async with session.get(url, timeout=8) as resp:
                if resp.status != 200:
                    return {}
                data = await resp.json()
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f)
            return data
        except Exception as e:
            logger.warning(f"加载 DDragon 数据失败 {url}: {e}", TAG)
            return {}

    async def _load_champion_full(self, key: str) -> Dict:
        """加载单个英雄的完整数据（champion/{key}.json），含 spells 数组。"""
        if not key or not self._version:
            return {}
        path = os.path.join(CHAMPION_FULL_DIR, f"{key}.json")
        return await self._load_json(
            path, DDRAGON_CHAMPION_FULL_URL.format(ver=self._version, name=key))

    async def _get_ultimate_spell(self, champion_name: str) -> Optional[Dict]:
        """返回大招(R)的 spell 数据（spells[3]）。"""
        key = self._find_champion_key(champion_name)
        if not key:
            return None
        info = await self._load_champion_full(key)
        champion = (info.get("data") or {}).get(key) or {}
        spells = champion.get("spells") or []
        if len(spells) < 4:
            return None
        return spells[3]

    # ------------------------------------------------------------------
    # 冷却时间
    # ------------------------------------------------------------------
    async def get_ultimate_cd(self, champion_name: str) -> Optional[int]:
        spell = await self._get_ultimate_spell(champion_name)
        if not spell:
            return None
        cooldowns = spell.get("cooldown") or []
        if not cooldowns:
            return None
        idx = ULT_LEVEL_INDEX if abs(ULT_LEVEL_INDEX) <= len(cooldowns) else 0
        return int(cooldowns[idx])

    def get_summoner_cd(self, raw_name: str) -> Optional[int]:
        key = self._find_summoner_key(raw_name)
        if not key:
            return None
        cooldowns = self._summoner_data.get("data", {}).get(key, {}).get("cooldown") or []
        return int(cooldowns[0]) if cooldowns else None

    def get_summoner_id(self, raw_name: str) -> Optional[int]:
        """返回召唤师技能的数字 id（LCU 图标缓存命名用的 key）。"""
        key = self._find_summoner_key(raw_name)
        if not key:
            return None
        entry = self._summoner_data.get("data", {}).get(key, {})
        try:
            return int(entry.get("key"))
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # 图标
    # ------------------------------------------------------------------
    async def get_ultimate_icon(self, champion_name: str) -> str:
        key = self._find_champion_key(champion_name) or champion_name
        spell = await self._get_ultimate_spell(champion_name)
        img_name = ""
        if spell:
            img_name = (spell.get("image") or {}).get("full", "")

        return await self._download_icon(ULT_ICON_DIR, key, img_name)

    async def get_summoner_icon(self, raw_name: str) -> str:
        key = self._find_summoner_key(raw_name)
        img_name = ""
        if key:
            entry = self._summoner_data.get("data", {}).get(key, {})
            img_name = (entry.get("image") or {}).get("full", "")

        return await self._download_icon(
            SUMMONER_ICON_DIR, raw_name, img_name)

    async def _download_icon(self, folder: str, cache_name: str, ddragon_img: str) -> str:
        path = os.path.join(folder, f"{cache_name}.png")
        if os.path.exists(path):
            return path

        if ddragon_img and self._version:
            url = DDRAGON_SPELL_ICON_URL.format(
                ver=self._version, name=ddragon_img)
            try:
                session = await self.ensure_session()
                async with session.get(url, timeout=8) as resp:
                    if resp.status == 200:
                        with open(path, "wb") as f:
                            f.write(await resp.read())
                        return path
            except Exception as e:
                logger.warning(f"下载图标失败 {url}: {e}", TAG)

        return "app/resource/images/champion-0.png"

    # ------------------------------------------------------------------
    # 名称匹配辅助
    # ------------------------------------------------------------------
    def _find_champion(self, name: str) -> Optional[Dict]:
        champions = self._champion_data.get("data") or {}
        if not name:
            return None
        if name in champions:
            return champions[name]
        lower = name.lower()
        for key, info in champions.items():
            if key.lower() == lower:
                return info
        return None

    def _find_champion_key(self, name: str) -> Optional[str]:
        """返回 champion.json 中的英雄 key（即 DDragon 完整数据 URL 所用的 id）。"""
        champions = self._champion_data.get("data") or {}
        if not name:
            return None
        if name in champions:
            return name
        lower = name.lower()
        for key, info in champions.items():
            if (key.lower() == lower
                    or (info.get("name") or "").lower() == lower
                    or (info.get("id") or "").lower() == lower):
                return key
        return None

    def _find_summoner_key(self, raw_name: str) -> Optional[str]:
        data = self._summoner_data.get("data") or {}
        if raw_name in data:
            return raw_name
        lower = raw_name.lower()
        for key in data:
            if key.lower() == lower:
                return key
        return None


# 全局单例，供界面层复用
liveClient = LiveClientDataProvider()