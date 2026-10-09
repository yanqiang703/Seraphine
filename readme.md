<div align="center">

# Seraphine

基于 LCU API 实现的英雄联盟辅助工具

</div>

## 快速上手 🤗

### 直接安装（推荐）

前往 [Releases](https://github.com/yanqiang703/Seraphine/releases) 页面下载 `SeraphineSetup_2.0.exe`，双击运行安装向导，按提示完成安装（自动创建桌面和开始菜单快捷方式）。

### 或通过本地构建

下载项目源码 `zip` 压缩包解压至文件夹或通过 `git`：

```shell
git clone https://github.com/yanqiang703/Seraphine.git
cd Seraphine
```

创建并激活新的虚拟环境（Python 3.12）

```shell
conda create -n seraphine python=3.12
conda activate seraphine
```

安装依赖

```shell
pip install -r requirements.txt
```

运行 `main.py` 开始使用

```shell
python main.py
```

### 卸载 Seraphine 😑

通过控制面板或"开始菜单 → 卸载 Seraphine"卸载即可，再删除 `%AppData%/Seraphine` 文件夹清理个人配置。

## 功能一览 🥰

- 战绩查询功能
  - 同大区召唤师战绩查询 ✅
  - 进入 BP 后自动查队友战绩 ✅
  - 进入游戏后自动查对手战绩 ✅
  - 段位显示中文段位名 + 图标 ✅

- Mini 悬浮窗
  - 进房间自动弹出、退房间自动隐藏 ✅
  - 英雄选择显示备战席、可点击换英雄 ✅
  - 自动接受对局 ✅
  - 自动匹配（支持 0-30 秒可编辑延迟）✅

- 其他辅助功能
  - 自动 B/P
    - 找到对局后自动接受对局 ✅
    - 进入英雄选择后自动选择英雄 ✅
    - 进入禁用环节时自动禁用英雄 ✅
    - 自动接受来自队友的交换英雄 / 楼层请求 ✅

  - 外部数据显示
    - 自动显示大乱斗英雄 Buff 信息 ✅
    - 自动显示 OPGG 英雄排行 ✅
    - 自动显示 OPGG 英雄出装加点，一键设置符文 ✅

  - 游戏功能
    - 创建 5v5 自定义训练模式房间 ✅
    - 观战同大区玩家正在进行的游戏 ✅
    - 锁定游戏内设置 ✅

  - 客户端功能
    - 退出后自动重新连接 ✅
    - 修复客户端结算时无限加载和缩成一块 ✅
    - 热重启客户端 ✅

  - 个性化功能
    - 修改个人主页背景 ✅
    - 修改个人在线状态 ✅
    - 修改个人签名 ✅
    - 修改个人状态卡片中的段位显示 ✅
    - 一键卸下勋章 ✅
    - 一键卸下头像框 ✅

  - 工具箱
    - 领取工具 ✅
    - 好友工具 ✅

## 常见问题 FAQ 🧐

### Q：我会因为使用 Seraphine 而被封号吗 😨？

由于本程序的功能**完全**基于英雄联盟客户端 API 实现，**不含任何**对客户端以及游戏文件本体、代码以及内存的读取或破坏其完整性的行为（详情见下方免责声明）。因此仅使用 Seraphine 时极大概率不会被封号，但**并不保证**一定不会封号。

### Q：真的被封号了怎么办？

申诉或等待解封吧 😭

### Q：为什么客户端无法连接 / 功能无法使用 / 生涯界面无限转圈 / 最新战绩更新有延迟？

Seraphine 提供的战绩查询相关功能的数据均是由英雄联盟客户端接口所提供的，程序只是负责将它们显示出来。所以如果遇到功能无法使用或数据更新有延迟的情况，原因基本出在英雄联盟服务器本身，与 Seraphine 大概率没啥关系~

### Q：为什么不提供具体某模式 / 某英雄总场次以及总胜率？

英雄联盟客户端没有提供相关数据接口，做不到哇~

## 帮助我们改进 Seraphine 😘

在您的使用过程中，如果遇到程序的任何 BUG 或不符合预期的行为，欢迎提出 [issue](https://github.com/yanqiang703/Seraphine/issues)。

如果您有功能上的添加或修改建议，也非常欢迎提出 issue 进行讨论！[PR](https://github.com/yanqiang703/Seraphine/pulls) 也大欢迎！

## 您也可以自己打包 📂

### 打包可执行文件

在虚拟环境下安装 `PyInstaller`，执行项目中的 `make.ps1` 脚本：

```shell
pip install pyinstaller
.\make.ps1
```

### 制作安装器

使用 [Inno Setup 6](https://jrsoftware.org/isdl.php) 编译项目根目录的 `installer.iss`，得到 `SeraphineSetup_2.0.exe` 安装包。

## Riot 声明 📢

Seraphine is not endorsed by Riot Games and does not reflect the views or opinions of Riot Games or anyone officially involved in producing or managing Riot Games properties. Riot Games and all associated properties are trademarks or registered trademarks of Riot Games, Inc

**参考译文**：Seraphine 未经 Riot Games 认可，也不代表 Riot Games 或任何官方参与制作或管理 Riot Games 产品的人的观点或意见。Riot Games 及其所有相关产物均为 Riot Games，Inc 的商标或注册商标。

## 免责声明 🛡️

1. 本程序的目的是通过为游戏玩家提供**游戏外**辅助功能，从而给玩家提供更好的游戏体验。我们不鼓励不支持任何违反 Riot 以及腾讯规定或任何可能导致游戏环境不公平的行为。
2. 本程序的代码实现遵守 Riot Policies 的规定，提供的功能符合《英雄联盟》游戏插件公约的要求。
3. 本程序是基于 Riot 提供的 League Client Update（LCU）API 开发的工具，其代码与行为均不含任何侵入性的手段，因此在理论上并不会做出任何破坏客户端以及游戏完整性的行为，包括但不限于客户端文件内容的修改或游戏进程内存的读写等。
4. 在具体的游戏环境以及 Riot 或腾讯提供的服务更新的过程中（如反作弊系统或其他保护手段的更新），使用本程序可能会对您的游戏体验产生负面影响，如客户端崩溃、账号封禁等。
5. 使用本程序所产生的一切后果将由您自行承担，我们不对因使用本程序而产生的任何直接或间接损失负责，用户在决定使用本程序时，应充分考虑并自行承担由此产生的所有风险和后果。
6. 我们保留随时修改本免责声明的权利，请定期查阅此页面以获取最新信息。

在您使用本程序之前，请确保您已经详细**阅读**、**理解**并**同意**免责声明中的条款；同时，请遵守相关游戏规则，共同维护健康和公平的游戏环境。

## 许可证 ⚖️

- 对于非商用行为，Seraphine 使用 GPLv3 许可证（详见 LICENSE 文件）。
- 禁止一切针对代码以及二进制文件的商用行为。
