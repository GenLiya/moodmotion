// 推送前密钥反扫：有任何命中就绝不推送
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';

const ROOT = process.argv[2] || '.';
const SKIP_DIRS = new Set(['__pycache__', '.git', 'node_modules', '.pytest_cache', 'build', 'dist', '.venv']);
const SKIP_EXT = new Set(['.pyc', '.png', '.jpg', '.jpeg', '.gif', '.webp', '.zip', '.whl']);

// 高危模式：真实密钥的形态
const PATTERNS = [
  [/\bsk-[A-Za-z0-9_-]{16,}/g, '疑似 OpenAI/DeepSeek 风格密钥 sk-...'],
  [/\bsk-cp-[A-Za-z0-9_-]{10,}/g, 'MiniMax 订阅 key sk-cp-...'],
  [/\bsk-api-[A-Za-z0-9_-]{10,}/g, 'MiniMax 标准 key sk-api-...'],
  [/eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}/g, '疑似 JWT'],
  [/gh[pousr]_[A-Za-z0-9]{20,}/g, 'GitHub token'],
  [/AKIA[0-9A-Z]{16}/g, 'AWS access key id'],
  [/xox[baprs]-[A-Za-z0-9-]{10,}/g, 'Slack token'],
  [/(api[_-]?key|apikey|secret|token|password|passwd|私钥)\s*[:=]\s*["'][^"'\s]{8,}["']/gi, '硬编码凭据赋值'],
  [/Bearer\s+[A-Za-z0-9._-]{20,}/g, 'Bearer 令牌'],
];

const files = [];
(function walk(dir) {
  for (const e of readdirSync(dir)) {
    const p = join(dir, e);
    const st = statSync(p);
    if (st.isDirectory()) { if (!SKIP_DIRS.has(e)) walk(p); continue; }
    if (SKIP_EXT.has(e.slice(e.lastIndexOf('.')))) continue;
    files.push(p);
  }
})(ROOT);

let hits = 0;
const scanned = [];
for (const f of files) {
  let text;
  try { text = readFileSync(f, 'utf8'); } catch { continue; }
  scanned.push(relative(ROOT, f));
  for (const [re, label] of PATTERNS) {
    const found = text.match(re);
    if (found) {
      for (const m of [...new Set(found)].slice(0, 4)) {
        hits++;
        const shown = m.length > 42 ? m.slice(0, 20) + '…' + m.slice(-8) : m;
        console.log(`❌ ${relative(ROOT, f)}  [${label}]  ${shown}`);
      }
    }
  }
}

// 额外：确认没有任何 .env / 凭据类文件混进来
// ⚠️ 允许清单：本扫描器自己的文件名含 "secret"，否则它会自我误报（实测踩过）。
const ALLOW = [/scan_secrets/i, /scanner/i];
const risky = scanned.filter((p) =>
  /(^|[\\/])\.env|cred|secret|\.pem$|\.key$/i.test(p) && !ALLOW.some((re) => re.test(p)));
if (risky.length) { console.log('❌ 疑似凭据文件在树里:', risky.join(', ')); hits += risky.length; }

console.log(`\n扫描 ${scanned.length} 个文件，命中 ${hits} 处`);
console.log(hits === 0 ? '✅ 反扫通过：0 命中，可以推送' : '⛔ 有命中，禁止推送');
process.exit(hits === 0 ? 0 : 1);
