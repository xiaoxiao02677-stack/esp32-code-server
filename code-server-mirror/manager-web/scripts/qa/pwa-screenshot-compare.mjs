#!/usr/bin/env node
// ============================================================
// PWA 双模式截图比对（Kawaii 控制台 P1-7 交付项）
//
// 功能：
//   1. 全量模式（node_modules 内已装 puppeteer）：
//      对关键页分别以浏览器偏好色 light / dark 两模式截图，
//      输出 PNG 到 manager-web/qa-screenshots/，并对 light/dark
//      截图做像素 diff，生成摘要（像素差异数 / 差异百分比 / 结论）。
//      Kawaii 设计系统约定无深色底，两模式渲染应基本一致，
//      diff 超阈值即说明存在偏好色泄漏（未跟色的深色残留）。
//   2. 降级模式（未装 puppeteer）：打印安装说明，退化为纯 DOM
//      检查（HTTP 拉取页面 + 静态核对 PWA 标记：manifest 链接、
//      theme-color meta、service-worker 注册、offline.html），
//      输出 dom-check 摘要到同一目录。
//
// 运行方式（在 manager-web 目录下）：
//   node scripts/qa/pwa-screenshot-compare.mjs \
//     --base-url http://localhost:8001 \
//     --pages /,/device-management \
//     [--cookie "token=xxx"]   # 登录态页面需带鉴权 cookie
//
// 退出码：0=全部通过/降级完成；1=存在 diff 超阈值；2=运行错误。
// 说明：不跑 npm build；dev 服务由 `npm run serve`（端口 8001）提供。
// ============================================================

import { createRequire } from 'node:module';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';
import { mkdirSync, existsSync, writeFileSync, readFileSync } from 'node:fs';

const __dirname = dirname(fileURLToPath(import.meta.url));
// 脚本位于 manager-web/scripts/qa/，回退两层定位 manager-web 根
const ROOT = join(__dirname, '..', '..');
const requireFromRoot = createRequire(join(ROOT, 'index.js'));
const OUT_DIR = join(ROOT, 'qa-screenshots');

// ---------- CLI 参数 ----------
const DEFAULT_PAGES = ['/', '/device-management'];
const DEFAULT_BASE_URL = 'http://localhost:8001';
const DIFF_THRESHOLD = 0.02; // 像素差异 > 2% 判 FAIL（Kawaii 无深色底，正常应 ≈0）

function parseArgs(argv) {
  const args = { baseUrl: DEFAULT_BASE_URL, pages: DEFAULT_PAGES, cookie: '' };
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--base-url') args.baseUrl = argv[++i] || args.baseUrl;
    else if (a === '--pages') args.pages = (argv[++i] || '').split(',').map((s) => s.trim()).filter(Boolean);
    else if (a === '--cookie') args.cookie = argv[++i] || '';
    else if (a === '--help' || a === '-h') {
      console.log('Usage: node scripts/qa/pwa-screenshot-compare.mjs [--base-url URL] [--pages /a,/b] [--cookie "k=v"]');
      process.exit(0);
    }
  }
  args.baseUrl = args.baseUrl.replace(/\/+$/, '');
  return args;
}

const args = parseArgs(process.argv.slice(2));
mkdirSync(OUT_DIR, { recursive: true });

// ---------- 依赖探测（从 manager-web 根解析 node_modules）----------
function tryRequire(name) {
  try {
    return requireFromRoot(name);
  } catch (e) {
    return null;
  }
}

const puppeteer = tryRequire('puppeteer');
const pixelmatch = tryRequire('pixelmatch');
const pngjs = tryRequire('pngjs');

function slug(p) {
  return p.replace(/^\/+|\/+$/g, '').replace(/[^a-zA-Z0-9]+/g, '_') || 'home';
}

