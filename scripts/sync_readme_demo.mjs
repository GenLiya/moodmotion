// 把真实 demo 输出写回 README（README 里的示例必须是跑出来的，不是手抄的）
// ⚠️ execFileSync 会把 stderr 混进返回值（本机有个 Python 警告），
//    导致行号整体偏移、表头被切掉。用 spawnSync 拿**干净的 stdout**。
import { spawnSync } from 'node:child_process';
import { readFileSync, writeFileSync } from 'node:fs';

const ROOT = 'E:\\person\\important\\openclaw\\AI项目\\moodmotion';
const run = spawnSync('py', ['-3', '-m', 'moodmotion.cli', 'demo'], {
  cwd: ROOT, encoding: 'utf8',
  env: { ...process.env, PYTHONIOENCODING: 'utf-8' },
});
if (run.status !== 0 || !run.stdout) {
  console.log('❌ demo 运行失败:', run.status, run.stderr?.slice(0, 300));
  process.exit(1);
}
if (run.stderr && run.stderr.trim()) console.log('(注意：stderr 有输出，已忽略)', run.stderr.trim().split('\n')[0]);
const real = run.stdout;

// ⚠️ 两个坑，都实测踩过：
//   ① execFileSync 会把 stderr 混进返回值 → 用 spawnSync 只取 stdout；
//   ② Python 写的是 \r\n，node 按 \n 切会留下孤立的 "\r" 行。
// ⚠️ 但**不能顺手把空行也滤掉**：分组标题前后靠空行分隔，滤掉就会把标题挤进表格里。
//    所以只归一化行尾，保留内部空行，最后再 trim 两端。
const clean = (s) => s.split('\n').map((l) => l.replace(/\r$/, ''));
const lines = clean(real);
// 用**内容锚点**定位，不依赖列宽/前导空格。
const stop = lines.findIndex((l) => l.includes('another one'));
if (stop === -1) { console.log('❌ 没在 demo 输出里找到结束锚点 "another one"'); process.exit(1); }
// 表头＝基准行**之前**那一行；用内容特征找，别用索引做算术（实测被前导空行坑过）
const baseline = lines.findIndex((l) => l.includes('baseline'));
const header = lines.findIndex((l) => l.includes('valence') && l.includes('energy'));
const start = header >= 0 ? header : Math.max(0, baseline - 1);
const table = lines.slice(start, stop + 1).join('\n').trimEnd();

// 硬断言：抓出来的东西必须真的像那张表，否则宁可中止也不要写进 README
const problems = [];
if (!/valence/.test(table) || !/energy/.test(table)) problems.push('缺表头（valence/energy）');
if (!table.includes('baseline')) problems.push('缺基线行');
if (!table.includes('another one')) problems.push('缺结束行');
const rows = (table.match(/^\s*d\d+ /gm) || []).length;
if (rows < 8) problems.push(`表体行数过少（${rows}）`);
if (problems.length) {
  console.log('❌ 抓取结果不可信，已中止:', problems.join('；'));
  console.log('--- 抓到的前 3 行 ---');
  table.split('\n').slice(0, 3).forEach((l) => console.log('   ', JSON.stringify(l.slice(0, 70))));
  process.exit(1);
}
console.log(`定位到表格：第 ${start + 1}–${stop + 1} 行，共 ${table.split('\n').length} 行（表体 ${rows} 行）`);

const path = `${ROOT}\\README.md`;
const readme = readFileSync(path, 'utf8');
const re = /(```\n\$ python -m moodmotion\.cli demo\n\n)([\s\S]*?)(```)/;
if (!re.test(readme)) { console.log('❌ README 里没找到 demo 代码块'); process.exit(1); }
const updated = readme.replace(re, (_m, head, _old, tail) => head + table + '\n' + tail);
writeFileSync(path, updated, 'utf8');
console.log('✅ 已把真实 demo 输出写入 README（' + table.split('\n').length + ' 行）');
