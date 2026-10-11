'use strict';

// Seraphine 在线统计 Worker
// 路由：
//   POST /heartbeat   客户端心跳（Header: X-Report-Key）
//   GET  /            后台页面（Cookie 鉴权）
//   GET  /api/stats   统计数据 JSON（Cookie 鉴权）
//   GET  /api/history 近 14 天快照 JSON（Cookie 鉴权）
//   POST /api/login   登录
//   GET  /logout      登出
//
// 需要的环境变量（Worker 设置 → Variables and Secrets）：
//   REPORT_KEY  客户端上报密钥（与 app/common/stats_reporter.py 一致）
//   ADMIN_PASS  后台登录密码（建议用随机长字符串）
// 需要的 D1 绑定：DB（执行 stats_worker/schema.sql 建表）
// 需要的 Cron：17 0 * * *（每天 UTC 00:17 写一条快照）

const ONLINE_WINDOW = 180; // 3 分钟内有心跳算在线
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

const json = (data, status = 200) =>
  new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json; charset=utf-8' },
  });

function getCookie(request, name) {
  const raw = request.headers.get('cookie') || '';
  const m = new RegExp(`(?:^|; )${name}=([^;]*)`).exec(raw);
  return m ? decodeURIComponent(m[1]) : null;
}

function isAuthed(request, env) {
  return !!env.ADMIN_PASS && getCookie(request, 'sp_auth') === env.ADMIN_PASS;
}

const authCookie = (pass) =>
  `sp_auth=${encodeURIComponent(pass)}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=604800`;

async function getStats(env) {
  const now = Math.floor(Date.now() / 1000);
  const onlineCut = now - ONLINE_WINDOW;
  const dayStart = now - (now % 86400); // UTC 零点

  const [counts, versions] = await Promise.all([
    env.DB.prepare(
      `SELECT
         (SELECT COUNT(*) FROM clients WHERE last_seen >= ?1) AS online,
         (SELECT COUNT(*) FROM clients WHERE last_seen >= ?2) AS active,
         (SELECT COUNT(*) FROM clients)                        AS installs`
    ).bind(onlineCut, dayStart).first(),
    env.DB.prepare(
      `SELECT version, COUNT(*) AS c
       FROM clients WHERE last_seen >= ?1
       GROUP BY version ORDER BY c DESC`
    ).bind(onlineCut).all(),
  ]);

  return {
    online: counts?.online ?? 0,
    todayActive: counts?.active ?? 0,
    installs: counts?.installs ?? 0,
    versions: versions?.results ?? [],
    serverTime: now,
  };
}

function loginPage(error) {
  return new Response(`<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Seraphine 统计后台</title>
<style>
  body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;
       background:#1b1b1b;color:#f2f2f2;font-family:"Microsoft YaHei",system-ui,sans-serif}
  .card{background:#2b2b2b;border-radius:12px;padding:36px 32px;width:300px;
        box-shadow:0 8px 32px rgba(0,0,0,.4)}
  h1{font-size:18px;margin:0 0 24px;text-align:center}
  input{width:100%;box-sizing:border-box;padding:10px 12px;border-radius:8px;border:1px solid #444;
        background:#1f1f1f;color:#f2f2f2;font-size:14px;margin-bottom:16px}
  button{width:100%;padding:10px;border:none;border-radius:8px;background:#0078d4;color:#fff;
         font-size:14px;cursor:pointer}
  button:hover{background:#1a86d9}
  .err{color:#ff6b6b;font-size:13px;margin-bottom:12px;text-align:center;min-height:18px}
</style></head><body>
<form class="card" method="post" action="/api/login">
  <h1>Seraphine 统计后台</h1>
  <div class="err">${error || ''}</div>
  <input name="password" type="password" placeholder="后台密码" autofocus required>
  <button type="submit">登 录</button>
</form></body></html>`, {
    status: error ? 401 : 200,
    headers: { 'content-type': 'text/html; charset=utf-8' },
  });
}