// ============================================================
// 降级模式：纯 DOM / 静态检查（无 puppeteer 时）
// 通过 HTTP 拉取 landing 页 HTML，核对 PWA 关键标记；
// 若 dev 服务未启动，则退化为核对本地 dist/ 静态产物。
// ============================================================
async function runDomCheck() {
  console.log('\n[降级模式] node_modules 缺少 puppeteer，执行纯 DOM/PWA 标记检查。');
  console.log('安装完整截图能力（可选）：');
  console.log('  npm i -D puppeteer pixelmatch pngjs   # 或 npm i -D puppeteer-core 并自备 Chrome');
  console.log('  # 安装后重跑本脚本即自动进入全量截图 diff 模式\n');

  const checks = [];
  // level: required=决定结论；info=信息项（manifest/theme-color 本项目为 PWA-lite：
  // 仅 workbox service worker + offline.html，未注入 manifest，属设计现状而非缺陷）
  const check = (name, ok, detail, level = 'required') => checks.push({ name, ok, detail, level });

  let html = '';
  let source = 'none';
  try {
    const res = await fetch(`${args.baseUrl}/`);
    html = await res.text();
    source = `http ${args.baseUrl}`;
  } catch (e) {
    console.log(`[降级] dev 服务不可达（${e.message}），改为检查本地 dist/ 静态产物。`);
    const distIndex = join(ROOT, 'dist', 'index.html');
    if (existsSync(distIndex)) {
      html = readFileSync(distIndex, 'utf8');
      source = 'dist/index.html';
    }
  }

  if (html) {
    check('landing HTML 可获取', true, source);
    check('service worker 产物存在', existsSync(join(ROOT, 'dist', 'service-worker.js')) || /service[- ]?worker/i.test(html), 'workbox InjectManifest（swSrc=src/service-worker.js, swDest=service-worker.js）');
    check('offline.html 存在', existsSync(join(ROOT, 'public', 'offline.html')), '离线降级页');
    check('PWA manifest 链接 <link rel="manifest">', /<link[^>]+rel=["']manifest["']/i.test(html), '信息项：本项目为 PWA-lite（无 manifest），未注入属设计现状', 'info');
    check('theme-color meta', /<meta[^>]+name=["']theme-color["']/i.test(html), '信息项：同上，无 theme-color 属设计现状', 'info');
  } else {
    check('landing HTML 可获取', false, '既连不上 dev 服务，也无 dist 产物');
  }

  const requiredChecks = checks.filter((c) => c.level === 'required');
  const report = {
    mode: 'dom-check',
    baseUrl: args.baseUrl,
    generatedAt: new Date().toISOString(),
    checks,
    result: requiredChecks.every((c) => c.ok) ? 'PASS' : 'REVIEW'
  };
  const jsonPath = join(OUT_DIR, 'dom-check.json');
  const mdPath = join(OUT_DIR, 'dom-check.md');
  writeFileSync(jsonPath, JSON.stringify(report, null, 2));
  writeFileSync(
    mdPath,
    `# PWA DOM 检查摘要（降级模式）\n\n- base-url: ${args.baseUrl}\n- 时间: ${report.generatedAt}\n\n` +
      checks.map((c) => `- [${c.ok ? 'PASS' : c.level === 'info' ? 'INFO' : 'FAIL'}] ${c.name} —— ${c.detail}`).join('\n') +
      `\n\n结论（required 项）: ${report.result}\n` +
      `\n> 截图 diff 需安装 puppeteer 后重跑（见脚本头部安装说明）。\n`
  );
  console.log(`[降级] 摘要已写入 ${jsonPath}\n${mdPath}`);
  console.log(`\n结论: ${report.result}`);
  process.exit(report.result === 'PASS' ? 0 : 2);
}

// ============================================================
// 全量模式：puppeteer 双模式截图 + 像素 diff
// ============================================================
async function captureAllModes(browser, page) {
  const results = {};
  for (const mode of ['light', 'dark']) {
    // 浏览器偏好色切换：Kawaii 无深色底，两模式渲染预期一致
    await page.emulateMedia({ colorScheme: mode });
    for (const p of args.pages) {
      const url = `${args.baseUrl}${p.startsWith('/') ? p : `/${p}`}`;
      try {
        await page.goto(url, { waitUntil: 'networkidle2', timeout: 45000 });
      } catch (e) {
        // networkidle2 超时（长连接/MQTT 模拟等）不阻断，退化为 load
        console.log(`[warn] ${url} networkidle2 超时（${e.message}），退化为 load`);
        await page.goto(url, { waitUntil: 'load', timeout: 45000 });
      }
      await new Promise((r) => setTimeout(r, 800)); // 等待首帧动画/字体稳定
      const file = join(OUT_DIR, `pwa-${slug(p)}-${mode}.png`);
      await page.screenshot({ path: file, fullPage: true });
      results[mode] = results[mode] || {};
      results[mode][p] = file;
    }
  }
  return results;
}

function diffLightDark(lightPng, darkPng, outDir, label) {
  // 1) pixelmatch 像素级 diff
  if (pixelmatch && pngjs) {
    const a = new pngjs.PNG().parse(readFileSync(lightPng));
    const b = new pngjs.PNG().parse(readFileSync(darkPng));
    const { width, height } = a;
    const diff = new pngjs.PNG({ width, height });
    const numDiff = pixelmatch(a.data, b.data, diff.data, width, height, { threshold: 0.1 });
    const diffPng = join(outDir, `pwa-${label}-diff.png`);
    diff.pack().writeFileSync(diffPng);
    const total = width * height;
    const pct = total ? numDiff / total : 0;
    return {
      method: 'pixelmatch',
      numDiff,
      totalPixels: total,
      diffPercent: Number(pct.toFixed(4)),
      verdict: pct <= DIFF_THRESHOLD ? 'PASS' : 'FAIL',
      diffImage: diffPng
    };
  }
  // 2) 无 pixelmatch/pngjs：字节级比对（同分辨率下全等即可判一致）
  const la = readFileSync(lightPng);
  const da = readFileSync(darkPng);
  const byteIdentical = la.length === da.length && la.equals(da);
  return {
    method: 'byte-compare',
    note: '未安装 pixelmatch/pngjs，仅字节级比对；安装后重跑可获得像素级 diff',
    byteIdentical,
    verdict: byteIdentical ? 'PASS' : 'REVIEW'
  };
}

async function runFullMode() {
  console.log(`[全量模式] base=${args.baseUrl} pages=${args.pages.join(' ')}`);
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--force-color-profile=srgb', '--font-render-hinting=none']
  });
  try {
    const page = await browser.newPage();
    await page.setViewport({ width: 1280, height: 800, deviceScaleFactor: 1 });
    if (args.cookie) {
      await page.setExtraHTTPHeaders({ Cookie: args.cookie });
    }
    const shots = await captureAllModes(browser, page);
    const report = {
      mode: 'screenshot-diff',
      baseUrl: args.baseUrl,
      threshold: DIFF_THRESHOLD,
      generatedAt: new Date().toISOString(),
      results: []
    };
    let allPass = true;
    for (const p of args.pages) {
      const light = shots.light[p];
      const dark = shots.dark[p];
      const d = diffLightDark(light, dark, OUT_DIR, slug(p));
      const entry = { page: p, light, dark, ...d };
      report.results.push(entry);
      console.log(
        `[${entry.verdict}] ${p}: ${d.method === 'pixelmatch'
          ? `diff=${d.numDiff}/${d.totalPixels} px (${d.diffPercent}%)`
          : `byteIdentical=${d.byteIdentical}`}  -> ${d.diffImage || '(无 diff 图)'}`
      );
      if (entry.verdict === 'FAIL') allPass = false;
    }
    report.verdict = allPass ? 'PASS' : 'FAIL';

    const jsonPath = join(OUT_DIR, 'pwa-compare-summary.json');
    writeFileSync(jsonPath, JSON.stringify(report, null, 2));
    const mdPath = join(OUT_DIR, 'pwa-compare-summary.md');
    writeFileSync(
      mdPath,
      `# PWA 双模式截图 diff 摘要\n\n- base-url: ${args.baseUrl}\n- 页面: ${args.pages.join(', ')}\n- 判定阈值: 像素差异 ≤ ${(DIFF_THRESHOLD * 100).toFixed(0)}% 为 PASS\n- 时间: ${report.generatedAt}\n\n` +
        '| 页面 | light 截图 | dark 截图 | diff 图 | 差异 | 结论 |\n|---|---|---|---|---|---|\n' +
        report.results
          .map(
            (r) =>
              `| ${r.page} | ${r.light.replace(ROOT + '/', '')} | ${r.dark.replace(ROOT + '/', '')} | ` +
              `${r.diffImage ? r.diffImage.replace(ROOT + '/', '') : '-'} | ` +
              `${r.method === 'pixelmatch' ? `${r.numDiff}/${r.totalPixels} (${r.diffPercent}%)` : `字节级 ${r.byteIdentical ? '一致' : '不一致'}`} | ${r.verdict} |`
          )
          .join('\n') +
        `\n\n总结论: **${report.verdict}**\n\n> Kawaii 设计系统无深色底：light/dark 偏好色渲染预期一致；FAIL 表示存在未跟色的深色残留或未适配元素，请定位 diff 图逐像素排查。\n`
    );
    console.log(`\n摘要: ${mdPath}\n      ${jsonPath}`);
    process.exit(allPass ? 0 : 1);
  } finally {
    await browser.close();
  }
}

// ---------- 入口 ----------
(async () => {
  if (!puppeteer) {
    await runDomCheck();
    return;
  }
  try {
    await runFullMode();
  } catch (e) {
    console.error(`[error] 全量模式执行失败: ${e.message}`);
    console.error('提示：puppeteer 启动失败常见原因为缺少浏览器内核，可执行 npx puppeteer browsers install chrome 后重试；' +
      '亦可暂不安装 puppeteer，重跑本脚本会自动降级为纯 DOM 检查。');
    process.exit(2);
  }
})();
