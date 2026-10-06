'use strict';
/**
 * 探针驱动（只在 `MIPL_PROBE=1` 时被 main.js require）
 * ==================================================
 *
 * 它在真 Electron 里把界面**逐页跑一遍**并截图，断言这些事：
 *   1. 普通 8 步 / 高级 12 步都能渲染出对应页面；
 *   2. 界面上不出现 `⟨缺键⟩`（文案键全覆盖）；
 *   3. 中英切换真的换了字（拿 `nav.next` 当锚点）；
 *   4. 亮 / 暗两套主题都渲染（`data-theme` 生效）；
 *   5. 每个可点元素都有无障碍名字（文本或 `aria-label`）；
 *   6. `prefers-reduced-motion: reduce` 下页面进场不做位移。
 *
 * 口径：这是**离屏旁证**，不等于 cage / 真 ISO 里验过（V3 / V5 / V7 仍要 QEMU）。
 * 任一断言失败 → 退出码 1；全部通过 → 0，并把摘要打到 stdout。
 */

const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

module.exports = async function probe({ app, win, launch }) {
  const outDir = process.env.MIPL_PROBE_OUT || path.join(os.tmpdir(), 'mipl-probe');
  fs.mkdirSync(outDir, { recursive: true });

  const failures = [];
  const notes = [];
  // 记住「最后一句注入的脚本」：注入脚本抛错时 Electron 只给一句笼统的话，
  // 没有它就只能靠猜是哪一行
  let lastRun = '';
  const run = async (code) => {
    lastRun = code.replace(/\s+/g, ' ').slice(0, 160);
    return win.webContents.executeJavaScript(code, true);
  };

  // 离屏渲染：最新的 paint 帧就是「屏幕上的画面」。headless 下 capturePage() 会给 1×1。
  let lastFrame = null;
  let frameWaiters = [];
  win.webContents.on('paint', (_event, _dirty, image) => {
    if (!lastFrame) console.log(`（首帧尺寸：${JSON.stringify(image.getSize())}，窗口内容区：${JSON.stringify(win.getContentSize())}）`);
    lastFrame = image;
    const waiters = frameWaiters;
    frameWaiters = [];
    for (const resolve of waiters) resolve(image);
  });
  win.webContents.setFrameRate(30);

  const nextFrame = (timeoutMs = 2000) =>
    new Promise((resolve) => {
      const timer = setTimeout(() => resolve(lastFrame), timeoutMs);
      frameWaiters.push((image) => {
        clearTimeout(timer);
        resolve(image);
      });
    });

  /** 等 `[data-anim]` 全部淡入完成 —— 截图必须是稳定帧，不能是动画中间态。 */
  const settle = async (timeoutMs = 2000) => {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const pending = await run(
        `[...document.querySelectorAll('[data-anim]')].filter((el) => Number(getComputedStyle(el).opacity) < 0.99).length`
      );
      if (pending === 0) {
        await nextFrame();
        return true;
      }
      await sleep(80);
    }
    return false;
  };

  const shot = async (name) => {
    await settle();
    const image = (await nextFrame()) || lastFrame;
    if (!image || image.isEmpty()) {
      failures.push(`截图 ${name} 是空帧（离屏渲染没出画面）`);
      return null;
    }
    const file = path.join(outDir, `${name}.png`);
    fs.writeFileSync(file, image.toPNG());
    return file;
  };
  const check = (ok, label, detail = '') => {
    if (ok) console.log(`  ✅ ${label}`);
    else {
      console.log(`  ❌ ${label}${detail ? ` —— ${detail}` : ''}`);
      failures.push(`${label}${detail ? `：${detail}` : ''}`);
    }
  };

  win.webContents.on('did-fail-load', (_e, code, desc) => {
    failures.push(`页面加载失败：${code} ${desc}`);
  });

  try {
    await new Promise((resolve) => {
      if (!win.webContents.isLoading()) return resolve();
      win.webContents.once('did-finish-load', resolve);
    });

    // 等 app.boot() 完成（暴露了探针接口就说明装配完了）
    for (let i = 0; i < 100; i += 1) {
      const ready = await run('Boolean(window.__mipl)');
      if (ready) break;
      await sleep(100);
    }
    const ready = await run('Boolean(window.__mipl)');
    if (!ready) {
      console.log('❌ 界面没有暴露探针接口（window.__mipl）—— 启动阶段就失败了');
      console.log(await run('document.body.innerText.slice(0, 400)'));
      app.exit(1);
      return;
    }

    console.log(`\n探针输出目录：${outDir}`);
    console.log(`Electron ${launch ? launch.electron || process.versions.electron : process.versions.electron}\n`);

    // ---------------------------------------------------------- 1. 普通 8 步
    const state0 = await run('window.__mipl.state()');
    check(state0.steps.length === 8, '普通流程是 8 步', `实际 ${state0.steps.length}`);
    check(state0.language === 'zh_CN', '首帧语言是 zh_CN', `实际 ${state0.language}`);
    check(state0.theme === 'dark' || state0.theme === 'light', '首帧有明确主题', `实际 ${state0.theme}`);

    for (const id of state0.steps) {
      await run(`window.__mipl.goTo(${JSON.stringify(id)})`);
      await sleep(200);
      await settle();
      const mounted = await run(`Boolean(document.querySelector('#page-${id}'))`);
      check(mounted, `普通流程渲染 ${id}`);
      await shot(`normal-${String(state0.steps.indexOf(id) + 1).padStart(2, '0')}-${id}`);
    }

    // ---------------------------------------------------------- 2. 高级 12 步
    const advanced = await run('window.__mipl.setAdvanced(true)');
    check(advanced.length === 12, '高级流程是 12 步', `实际 ${advanced.length}`);
    for (const id of advanced) {
      await run(`window.__mipl.goTo(${JSON.stringify(id)})`);
      await sleep(200);
      await settle();
      let mounted = await run(`Boolean(document.querySelector('#page-${id}'))`);
      if (!mounted && id === 'progress') {
        // 进度页跑完会自动跳完成页 —— 那是预期行为，回来看一眼再断言
        await run('window.__mipl.goTo("progress")');
        await sleep(120);
        mounted = await run(`Boolean(document.querySelector('#page-progress'))`);
      }
      check(mounted, `高级流程渲染 ${id}`);
      if (['locale', 'keymap', 'timezone', 'hostname'].includes(id)) {
        await shot(`advanced-${id}`);
      }
    }

    // ---------------------------------------------------------- 3. 缺键、图片、无障碍
    const missing = await run('window.__mipl.countUndefinedStrings()');
    check(missing === 0, '界面上没有未解析的文案键', `发现 ${missing} 处 ⟨…⟩`);

    // 图片真的载入了（载入失败时 naturalWidth === 0，页面上只是「少了一块」，不报错）
    await run('window.__mipl.goTo("welcome")');
    await sleep(320);
    const images = await run(
      `[...document.images].map((img) => ({ src: img.currentSrc || img.src, w: img.naturalWidth, h: img.naturalHeight }))`
    );
    const broken = images.filter((img) => !img.w || !img.h);
    check(images.length > 0 && broken.length === 0, `图片资源都载入了（${images.length} 张）`, JSON.stringify(broken));

    // 「载入了但看不见」也要抓：报出主视觉的几何与可见性
    const heroBox = await run(`(() => {
      const el = document.querySelector('.welcome__logo');
      if (!el) return { missing: true };
      const rect = el.getBoundingClientRect();
      const style = getComputedStyle(el);
      return {
        x: Math.round(rect.x), y: Math.round(rect.y), w: Math.round(rect.width), h: Math.round(rect.height),
        natural: [el.naturalWidth, el.naturalHeight],
        opacity: style.opacity, visibility: style.visibility, display: style.display,
        transform: style.transform, zIndex: style.zIndex, filter: style.filter.slice(0, 40),
        complete: el.complete,
      };
    })()`);
    check(
      !heroBox.missing && heroBox.w > 120 && heroBox.h > 120 && heroBox.opacity === '1' && heroBox.visibility === 'visible',
      '欢迎页主视觉真的画出来了（尺寸 / 透明度 / 可见性）',
      JSON.stringify(heroBox)
    );

    const a11y = await run(`(() => {
      const nodes = [...document.querySelectorAll('button, input')];
      const bad = nodes.filter((el) => {
        if (el.tagName === 'INPUT') return !el.id && !el.getAttribute('aria-label');
        return !(el.innerText || '').trim() && !el.getAttribute('aria-label') && !el.getAttribute('title');
      }).map((el) => el.tagName + '#' + (el.id || '?'));
      return { total: nodes.length, bad };
    })()`);
    check(a11y.bad.length === 0, `可点元素都有无障碍名字（共 ${a11y.total} 个）`, a11y.bad.join(', '));

    const primaryText = async () => {
      const info = await run(`(() => {
        const btn = document.querySelector('#nav-primary');
        return { text: btn ? btn.innerText.trim() : null, page: window.__mipl.state().page,
                 actions: [...document.querySelectorAll('#actions button')].map((b) => b.id + ':' + b.innerText.trim()) };
      })()`);
      return info;
    };

    // ---------------------------------------------------------- 4. 中英切换
    // 锚点：欢迎页的主动作是 `welcome.begin`，网络页没有专属文案 → 通用 `nav.next`
    await run('window.__mipl.goTo("welcome")');
    await sleep(420);
    const zhBeginInfo = await primaryText();
    check(zhBeginInfo.text === '开始', '中文欢迎页主按钮是「开始」', JSON.stringify(zhBeginInfo));

    await run('window.__mipl.setLanguage("en_US")');
    await sleep(320);
    const enBeginInfo = await primaryText();
    check(enBeginInfo.text === 'Get started', '英文欢迎页主按钮是 Get started', JSON.stringify(enBeginInfo));

    await run('window.__mipl.goTo("network")');
    await sleep(420);
    const enNextInfo = await primaryText();
    check(enNextInfo.text === 'Next', '英文网络页主按钮是通用 Next', JSON.stringify(enNextInfo));
    await shot('lang-en-network');
    const enMissing = await run('window.__mipl.countUndefinedStrings()');
    check(enMissing === 0, '英文界面也没有缺键');

    await run('window.__mipl.setLanguage("zh_CN")');
    await sleep(320);
    const zhNextInfo = await primaryText();
    check(zhNextInfo.text === '下一步', '切回中文后主按钮是「下一步」', JSON.stringify(zhNextInfo));

    // ---------------------------------------------------------- 4.5 表单页的无障碍
    await run('window.__mipl.goTo("account")');
    await sleep(220);
    const a11yForm = await run(`(() => {
      const nodes = [...document.querySelectorAll('button, input')];
      const bad = nodes.filter((el) => {
        if (el.tagName === 'INPUT') return !el.id && !el.getAttribute('aria-label');
        return !(el.innerText || '').trim() && !el.getAttribute('aria-label') && !el.getAttribute('title');
      }).map((el) => el.tagName + '#' + (el.id || '?'));
      return { total: nodes.length, bad };
    })()`);
    check(a11yForm.bad.length === 0, `账户页的可点元素都有无障碍名字（${a11yForm.total} 个）`, a11yForm.bad.join(', '));
    const labelled = await run(`[...document.querySelectorAll('input')].every((el) => Boolean(document.querySelector('label[for="' + el.id + '"]')))`);
    check(labelled, '账户页每个输入框都有对应的 label');

    // ---------------------------------------------------------- 5. 双主题
    await run('window.__mipl.setTheme("light")');
    await sleep(250);
    const lightTheme = await run('document.documentElement.dataset.theme');
    check(lightTheme === 'light', '亮色主题已应用', `实际 ${lightTheme}`);
    await run('window.__mipl.goTo("welcome")');
    await sleep(260);
    await shot('theme-light-welcome');
    await run('window.__mipl.setTheme("dark")');
    await sleep(250);
    await run('window.__mipl.goTo("welcome")');
    await sleep(260);
    await shot('theme-dark-welcome');
    const darkTheme = await run('document.documentElement.dataset.theme');
    check(darkTheme === 'dark', '暗色主题已应用', `实际 ${darkTheme}`);

    // ---------------------------------------------------------- 6. 界面缩放：自动 / 100 / 167 / 200
    for (const mode of [100, 167, 200]) {
      await run(`window.__mipl.setScale(${mode})`);
      await sleep(140);
      const applied = await run('getComputedStyle(document.documentElement).getPropertyValue("--ui-scale").trim()');
      check(Math.abs(Number(applied) - mode / 100) < 0.001, `界面缩放 ${mode}% 生效`, `实际 ${applied}`);
    }
    // 控件尺寸体系（实机反馈：167% 下按钮「太扁」、图标没有呼吸空间、目录数字小）
    const metrics = async () => {
      return run(`(() => {
        const btn = document.getElementById('nav-primary');
        const dot = document.querySelector('.step__dot');
        const title = document.querySelector('.lead') || document.querySelector('.page-title');
        const num = (el, prop) => (el ? Math.round(parseFloat(getComputedStyle(el)[prop])) : -1);
        return {
          buttonHeight: btn ? Math.round(btn.getBoundingClientRect().height) : -1,
          dotFont: num(dot, 'fontSize'),
          titleFont: num(title, 'fontSize'),
        };
      })()`);
    };
    await run('window.__mipl.setScale(100)');
    await sleep(180);
    const at100 = await metrics();
    await run('window.__mipl.setScale(200)');
    await sleep(180);
    const at200 = await metrics();
    check(
      at100.buttonHeight > 0 && at200.buttonHeight >= at100.buttonHeight * 1.8,
      '按钮高度跟着界面缩放（不再「扁」）',
      JSON.stringify({ at100, at200 })
    );
    check(at100.dotFont > 0 && at200.dotFont >= at100.dotFont * 1.8, '步骤序号跟着缩放', JSON.stringify({ dot: [at100.dotFont, at200.dotFont] }));
    check(
      at100.titleFont > 0 && at200.titleFont <= at100.titleFont * 1.7,
      '大标题缩放放缓（不把一屏撑满）',
      JSON.stringify({ title: [at100.titleFont, at200.titleFont] })
    );
    await run('window.__mipl.setScale(100)');
    await sleep(150);

    // 图标必须跟着缩放走（实机反馈：167% 下图标显得小 —— 曾经是固定 px）
    const iconAt100 = await run(`(() => { window.__mipl.setScale(100); const el = document.querySelector('.icon-btn svg') || document.querySelector('.menu__item svg'); return el ? Math.round(el.getBoundingClientRect().width) : -1; })()`);
    await sleep(120);
    const iconAt200 = await run(`(() => { window.__mipl.setScale(200); const el = document.querySelector('.icon-btn svg') || document.querySelector('.menu__item svg'); return el ? Math.round(el.getBoundingClientRect().width) : -1; })()`);
    check(
      iconAt100 > 0 && iconAt200 >= iconAt100 * 1.8,
      '图标随界面缩放一起变大（100% → 200% 约翻倍）',
      JSON.stringify({ iconAt100, iconAt200 })
    );

    // 软渲染下的低配模式：氛围层必须被关掉（否则 CPU 光栅化要糊一堆大模糊）
    const lowPower = await run(`(() => {
      document.documentElement.dataset.renderer = 'software';
      const aurora = getComputedStyle(document.querySelector('.aurora')).display;
      const grain = getComputedStyle(document.querySelector('.grain')).display;
      const panel = document.querySelector('.panel');
      const shadow = panel ? getComputedStyle(panel).boxShadow : '（本页无面板）';
      document.documentElement.dataset.renderer = 'gpu';
      return { aurora, grain, shadow };
    })()`);
    check(
      lowPower.aurora === 'none' && lowPower.grain === 'none',
      '软渲染时自动关掉极光与噪点（低配模式）',
      JSON.stringify(lowPower)
    );

    // 动画期间的帧间隔基线（离屏渲染，只作仓内回归基线，不代表实机）
    const perf = await run(`new Promise((resolve) => {
      const frames = [];
      let last = performance.now();
      let count = 0;
      window.__mipl.goTo('welcome');
      function tick(now) {
        frames.push(now - last);
        last = now;
        count += 1;
        if (count === 2) window.__mipl.goTo('network');
        if (count >= 90) {
          const sorted = [...frames.slice(1)].sort((a, b) => a - b);
          const pick = (q) => Math.round(sorted[Math.floor(sorted.length * q)]);
          resolve({ frames: sorted.length, p50: pick(0.5), p95: pick(0.95), max: Math.round(sorted[sorted.length - 1]) });
          return;
        }
        requestAnimationFrame(tick);
      }
      requestAnimationFrame(tick);
    })`);
    console.log(`  ℹ️  帧间隔基线（离屏，仅供参考）：p50=${perf.p50}ms p95=${perf.p95}ms max=${perf.max}ms`);
    notes.push(`帧间隔基线（离屏）：p50=${perf.p50}ms p95=${perf.p95}ms max=${perf.max}ms`);
    check(perf.p95 <= 120, '离屏帧间隔基线正常（p95 ≤ 120ms）', JSON.stringify(perf));

    const autoPercent = await run('window.__mipl.setScale("auto")');
    check([100, 167, 200].includes(autoPercent), `自动档落到白名单档位（${autoPercent}%）`, `实际 ${autoPercent}`);

    // 菜单本身：缩放 4 项（自动 + 三档）、主题 3 项
    await run('window.__mipl.setScale(100)');
    await sleep(120);
    await run('window.__mipl.openScaleMenu()');
    await sleep(200);
    await shot('menu-scale-open');
    const scaleMenu = await run(`(() => {
      const open = !document.getElementById('scale-menu-popup').hidden;
      const items = [...document.querySelectorAll('#scale-menu-popup .menu__item')].map((el) => el.innerText.trim());
      const triggerIcon = document.querySelector('#scale-menu svg') ? 'yes' : 'no';
      document.body.click();
      return { open, items, triggerIcon };
    })()`);
    check(scaleMenu.open, '缩放菜单能打开', JSON.stringify(scaleMenu));
    check(scaleMenu.items.length === 4 && scaleMenu.items[0] === '自动检测', '缩放菜单是「自动检测 + 100/167/200」', JSON.stringify(scaleMenu.items));
    check(scaleMenu.triggerIcon === 'yes', '缩放按钮有图标（放大镜）');

    await run('window.__mipl.openThemeMenu()');
    await sleep(200);
    await shot('menu-theme-open');
    const themeMenu = await run(`(() => {
      const open = !document.getElementById('theme-menu-popup').hidden;
      const items = [...document.querySelectorAll('#theme-menu-popup .menu__item')].map((el) => el.innerText.trim());
      document.body.click();
      return { open, items };
    })()`);
    check(themeMenu.open, '主题菜单能打开', JSON.stringify(themeMenu));
    check(themeMenu.items.length === 3, '主题菜单是「跟随时间 / 亮 / 暗」', JSON.stringify(themeMenu.items));

    // 药囊：不换行（实机反馈：被折成四行）。走**真实用户路径** —— 点菜单项，
    // 因为药囊就是由菜单的 onSelect 弹出来的（用探针 API 换档不会弹）。
    const clicked = await run(`(() => {
      try {
        window.__mipl.openScaleMenu();
        const item = document.querySelector('#scale-menu-popup .menu__item[data-value="167"]');
        if (!item) return { ok: false, why: '没找到 167% 菜单项', items: [...document.querySelectorAll('#scale-menu-popup .menu__item')].map((el) => el.dataset.value) };
        item.click();
        return { ok: true };
      } catch (error) {
        return { ok: false, why: String(error && (error.stack || error.message || error)) };
      }
    })()`);
    check(clicked.ok, '能通过菜单把缩放切到 167%', JSON.stringify(clicked));
    await sleep(260);
    // 判「一行」只用药囊的高度 + white-space：**别在注入脚本里分裂换行**
    // （注入脚本是模板字面量，`\n` 会先被 Node 变成真换行，注入进去就是语法错误）
    const snack = await run(`(() => {
      const el = document.querySelector('.snackbar');
      if (!el) return null;
      const style = getComputedStyle(el);
      const span = el.querySelector('span');
      return {
        height: Math.round(el.getBoundingClientRect().height),
        width: Math.round(el.getBoundingClientRect().width),
        nowrap: style.whiteSpace,
        // 换行的行内盒会给**多个** client rect —— 这才是「有没有折行」的可靠判据
        textRects: span ? span.getClientRects().length : 0,
      };
    })()`);
    check(
      Boolean(snack) && snack.nowrap === 'nowrap' && snack.textRects === 1 && snack.height <= 72,
      '药囊提示一行放得下（不换行）',
      JSON.stringify(snack)
    );

    // ---------------------------------------------------------- 6.5 布局不变量（实机反馈的回归）
    // 2026-10-04 实机发现：`#root` 没有高度 → `.app` 随内容长高，高级安装（12 步）与
    // WiFi 展开都会把底部动作区顶出视口。下面这些断言把那次问题钉死。
    await run('window.__mipl.setScale(100)');
    await run('window.__mipl.setTheme("light")');   // 亮色是主主题：回归截图也按亮色留档
    win.setContentSize(1024, 768);
    await sleep(420);
    await run('window.__mipl.setAdvanced(true)');
    await run('window.__mipl.goTo("welcome")');
    await sleep(420);
    await settle();

    const layout = await run(`(() => {
      const root = document.getElementById('root');
      const actions = document.getElementById('actions');
      const stepsBody = document.querySelector('.steps__body');
      const stage = document.getElementById('stage');
      const rect = actions.getBoundingClientRect();
      const inner = window.innerHeight;
      return {
        innerHeight: inner,
        docScroll: document.documentElement.scrollHeight,
        bodyScroll: document.body.scrollHeight,
        rootHeight: Math.round(root.getBoundingClientRect().height),
        actionsBottom: Math.round(rect.bottom),
        actionsTop: Math.round(rect.top),
        stageClient: stage.clientHeight,
        stageScroll: stage.scrollHeight,
        stepsClient: stepsBody ? stepsBody.clientHeight : -1,
        stepsScroll: stepsBody ? stepsBody.scrollHeight : -1,
        scrollbarGap: window.innerWidth - document.documentElement.clientWidth,
        userSelect: getComputedStyle(document.body).userSelect || getComputedStyle(document.body).webkitUserSelect,
        inputSelect: getComputedStyle(document.querySelector('input') || document.body).userSelect,
      };
    })()`);

    check(layout.docScroll <= layout.innerHeight + 1, '1024×768 下页面本身不滚动（整窗固定）', JSON.stringify(layout));
    check(layout.actionsBottom <= layout.innerHeight + 1, '动作区始终在视口内（12 步时也是）', `bottom=${layout.actionsBottom} / 视口=${layout.innerHeight}`);
    check(Math.abs(layout.rootHeight - layout.innerHeight) <= 1, '#root 高度 = 视口高度', `${layout.rootHeight} vs ${layout.innerHeight}`);
    // 维护者 2026-10-04：轨道**允许**在放不下时滚，但不许画出占位的滚动条，
    // 条目也不许为了「塞下 12 步」被压扁。
    const stepBox = await run(`(() => {
      const step = document.querySelector('.step');
      const body = document.querySelector('.steps__body');
      const rail = document.querySelector('.steps');
      return {
        itemHeight: step ? Math.round(step.getBoundingClientRect().height) : -1,
        scrollbarGap: body ? body.offsetWidth - body.clientWidth : -1,
        // rail 的 offset-client 差 = 左右边框（1px×2），不是滚动条；要减掉边框再判
        railGap: (() => {
          if (!rail) return -1;
          const style = getComputedStyle(rail);
          const border = parseFloat(style.borderLeftWidth) + parseFloat(style.borderRightWidth);
          return Math.round(rail.offsetWidth - rail.clientWidth - border);
        })(),
      };
    })()`);
    check(stepBox.itemHeight >= 34, '步骤条目保持舒适高度（没有被压扁）', JSON.stringify(stepBox));
    check(stepBox.scrollbarGap === 0 && stepBox.railGap === 0, '轨道里没有占位的滚动条', JSON.stringify(stepBox));
    check(layout.scrollbarGap === 0, '滚动条不占位（不挤压内容宽度）', `差 ${layout.scrollbarGap}px`);
    check(layout.userSelect === 'none', '文本默认不可选中', `实际 ${layout.userSelect}`);
    check(layout.inputSelect === 'text', '输入框里可以选中文本', `实际 ${layout.inputSelect}`);
    await shot('layout-1024x768-advanced-welcome');

    // ---------------------------------------------------------- 6.6 选中 WiFi 之后主按钮仍可点
    await run('window.__mipl.goTo("network")');
    await sleep(360);
    const wifi = await run('window.__mipl.scanWifi()');   // 显式扫一次，别在空列表上做断言
    await sleep(320);
    check(wifi.length > 0, `Wi-Fi 候选扫出来了（${wifi.length} 个）`, JSON.stringify(wifi));
    await settle();
    await run('window.__mipl.setData("wifiSelected", "MipLab-5G")');
    await run('window.__mipl.rerender()');
    await sleep(320);
    await settle();
    const reachable = await run(`(() => {
      const btn = document.getElementById('nav-primary');
      if (!btn) return { ok: false, why: '没有主按钮' };
      const rect = btn.getBoundingClientRect();
      const cx = rect.left + rect.width / 2, cy = rect.top + rect.height / 2;
      const hit = document.elementFromPoint(cx, cy);
      return {
        ok: rect.bottom <= window.innerHeight && !btn.disabled && Boolean(hit) && (hit === btn || btn.contains(hit)),
        inViewport: rect.bottom <= window.innerHeight,
        disabled: btn.disabled,
        hit: hit ? hit.id || hit.className : null,
        bottom: Math.round(rect.bottom), innerHeight: window.innerHeight,
      };
    })()`);
    check(reachable.ok, '选中 WiFi 后主动作仍在视口内且可点', JSON.stringify(reachable));
    await shot('network-wifi-selected-1024x768');

    // ---------------------------------------------------------- 6.6b 网络页的「重新扫描」与现状自动刷新
    // 9a99666 那次「重新扫描挪到列表下方」在 disk.js 挪对了，在网络页却是**直接删掉**
    // （`?: null`）—— 于是网卡住时既没有手动入口，也没有自动刷新（维护者 2026-10-05）。
    const rescanButton = await run(`(() => {
      const btn = document.getElementById('wifi-rescan');
      if (!btn) return { exists: false };
      const list = document.querySelector('#page-network .list');
      return {
        exists: true,
        // 「在列表下方」：按钮顶边不低于列表底边（空列表时没有列表可依，只判存在）
        below: list ? btn.getBoundingClientRect().top >= list.getBoundingClientRect().bottom - 1 : true,
        label: btn.textContent.trim(),
      };
    })()`);
    check(rescanButton.exists && rescanButton.below, '网络页有「重新扫描」，位置在列表下方', JSON.stringify(rescanButton));

    const rescanRan = await run(`(async () => {
      document.getElementById('wifi-rescan').click();
      await new Promise((resolve) => setTimeout(resolve, 150));
      const scanning = Boolean(document.querySelector('#page-network .skeleton'));
      await new Promise((resolve) => setTimeout(resolve, 1300));
      return { scanning, options: document.querySelectorAll('#page-network .option').length };
    })()`);
    check(rescanRan.scanning && rescanRan.options > 0, '点「重新扫描」：先出「正在扫描」，扫完列表还在', JSON.stringify(rescanRan));

    // 停留本页时，「外面的世界变了」界面得自己发现：这一页没连上就不让往下走，
    // 只在开工时读一次现状的话，网通了人也出不去。
    const unplugged = await run(`(() => {
      const badge = () => document.querySelector('#page-network .badge').textContent;
      const before = badge();
      window.__mipl.setLink(false);   // 只改「现状」，不改上一次问回来的结果
      return { before, stillShown: badge() };   // 同一个同步块里读：中间插不进一轮轮询
    })()`);
    await sleep(3800);   // 等一轮轮询（POLL_MS = 3000）
    await settle();
    const afterUnplug = await run(`(() => ({
      badge: document.querySelector('#page-network .badge').textContent,
      disabled: document.getElementById('nav-primary').disabled,
    }))()`);
    check(
      unplugged.before === unplugged.stillShown && afterUnplug.badge !== unplugged.before && afterUnplug.disabled === true,
      '停在网络页：拔网线之后界面自己变成「未连接」并拦住「下一步」',
      JSON.stringify({ ...unplugged, ...afterUnplug })
    );

    // 再插回去 —— 这一条**要求上一轮轮询先落地**（`beforePlug` 必须是「未连接 + 拦住」），
    // 否则「网通了能解锁」在网络页从头到尾没刷新的情况下也会绿：那是假绿。
    const beforePlug = await run(`(() => ({
      badge: document.querySelector('#page-network .badge').textContent,
      disabled: document.getElementById('nav-primary').disabled,
    }))()`);
    await run('window.__mipl.setLink(true)');
    await sleep(3800);
    await settle();
    const afterPlug = await run(`(() => ({
      badge: document.querySelector('#page-network .badge').textContent,
      disabled: document.getElementById('nav-primary').disabled,
    }))()`);
    check(
      beforePlug.disabled === true && afterPlug.disabled === false && afterPlug.badge !== beforePlug.badge,
      '停在网络页：网通了界面自己发现，「下一步」随之解锁（原来卡住的正是这一步）',
      JSON.stringify({ beforePlug, afterPlug })
    );
    await shot('network-replugged-1024x768');

    // 完成页必须一屏放得下（实机反馈：安装完成界面居然能滚）
    await run('window.__mipl.goTo("finish")');
    await sleep(360);
    await settle();
    const finishBox = await run(`(() => {
      const stage = document.getElementById('stage');
      const page = document.getElementById('page-finish');
      return {
        stageScroll: stage.scrollHeight, stageClient: stage.clientHeight,
        pageHeight: page ? Math.round(page.getBoundingClientRect().height) : -1,
        logo: (() => { const el = document.querySelector('.finish__logo'); if (!el) return null; const r = el.getBoundingClientRect(); return [Math.round(r.width), Math.round(r.height), el.draggable]; })(),
      };
    })()`);
    check(finishBox.stageScroll <= finishBox.stageClient + 1, '完成页一屏放得下（不滚动）', JSON.stringify(finishBox));
    check(Boolean(finishBox.logo) && finishBox.logo[2] === false, '完成页 logo 不可拖拽', JSON.stringify(finishBox.logo));
    await shot('finish-1024x768');

    // 全站图片都不该可拖（拖出去会变成复制图片）
    const draggable = await run(`[...document.images].map((img) => ({ src: img.currentSrc.split('/').pop(), draggable: img.draggable, drag: getComputedStyle(img).webkitUserDrag }))`);
    check(draggable.every((item) => item.draggable === false && (item.drag === 'none' || item.drag === '')), '所有图片都不可拖拽', JSON.stringify(draggable));

    // 「实机比例」留档：2560×1600 @167% → 逻辑 1533×958（维护者那台机器的等效视口）
    win.setContentSize(1533, 958);
    await run('window.__mipl.setScale(167)');
    for (const id of ['welcome', 'disk', 'account', 'finish']) {
      await run(`window.__mipl.goTo(${JSON.stringify(id)})`);
      await sleep(320);
      await settle();
      await shot(`real2k-${id}`);
    }
    await run('window.__mipl.setScale(100)');

    // ---------------------------------------------------------- 6.7 滚动归属与留白一致性
    // 维护者 2026-10-05：允许滚动的是**列表**，不是整个页面；上下左右留白必须一致。
    const padding = await run(`(() => {
      const app = getComputedStyle(document.getElementById('app'));
      return [app.paddingTop, app.paddingRight, app.paddingBottom, app.paddingLeft];
    })()`);
    check(new Set(padding).size === 1, '窗口四周留白一致（上下左右同值）', JSON.stringify(padding));

    await run('window.__mipl.goTo("timezone")');   // 26 个时区：一定长过一屏
    await sleep(340);
    await settle();
    const scrollState = await run(`(() => {
      const stage = document.getElementById('stage');
      const list = document.querySelector('#timezone-list .list');
      const wrap = document.getElementById('timezone-list');
      return {
        stageFits: stage.scrollHeight <= stage.clientHeight + 1,
        listScrolls: list ? list.scrollHeight > list.clientHeight + 1 : false,
        listScrollbarGap: list ? Math.round(list.offsetWidth - list.clientWidth - parseFloat(getComputedStyle(list).borderLeftWidth) * 2) : -1,
        wrapFits: wrap ? Math.round(wrap.getBoundingClientRect().height) : -1,
      };
    })()`);
    check(scrollState.stageFits, '长列表页：页面本体不滚动', JSON.stringify(scrollState));
    check(scrollState.listScrolls, '长列表页：列表自己滚', JSON.stringify(scrollState));
    check(scrollState.listScrollbarGap === 0, '列表的滚动条不占位', JSON.stringify(scrollState));
    await shot('scroll-timezone-1024x768');

    // 渐隐必须跟着滚动位置走：不能滚的列表不许加遮罩（否则最后一项被啃掉一块）
    const listGap = await run(`(() => {
      const search = document.querySelector('#timezone-list .search');
      const list = document.querySelector('#timezone-list .list');
      return { gap: Math.round(list.getBoundingClientRect().top - search.getBoundingClientRect().bottom) };
    })()`);
    check(listGap.gap >= 8, '搜索框与列表之间有间距', JSON.stringify(listGap));

    const fadeStates = await run(`(() => {
      const list = document.querySelector('#timezone-list .list');
      const out = { top: list.dataset.scrollFade };
      list.scrollTop = Math.round((list.scrollHeight - list.clientHeight) / 2);
      list.dispatchEvent(new Event('scroll'));
      out.middle = list.dataset.scrollFade;
      list.scrollTop = list.scrollHeight;
      list.dispatchEvent(new Event('scroll'));
      out.bottom = list.dataset.scrollFade;
      list.scrollTop = 0;
      list.dispatchEvent(new Event('scroll'));
      return out;
    })()`);
    check(fadeStates.top === 'bottom', '列表在顶部：只在底部渐隐', JSON.stringify(fadeStates));
    check(fadeStates.middle === 'both', '列表在中间：两侧都渐隐', JSON.stringify(fadeStates));
    check(fadeStates.bottom === 'top', '列表在底部：只在顶部渐隐', JSON.stringify(fadeStates));

    // 默认项在第一行，且**选中别的项不会让列表重排**（选中项不参与排序）。
    // 置顶的是「默认值」而不是「当前选中」：选中一置顶，点一条列表就在手指底下
    // 重排一次，紧接着的第二次点击会落到刚挪上来的那一行上（维护者 2026-10-05）。
    const orderBefore = await run(`[...document.querySelectorAll('#timezone-list .option')].map((el) => el.id)`);
    const pickedId = orderBefore[4];
    await run(`document.getElementById(${JSON.stringify(pickedId)}).click()`);
    await sleep(360);
    await settle();
    const orderAfter = await run(`[...document.querySelectorAll('#timezone-list .option')].map((el) => el.id)`);
    check(orderBefore[0] === 'timezone-list-asia-shanghai', '时区页：默认项（Asia/Shanghai）在第一行', orderBefore[0]);
    check(
      JSON.stringify(orderAfter) === JSON.stringify(orderBefore),
      '选中别的时区之后列表不重排（第一行仍是默认项）',
      `选中 ${pickedId} 前后：${JSON.stringify({ before: orderBefore.slice(0, 3), after: orderAfter.slice(0, 3) })}`
    );

    // 选中之后**不许跳回开头**：整页会重画一次（子树是新的），滚动位置得还回去。
    // 以前这里是「在几百条语言里挑一条，列表跳回开头」（维护者 2026-10-05）。
    const scrollKept = await run(`(async () => {
      const list = document.querySelector('#timezone-list .list');
      list.scrollTop = 240;
      const before = list.scrollTop;
      const target = [...document.querySelectorAll('#timezone-list .option')].find(
        (el) => el.getBoundingClientRect().top > 260
      ) || [...document.querySelectorAll('#timezone-list .option')].at(-1);
      target.click();
      await new Promise((resolve) => setTimeout(resolve, 420));
      const fresh = document.querySelector('#timezone-list .list');
      return { before, after: fresh.scrollTop, rebuilt: fresh !== list };
    })()`);
    check(
      scrollKept.before > 0 && scrollKept.rebuilt && scrollKept.after === scrollKept.before,
      '选中之后列表不回开头（整页确实重画了，滚动位置还回去了）',
      JSON.stringify(scrollKept)
    );
    await shot('timezone-scroll-kept-1024x768');

    await run('window.__mipl.goTo("locale")');   // 5 项，放得下 → 不该有任何遮罩
    await sleep(320);
    await settle();
    const shortList = await run(`(() => {
      const list = document.querySelector('#locale-list .list');
      const last = list ? list.lastElementChild : null;
      return {
        fade: list ? list.dataset.scrollFade : 'missing',
        scrollable: list ? list.scrollHeight > list.clientHeight + 1 : false,
        lastBottom: last ? Math.round(last.getBoundingClientRect().bottom) : -1,
        listBottom: list ? Math.round(list.getBoundingClientRect().bottom) : -1,
      };
    })()`);
    check(shortList.fade === 'none' && !shortList.scrollable, '不用滚的列表不加渐隐（最后一项不吃遮罩）', JSON.stringify(shortList));

    // 焦点环只准有一层：容器的边框 + 光圈已经表达焦点，内层 input 不再叠 outline
    await run('window.__mipl.goTo("timezone")');
    await sleep(300);
    const focusRing = await run(`(() => {
      const input = document.querySelector('#timezone-list .search input');
      input.focus();
      const style = getComputedStyle(input);
      const wrap = getComputedStyle(input.closest('.search'));
      return { inputOutline: style.outlineStyle, wrapBorder: wrap.borderTopColor, focused: document.activeElement === input };
    })()`);
    check(focusRing.focused && focusRing.inputOutline === 'none', '搜索框焦点只有一层（容器），内层不再叠 outline', JSON.stringify(focusRing));

    // 键盘页：主键区图在列表上方，且画的是**真布局**（Issue #65 用它替掉了试打框）
    await run('window.__mipl.goTo("keymap")');
    await sleep(420);
    await settle();
    const keymapBefore = await run(`(() => {
      const block = document.getElementById('keymap-block');
      const list = document.querySelector('#keymap-list .list');
      const stage = document.getElementById('stage');
      if (!block) return { missing: true };
      const blockBox = block.getBoundingClientRect();
      const listBox = list ? list.getBoundingClientRect() : null;
      const caps = [...block.querySelectorAll('.keycap')];
      return {
        rows: block.querySelectorAll('.keyblock__row').length,
        caps: caps.length,
        labelled: caps.filter((cap) => (cap.textContent || '').trim()).length,
        width: Math.round(blockBox.width),
        height: Math.round(blockBox.height),
        aboveList: listBox ? blockBox.bottom <= listBox.top + 1 : false,
        stageFits: stage.scrollHeight <= stage.clientHeight + 1,
      };
    })()`);
    check(!keymapBefore.missing, '键盘页画出了主键区图', JSON.stringify(keymapBefore));
    check(
      keymapBefore.rows >= 5 && keymapBefore.labelled >= 30,
      `主键区图有 5 行、至少 30 个键有字（实际 ${keymapBefore.rows} 行 / ${keymapBefore.labelled} 个）`,
      JSON.stringify(keymapBefore)
    );
    check(keymapBefore.aboveList, '键位图在列表上方', JSON.stringify(keymapBefore));
    check(keymapBefore.stageFits, '键盘页：页面本体不滚动', JSON.stringify(keymapBefore));

    // 换一份布局，图要跟着变 —— 这是「图来自所选映射」而不是「一张通用键盘图」的证据
    const labelAt = (code) =>
      run(`(() => {
        const cap = document.querySelector('.keycap[data-code="${code}"]');
        return cap ? cap.querySelector('.keycap__label').textContent : null;
      })()`);
    const qwertyQ = await labelAt(16);
    const switched = await run(`(() => {
      const item = [...document.querySelectorAll('#keymap-list .option')].find((el) => el.textContent.includes('dvorak'));
      if (!item) return false;
      item.click();
      return true;
    })()`);
    await sleep(420);
    await settle();
    const dvorakAt16 = await labelAt(16);
    check(switched, '键盘页列表里找得到 dvorak', String(switched));
    check(
      qwertyQ && dvorakAt16 && qwertyQ !== dvorakAt16,
      `换布局之后同一个键位的字跟着变（q → ${dvorakAt16}）`,
      `qwerty=${qwertyQ} dvorak=${dvorakAt16}`
    );
    await shot('keymap-block-1024x768');

    // 提交回来的布局名要真的写进 setup（后端 `Plan.keymap` 读的就是它）
    const pickedKeymap = await run('window.__mipl.state().data.keymap');
    check(pickedKeymap === 'dvorak', '选中的布局写进了状态', String(pickedKeymap));
    await run('window.__mipl.setData("keymap", "us")');

    win.setContentSize(1440, 900);
    await sleep(360);
    await run('window.__mipl.setAdvanced(false)');

    // ---------------------------------------------------------- 7. reduced-motion
    try {
      win.webContents.debugger.attach('1.3');
      await win.webContents.debugger.sendCommand('Emulation.setEmulatedMedia', {
        features: [{ name: 'prefers-reduced-motion', value: 'reduce' }],
      });
      await run('window.__mipl.goTo("disk")');
      await sleep(240);
      // 把原始 transform 取回 Node 解析：正则放在注入字符串里会被模板字面量吃掉转义
      const motionState = await run(`[...document.querySelectorAll('[data-anim]')].map((el) => {
        const style = getComputedStyle(el);
        return { transform: style.transform, opacity: style.opacity };
      })`);
      const moved = motionState.filter(({ transform, opacity }) => {
        if (Number(opacity) < 1) return true;
        if (transform === 'none') return false;
        const numbers = transform.match(/-?[\d.]+/g);
        if (!numbers || numbers.length < 6) return true;
        const [a, b, c, d, tx, ty] = numbers.map(Number);
        // 恒等矩阵（translateY(0) 会写成 matrix(1,0,0,1,0,0)）不算位移
        return (
          Math.abs(a - 1) > 0.001 ||
          Math.abs(b) > 0.001 ||
          Math.abs(c) > 0.001 ||
          Math.abs(d - 1) > 0.001 ||
          Math.abs(tx) > 0.5 ||
          Math.abs(ty) > 0.5
        );
      });
      check(moved.length === 0, 'reduced-motion 下页面块没有位移', `仍有 ${moved.length} 个在动：${JSON.stringify(moved.slice(0, 2))}`);
      await win.webContents.debugger.sendCommand('Emulation.setEmulatedMedia', { features: [] });
      win.webContents.debugger.detach();
    } catch (error) {
      notes.push(`reduced-motion 未验（debugger 不可用：${error.message}）`);
      console.log(`  ⚠️  reduced-motion 未验：${error.message}`);
    }

    await run('window.__mipl.setScale(100)');
  } catch (error) {
    failures.push(`探针异常：${error.message || error} —— 最后执行的脚本：${lastRun}`);
  }

  console.log('');
  if (notes.length) for (const note of notes) console.log(`⚠️  ${note}`);
  const files = fs.readdirSync(outDir).filter((name) => name.endsWith('.png')).sort();
  console.log(`截图 ${files.length} 张：`);
  for (const name of files) console.log(`  ${path.join(outDir, name)}`);

  if (failures.length) {
    console.log(`\n❌ 探针失败 ${failures.length} 项：`);
    for (const failure of failures) console.log(`  - ${failure}`);
    app.exit(1);
    return;
  }
  console.log('\n✅ 探针全部通过（离屏旁证；cage / 真 ISO 仍未实测）');
  app.exit(0);
};