function dashboardPage() {
  return new Response(`<!doctype html>
<html lang="zh"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Seraphine 统计后台</title>
<style>
  *{box-sizing:border-box}
  body{margin:0;background:#1b1b1b;color:#f2f2f2;
       font-family:"Microsoft YaHei",system-ui,sans-serif;padding:28px}
  .head{display:flex;align-items:center;justify-content:space-between;margin-bottom:24px}
  h1{font-size:20px;margin:0}
  .muted{color:#999;font-size:13px}
  a{color:#4cc2ff;text-decoration:none}
  .cards{display:flex;gap:18px;flex-wrap:wrap;margin-bottom:26px}
  .card{background:#2b2b2b;border-radius:12px;padding:22px 26px;min-width:170px;flex:1;
        box-shadow:0 4px 16px rgba(0,0,0,.25)}
  .num{font-size:40px;font-weight:700;line-height:1.1}
  .num.green{color:#4ecb71}.num.blue{color:#4cc2ff}.num.purple{color:#b18cff}
  .lbl{color:#aaa;font-size:13px;margin-top:6px}
  .panel{background:#2b2b2b;border-radius:12px;padding:20px 24px;margin-bottom:20px}
  .panel h2{font-size:15px;margin:0 0 14px;color:#ddd}
  table{border-collapse:collapse;width:100%;font-size:14px}
  td,th{padding:7px 10px;text-align:left;border-bottom:1px solid #383838}
  th{color:#999;font-weight:400}
  .bars{display:flex;align-items:flex-end;gap:6px;height:130px;margin-top:10px}
  .bar{flex:1;background:linear-gradient(180deg,#4cc2ff,#2b7fb8);border-radius:4px 4px 0 0;
       min-height:2px;position:relative}
  .bar span{position:absolute;top:-18px;left:50%;transform:translateX(-50%);
            font-size:11px;color:#aaa;white-space:nowrap}
  .bar i{position:absolute;bottom:-20px;left:50%;transform:translateX(-50%);
         font-style:normal;font-size:10px;color:#777;white-space:nowrap}
  .chart{padding-bottom:28px}
</style></head><body>
<div class="head">
  <h1>Seraphine 统计后台</h1>
  <div><span class="muted" id="updated">加载中…</span> &nbsp; <a href="/logout">退出</a></div>
</div>
<div class="cards">
  <div class="card"><div class="num green" id="online">-</div><div class="lbl">当前在线（近 3 分钟）</div></div>
  <div class="card"><div class="num blue" id="active">-</div><div class="lbl">今日活跃（UTC）</div></div>
  <div class="card"><div class="num purple" id="installs">-</div><div class="lbl">累计安装</div></div>
</div>
<div class="panel"><h2>在线版本分布</h2><table id="verTable"><tbody><tr><td colspan="2" class="muted">加载中…</td></tr></tbody></table></div>
<div class="panel chart"><h2>近 14 天在线快照（每日 UTC 00:17）</h2><div class="bars" id="bars"></div></div>
<script>
async function refresh(){
  try{
    const [s, h] = await Promise.all([
      fetch('/api/stats').then(r=>r.json()),
      fetch('/api/history').then(r=>r.json())
    ]);
    online.textContent = s.online;
    active.textContent = s.todayActive;
    installs.textContent = s.installs;
    updated.textContent = '更新于 ' + new Date().toLocaleTimeString();
    verTable.innerHTML = s.versions.length
      ? s.versions.map(v=>'<tr><td>v'+v.version+'</td><td>'+v.c+' 人</td></tr>').join('')
      : '<tr><td colspan="2" class="muted">当前无人在线</td></tr>';
    const max = Math.max(1, ...h.map(x=>x.online));
    bars.innerHTML = h.slice().reverse().map(x=>{
      const hgt = Math.round(x.online/max*100);
      const d = x.day.slice(5);
      return '<div class="bar" style="height:'+hgt+'%"><span>'+x.online+'</span><i>'+d+'</i></div>';
    }).join('');
  }catch(e){ updated.textContent = '刷新失败：'+e; }
}
refresh();
setInterval(refresh, 30000);
</script></body></html>`, {
    headers: { 'content-type': 'text/html; charset=utf-8' },
  });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const { pathname } = url;

    // ---------- 客户端心跳 ----------
    if (pathname === '/heartbeat' && request.method === 'POST') {
      if (!env.REPORT_KEY || request.headers.get('x-report-key') !== env.REPORT_KEY) {
        return json({ ok: false, error: 'bad key' }, 403);
      }
      let body;
      try {
        body = await request.json();
      } catch {
        return json({ ok: false, error: 'bad json' }, 400);
      }
      const id = String(body.id || '');
      const v = String(body.v || '').slice(0, 20);
      if (!UUID_RE.test(id)) return json({ ok: false, error: 'bad id' }, 400);

      const now = Math.floor(Date.now() / 1000);
      await env.DB.prepare(
        `INSERT INTO clients (id, version, first_seen, last_seen)
         VALUES (?1, ?2, ?3, ?3)
         ON CONFLICT(id) DO UPDATE SET last_seen = excluded.last_seen,
                                       version = excluded.version`
      ).bind(id, v, now).run();
      return json({ ok: true });
    }

    // ---------- 登录 / 登出 ----------
    if (pathname === '/api/login' && request.method === 'POST') {
      const form = await request.formData();
      if (form.get('password') !== env.ADMIN_PASS || !env.ADMIN_PASS) {
        return loginPage('密码错误');
      }
      return new Response(null, {
        status: 302,
        headers: { location: '/', 'set-cookie': authCookie(env.ADMIN_PASS) },
      });
    }
    if (pathname === '/logout') {
      return new Response(null, {
        status: 302,
        headers: { location: '/', 'set-cookie': 'sp_auth=; Path=/; Max-Age=0' },
      });
    }

    // ---------- 后台（需登录） ----------
    if (!isAuthed(request, env)) return loginPage();

    if (pathname === '/api/stats') return json(await getStats(env));

    if (pathname === '/api/history') {
      const rows = await env.DB.prepare(
        `SELECT day, online, active, installs FROM snapshots
         ORDER BY day DESC LIMIT 14`
      ).all();
      return json(rows.results || []);
    }

    if (pathname === '/') return dashboardPage();

    return new Response('Not Found', { status: 404 });
  },

  // ---------- 每日快照（Cron 触发） ----------
  async scheduled(event, env) {
    const stats = await getStats(env);
    const day = new Date().toISOString().slice(0, 10);
    await env.DB.prepare(
      `INSERT INTO snapshots (day, online, active, installs)
       VALUES (?1, ?2, ?3, ?4)
       ON CONFLICT(day) DO NOTHING`
    ).bind(day, stats.online, stats.todayActive, stats.installs).run();

    // 只保留 365 天快照
    await env.DB.prepare(`DELETE FROM snapshots WHERE day < date('now', '-365 day')`).run();
  },
};
