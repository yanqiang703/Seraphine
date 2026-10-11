-- Seraphine 在线统计 D1 数据库表结构
-- 在 Cloudflare 控制台 D1 数据库的 Console 中执行一次即可

CREATE TABLE IF NOT EXISTS clients (
  id         TEXT PRIMARY KEY,   -- 客户端随机匿名 UUID
  version    TEXT,               -- 软件版本号
  first_seen INTEGER NOT NULL,   -- 首次心跳时间（Unix 秒）
  last_seen  INTEGER NOT NULL    -- 最后心跳时间（Unix 秒）
);

CREATE INDEX IF NOT EXISTS idx_clients_last_seen ON clients(last_seen);

-- 每天一条快照，由 Worker 的定时任务自动写入
CREATE TABLE IF NOT EXISTS snapshots (
  day      TEXT PRIMARY KEY,     -- UTC 日期 YYYY-MM-DD
  online   INTEGER NOT NULL,     -- 快照时在线人数
  active   INTEGER NOT NULL,     -- 快照时当日活跃
  installs INTEGER NOT NULL      -- 快照时累计安装
);
