// 核对 README 里的 demo 输出块与真实运行结果是否一致（README 不能是编的）
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';

const ROOT = 'E:\\person\\important\\openclaw\\AI项目\\moodmotion';

// 真实输出（用 UTF-8 环境，避免控制台编码破坏破折号）
const real = execFileSync('py', ['-3', '-m', 'moodmotion.cli', 'demo'],
  { cwd: ROOT, encoding: 'utf8', env: { ...process.env, PYTHONIOENCODING: 'utf-8' } });

const readme = readFileSync(`${ROOT}\\README.md`, 'utf8');
const m = readme.match(/```\n\$ python -m moodmotion\.cli demo\n\n([\s\S]*?)```/);
if (!m) { console.log('❌ README 里没找到 demo 代码块'); process.exit(1); }
const claimed = m[1].trimEnd().split('\n');

const realLines = real.split('\n')
  .filter((l) => /^\s*(d\d |clock|--|\s*$)/.test(l) && l.trim() !== '')
  .map((l) => l.trimEnd());

// 只比对 README 声称的那些行
// 与 sync 脚本保持同一套归一化：只去行尾 \r，**保留空行**（分组标题靠空行分隔）
const realSet = new Set(real.split('\n').map((l) => l.replace(/\r$/, '').trimEnd()));
let bad = 0;
for (const line of claimed) {
  const key = line.trimEnd();
  if (!realSet.has(key)) { bad++; console.log('❌ README 声称但实际没有:\n   ', JSON.stringify(key)); }
}
console.log(`（真实输出共 ${realSet.size} 行，README 声称表格式行 ${claimed.length} 行）`);
console.log(bad === 0
  ? '✅ README 的 demo 输出与真实运行逐行一致'
  : `⛔ ${bad} 行对不上`);
process.exit(bad === 0 ? 0 : 1);
