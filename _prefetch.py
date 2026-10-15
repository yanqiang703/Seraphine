# coding: utf-8
"""一次性预下载全部 DDragon 数据到 app/resource/game/liveclient，供打包离线使用。"""
import asyncio
import os

os.chdir(os.path.dirname(os.path.abspath(__file__)))

from app.lol.live_client import liveClient


async def main():
    await liveClient.ensure_data()
    print("version =", liveClient._version)

    champions = liveClient._champion_data.get("data", {})
    print("champions =", len(champions))

    ok = 0
    for key in champions:
        full = await liveClient._load_champion_full(key)
        spells = (full.get("data") or {}).get(key, {}).get("spells") or []
        icon = await liveClient.get_ultimate_icon(key)
        if spells and "champion-0.png" not in icon:
            ok += 1
        else:
            print("ULT FAIL", key, icon)
    print(f"ult ok = {ok}/{len(champions)}")

    summoners = liveClient._summoner_data.get("data", {})
    sok = 0
    for key in summoners:
        icon = await liveClient.get_summoner_icon(key)
        if "champion-0.png" not in icon:
            sok += 1
        else:
            print("SUM FAIL", key)
    print(f"summoner ok = {sok}/{len(summoners)}")

    await liveClient.close()
    print("DONE")


asyncio.run(main())