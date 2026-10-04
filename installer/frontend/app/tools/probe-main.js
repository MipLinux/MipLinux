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
  const run = (code) => win.webContents.executeJavaScript(code, true);

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

    // ---------------------------------------------------------- 6. 缩放四档
    const scaleResults = [];
    for (const level of [0.85, 1, 1.15, 1.3]) {
      await run(`window.__mipl.setScale(${level})`);
      await sleep(120);
      const applied = await run('getComputedStyle(document.documentElement).getPropertyValue("--ui-scale").trim()');
      scaleResults.push(`${Math.round(level * 100)}%→${applied}`);
      check(Number(applied) === level, `界面缩放 ${Math.round(level * 100)}% 生效`, `实际 ${applied}`);
    }

    // ---------------------------------------------------------- 6.5 布局不变量（实机反馈的回归）
    // 2026-10-04 实机发现：`#root` 没有高度 → `.app` 随内容长高，高级安装（12 步）与
    // WiFi 展开都会把底部动作区顶出视口。下面这些断言把那次问题钉死。
    await run('window.__mipl.setScale(1)');
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

    await run('window.__mipl.setScale(1)');
  } catch (error) {
    failures.push(`探针异常：${error.stack || error.message}`);
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
