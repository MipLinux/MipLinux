/**
 * app.js —— 外壳：顶栏 / 步骤轨道 / 内容区 / 动作区 + 页面生命周期
 *
 * 分工：
 *   - 页面（pages/*.js）只画内容、只表达「能不能走」；
 *   - 外壳决定导航、渲染动作区、跑页面切换动效、管对话框与提示；
 *   - 状态在 setup，候选数据在 **backend**，文案在 i18n —— 外壳自己不存业务状态。
 *
 * 「候选数据」那个数据源有两个实现，**同形**：
 *   - `Backend`（`backend.js`）—— 产品路径，问真后端；
 *   - `Mock`（`mock.js`）—— 只在 `MIPL_PROBE=1` 的离屏自检里出场。
 * 页面只认 `ctx.backend`，不知道自己在跟哪一个说话。
 */

import { h, mount, clear, captureScroll, restoreScroll, attachScrollFade } from './dom.js';
import { I18n, LANGUAGE_LABEL } from './i18n.js';
import { ThemeController } from './theme.js';
import { ScaleController, SCALE_AUTO, SCALE_PERCENTS } from './scale.js';
import { Setup } from './setup.js';
import { Mock } from './mock.js';
import { Backend } from './backend.js';
import { STEP_TITLE_KEY, NO_BACK, shouldRestartRun } from './steps.js';
import * as motion from './motion.js';
import {
  button,
  chip,
  menu,
  meter,
  stepsRail,
  dialogNode,
  snackbarNode,
} from './components.js';
import { PAGES } from './pages/index.js';

const launch = (window.mipl && window.mipl.config) || {
  theme: 'dark',
  themeSource: 'auto',
  lang: 'zh_CN',
  uiScale: 0,
  renderer: 'gpu',
  probe: false,
};

class App {
  constructor() {
    this.i18n = new I18n(launch.lang);
    this.theme = new ThemeController({ theme: launch.theme, source: launch.themeSource });
    // 缩放：默认自动档；推荐值由启动器算（device_scale.py 的纯函数），这里不复制判据
    this.scale = new ScaleController({ mode: SCALE_AUTO, recommended: launch.uiScale || 0 });
    this.setup = new Setup();
    // 离屏探针跑 Mock（可复现、不碰真设备）；产品路径一律走真后端。
    // 两个实现同形，页面读的键一个不差 —— 见 `backend.js` 的文件头。
    this.backend = launch.probe ? new Mock() : new Backend();
    this.page = null;
    this.nodes = {};
    this.snackbarTimer = null;
    /** 渲染代次：`renderPage` 是 async（要先等旧页淡出），并发调用时旧的那次必须作废 */
    this.renderToken = 0;
    /** 本轮渲染是不是「刚进这一页」——页面用它决定要不要跑交错动画 */
    this.animateIn = false;
  }

  /* ------------------------------------------------------------ 启动 */

  async boot() {
    // 渲染模式：software（SwiftShader）时走「低配模式」，见 base.css 的 [data-renderer='software']
    document.documentElement.dataset.renderer = launch.renderer === 'software' ? 'software' : 'gpu';
    await this.i18n.load();
    this.theme.start();
    this.scale.apply();
    this.buildShell();
    this.i18n.subscribe(() => {
      this.renderShell();
      this.renderPage({ animate: false });
    });
    this.setup.subscribe(() => this.renderActions());
    this.renderShell();
    await this.renderPage({ animate: false });

    // 首帧**已经出来了**才去取真数据：问后端要盘、要三份名单、要网络状态
    // 加起来是几百毫秒，压在首帧前面就是一块白屏。取回来再重画一次，
    // 中途用户看到的是欢迎页（数据还没用上）。
    if (typeof this.backend.load === 'function') {
      this.backend
        .load()
        .then(() => this.renderPage({ animate: false }))
        .catch((error) => console.error('[mipl-installer] 取候选数据失败', error));
    }

    // 首帧之后再扫 Wi-Fi（页面自己会显示「正在扫描…」）
    if (this.page && this.page.wantsWifiScan) {
      this.backend.scanWifi().then(() => this.renderPage({ animate: false }));
    }

    if (launch.probe) this.exposeProbeApi();
  }

  buildShell() {
    const brand = h('div', { class: 'brand' }, [
      h('span', { class: 'brand__mark' }),
      h('span', { class: 'brand__text' }, [
        h('span', { class: 'brand__name', text: 'MipLinux' }),
        h('span', { class: 'brand__sub', text: 'Installer' }),
      ]),
    ]);

    const langToggle = chip({
      id: 'lang-toggle',
      label: LANGUAGE_LABEL[this.i18n.other],
      icon: 'translate',
      onClick: () => this.i18n.setLanguage(this.i18n.other),
    });
    langToggle.setAttribute('aria-label', this.i18n.t('lang.tooltip', LANGUAGE_LABEL[this.i18n.other]));

    this.nodes.langToggle = langToggle;
    this.nodes.themeMenu = this.buildThemeMenu();
    this.nodes.scaleMenu = this.buildScaleMenu();

    const topbar = h('header', { class: 'topbar' }, [
      brand,
      h('span', { class: 'topbar__spacer' }),
      langToggle,
      this.nodes.themeMenu,
      this.nodes.scaleMenu,
    ]);

    this.nodes.stepsbar = h('div', { class: 'stepsbar', id: 'stepsbar' });
    this.nodes.rail = h('aside', { class: 'rail', id: 'rail' });
    this.nodes.stage = h('section', { class: 'stage', id: 'stage' });
    this.nodes.actions = h('footer', { class: 'actions', id: 'actions' });
    this.nodes.snackbar = h('div', { id: 'snackbar-root' });
    this.nodes.overlay = h('div', { id: 'overlay-root' });

    const shell = h('div', { class: 'app', id: 'app' }, [
      topbar,
      h('main', { class: 'shell' }, [this.nodes.rail, this.nodes.stage]),
      this.nodes.actions,
    ]);

    mount(
      document.getElementById('root'),
      h('div', { class: 'aurora', 'aria-hidden': 'true' }, [
        h('span', { class: 'aurora__blob aurora__blob--1' }),
        h('span', { class: 'aurora__blob aurora__blob--2' }),
        h('span', { class: 'aurora__blob aurora__blob--3' }),
      ]),
      h('div', { class: 'grain', 'aria-hidden': 'true' }),
      shell,
      this.nodes.snackbar,
      this.nodes.overlay
    );
  }

  /** 主题菜单：跟随时间 / 亮 / 暗（三个词都在审核稿里） */
  buildThemeMenu() {
    const t = (key, ...args) => this.i18n.t(key, ...args);
    const source = this.theme.source;
    const label =
      source === 'auto'
        ? t('theme.following')
        : source === 'dark'
          ? t('theme.lockedDark')
          : t('theme.lockedLight');
    return menu({
      id: 'theme-menu',
      ariaLabel: label,
      trigger: { kind: 'icon', icon: source === 'dark' ? 'moon-stars' : 'sun', label },
      items: [
        { value: 'auto', label: t('theme.following'), checked: source === 'auto' },
        { value: 'light', label: t('theme.toLight'), checked: source === 'light' },
        { value: 'dark', label: t('theme.toDark'), checked: source === 'dark' },
      ],
      onSelect: (value) => {
        this.theme.setMode(value);
        this.renderShell();
        this.showSnackbar(
          this.theme.source === 'auto'
            ? this.i18n.t('theme.following')
            : this.i18n.t(this.theme.source === 'dark' ? 'theme.lockedDark' : 'theme.lockedLight')
        );
      },
    });
  }

  /** 缩放菜单：自动检测 / 100% / 167% / 200%（百分比是数字，不需要翻译） */
  buildScaleMenu() {
    const t = (key, ...args) => this.i18n.t(key, ...args);
    const label = t('scale.tooltip', this.scale.percent);
    return menu({
      id: 'scale-menu',
      ariaLabel: label,
      trigger: { kind: 'icon', icon: 'magnifying-glass', label },
      items: [
        { value: SCALE_AUTO, label: t('scale.auto'), checked: this.scale.isAuto },
        ...SCALE_PERCENTS.map((percent) => ({
          value: percent,
          label: `${percent}%`,
          checked: !this.scale.isAuto && this.scale.mode === percent,
        })),
      ],
      onSelect: (value) => {
        this.scale.setMode(value);
        this.renderShell();
        this.showSnackbar(this.i18n.t('scale.tooltip', this.scale.percent));
      },
    });
  }

  /** 顶栏 / 步骤轨道 / 窄屏步骤条 —— 语言、主题、进度变了就重画这几块。 */
  renderShell() {
    const t = (key, ...args) => this.i18n.t(key, ...args);
    const steps = this.setup.steps.map((id) => ({ id, label: t(STEP_TITLE_KEY[id]) }));

    // 顶栏三个开关：整只换掉（比原地改子节点简单，也避免事件监听器叠加）
    const nextLang = chip({
      id: 'lang-toggle',
      label: LANGUAGE_LABEL[this.i18n.other],
      icon: 'translate',
      onClick: () => this.i18n.setLanguage(this.i18n.other),
    });
    nextLang.setAttribute('aria-label', t('lang.tooltip', LANGUAGE_LABEL[this.i18n.other]));
    nextLang.setAttribute('title', t('lang.tooltip', LANGUAGE_LABEL[this.i18n.other]));
    this.nodes.langToggle.replaceWith(nextLang);
    this.nodes.langToggle = nextLang;

    const nextThemeMenu = this.buildThemeMenu();
    this.nodes.themeMenu.replaceWith(nextThemeMenu);
    this.nodes.themeMenu = nextThemeMenu;

    const nextScaleMenu = this.buildScaleMenu();
    this.nodes.scaleMenu.replaceWith(nextScaleMenu);
    this.nodes.scaleMenu = nextScaleMenu;

    const rail = stepsRail({ steps, index: this.setup.index, onJump: () => {} });
    const progress = h('div', { class: 'stack' }, [
      h('span', { class: 'label', id: 'rail-progress', text: t('step.of', this.setup.index + 1, this.setup.stepCount) }),
      meter({ percent: this.setup.stepPercent }),
    ]);
    rail.querySelector('.steps__head').replaceChildren(progress);
    mount(this.nodes.rail, rail);
    // 12 步时轨道放不下：把当前步滚进视野（不用平滑滚动 —— 切页时滚动动画会和入场打架）
    const current = rail.querySelector('.step[data-state="current"]');
    if (current && current.scrollIntoView) current.scrollIntoView({ block: 'nearest' });
    // 轨道的渐隐同样按滚动位置来（只有真还有内容时才淡出）
    attachScrollFade(rail.querySelector('.steps__body'));

    mount(
      this.nodes.stepsbar,
      h('span', { class: 'label', text: t('step.of', this.setup.index + 1, this.setup.stepCount) }),
      meter({ percent: this.setup.stepPercent })
    );
  }

  /* ------------------------------------------------------------ 页面 */

  makeContext() {
    return {
      animateIn: this.animateIn,
      t: (key, ...args) => this.i18n.t(key, ...args),
      i18n: this.i18n,
      setup: this.setup,
      /**
       * 候选数据（运行系统的现状：候选盘 / 网络 / 三份名单）。**产品路径上它来自真后端**；
       * 名字不叫 `mock` 了 —— 那个名字只在探针里成立，留着会让下一个人以为数据是假的。
       *
       * 注意别与 `window.mipl.backend` 混了：那个是**通道**（怎么问），
       * 这个是**数据**（问到了什么）。页面只读这个。
       */
      backend: this.backend,
      theme: this.theme,
      scale: this.scale,
      /** 页面内部状态变了：只刷新动作区与轨道，不重画页面（不丢输入焦点）。 */
      refresh: () => {
        this.renderActions();
        this.renderShell();
      },
      /** 页面内容变了（例如扫描结果回来）：整页重画，但不跑进场动效。 */
      rerender: () => this.renderPage({ animate: false }),
      /** 扫 Wi-Fi。`{rescan:true}` = 让 NetworkManager 真扫一遍（几秒）；默认用缓存。 */
      scanWifi: async (options) => {
        await this.backend.scanWifi(options);
        this.renderPage({ animate: false });
        return this.backend.network.wifi.map((w) => w.ssid);
      },
      dialog: (options) => this.openDialog(options),
      closeDialog: (result) => this.closeDialog(result),
      snackbar: (text) => this.showSnackbar(text),
      goTo: (id) => this.goToId(id),
      goNext: () => this.next(),
      goBack: () => this.back(),
    };
  }

  async renderPage({ animate = true } = {}) {
    const token = (this.renderToken += 1);
    const id = this.setup.stepId;
    // 「**重新进入**进度页 = 重跑一轮安装」：不清掉上一轮的终态，环形进度会停在终点、
    // `startedAt` 还在，于是新的一轮根本不会开始。
    //
    // 关键在那个「重新」：只有**从别的页走过来**才算重跑。判据与理由都写在
    // `steps.shouldRestartRun()` 上（那里有测试 —— 这条写错会变成失败后无限重装）。
    const progress = this.setup.data.progress;
    if (id === 'progress' && shouldRestartRun(progress, { cameFromProgress: this.page?.id === 'progress' })) {
      // 整份丢掉（含 `startedAt`）：`pages/progress.js` 的 `startRun()` 会重新铺一份，
      // 这里只需要「没有终态、也没有 startedAt」——形状归进度页自己管，不在这儿复述。
      this.setup.data.progress = {};
    }
    const page = PAGES[id];
    if (!page) throw new Error(`没有这个页面模块：${id}`);
    const pageChanged = !this.page || this.page.id !== id;
    if (animate && this.page && this.nodes.stage.firstElementChild) {
      await motion.pageLeave(this.nodes.stage.firstElementChild);
    }
    // 等淡出的这段时间里可能又来了新的一次渲染：作废，别把两页同时挂上去
    if (token !== this.renderToken) return;
    // 上一页如果有定时器（进度页的模拟事件流就是），离开时必须停 ——
    // 否则它会在别的页面上把人「推」到下一步去
    if (this.page && this.page !== page && typeof this.page.onLeave === 'function') {
      this.page.onLeave(this.makeContext());
    }
    // 同一页重画（`rerender()`）要把滚动位置还回去：页面子树是重建的，`scrollTop`
    // 天然归零 —— 在几百条语言里选一条就会跳回开头（维护者 2026-10-05）。
    // **换页不还**：新的一页从顶部开始，那不叫「丢了位置」。
    const scrollSpots = pageChanged ? null : captureScroll(this.nodes.stage);
    this.page = page;
    this.animateIn = Boolean(animate) && pageChanged;
    const wrapper = h('div', { class: 'stage__inner', id: `page-${id}`, dataset: { page: id } });
    wrapper.append(page.render(this.makeContext()));
    mount(this.nodes.stage, wrapper);
    restoreScroll(this.nodes.stage, scrollSpots);
    // 「进入这一页」只在这一页真的被换上时发生**一次**（与 `onLeave` 对称）：
    // 网络页的轮询挂在这里，重画不会把它叠成两个。
    if (pageChanged && typeof page.onEnter === 'function') page.onEnter(this.makeContext());
    this.renderShell();
    this.renderActions();
    if (animate) motion.pageEnter(wrapper);
  }

  renderActions() {
    const t = (key, ...args) => this.i18n.t(key, ...args);
    const page = this.page;
    const setup = this.setup;
    const ctx = this.makeContext();
    const actions = this.nodes.actions;
    clear(actions);
    if (!page) return;

    const primaryLabel = page.primaryLabel ? page.primaryLabel(ctx) : '';
    const complete = page.isComplete ? page.isComplete(ctx) : true;
    const blocked = page.blockedReason ? page.blockedReason(ctx) : '';
    const isFinish = setup.stepId === 'finish';
    const isProgress = setup.stepId === 'progress';

    if (!setup.isFirst && !NO_BACK.has(setup.stepId)) {
      actions.append(
        button({
          id: 'nav-back',
          label: t('nav.back'),
          variant: 'ghost',
          icon: 'arrow-left',
          onClick: () => this.back(),
        })
      );
    }

    actions.append(
      h('span', {
        class: `actions__hint${blocked ? ' actions__blocked' : ''}`,
        id: 'actions-hint',
        text: blocked || '',
      })
    );

    if (isProgress) {
      // 装失败了要留一条出路：进度页在 `NO_BACK` 里，不特判的话人会被卡在一个
      // 不会再动的页面上。**不给「重试」** —— 盘上已经是半成品，
      // 在残骸上接着装是这个项目明令禁止的事（`pipeline.run` 的失败收尾）。
      if (setup.data.progress && setup.data.progress.failed) {
        actions.append(
          button({
            id: 'nav-back',
            label: t('nav.back'),
            variant: 'tonal',
            icon: 'arrow-left',
            onClick: () => this.back(),
          })
        );
        return;
      }
      const cancelling = Boolean(setup.data.progress && setup.data.progress.cancelRequested);
      actions.append(
        button({
          id: 'nav-cancel',
          label: t('progress.cancel'),
          variant: 'tonal',
          disabled: cancelling,
          onClick: () => this.confirmCancel(),
        })
      );
      return;
    }

    actions.append(
      button({
        id: 'nav-primary',
        label: primaryLabel || (isFinish ? t('finish.reboot') : t('nav.next')),
        variant: page.primaryError ? 'danger' : 'primary',
        icon: isFinish ? 'power' : null,
        disabled: !complete,
        onClick: () => {
          if (page.primaryError) motion.weigh(document.getElementById('nav-primary'));
          if (page.onPrimary) page.onPrimary(this.makeContext());
          else this.next();
        },
      })
    );
  }

  goToId(id) {
    const index = this.setup.steps.indexOf(id);
    if (index < 0) return false;
    this.setup.go(index);
    this.renderPage();
    return true;
  }

  next() {
    if (this.page && this.page.isComplete && !this.page.isComplete(this.makeContext())) return;
    this.setup.next();
    this.renderPage();
  }

  back() {
    this.setup.back();
    this.renderPage();
  }

  /* ------------------------------------------------------------ 对话框 / 提示 */

  openDialog({ title, body, actions = [], onClose }) {
    const scrim = h('div', { class: 'scrim', id: 'dialog-scrim' }, []);
    const node = dialogNode({ title, body, actions });
    scrim.append(node);
    scrim.addEventListener('click', (event) => {
      if (event.target === scrim && onClose) onClose();
    });
    mount(this.nodes.overlay, scrim);
    motion.popIn(scrim);
    const first = scrim.querySelector('button, input');
    if (first) first.focus();
    return scrim;
  }

  async closeDialog() {
    const scrim = this.nodes.overlay.firstElementChild;
    if (scrim) await motion.popOut(scrim);
  }

  /**
   * 进度页的「取消安装」：二次确认（不可逆动作用 danger 变体）。
   *
   * 确认之后**不立刻翻页**：这里只是把请求写进状态，真正送出去（`SIGUSR1` → 后端在
   * **阶段之间**停）由进度页做。后端回了退出码 130 才回摘要页 ——
   * 提前跳走会让人以为已经停了，而盘上的 `pacstrap` 还在跑。
   */
  confirmCancel() {
    const t = (key, ...args) => this.i18n.t(key, ...args);
    const scrim = this.openDialog({
      title: t('cancel.title'),
      body: [h('p', { class: 'muted', text: t('cancel.body') })],
      actions: [
        button({
          id: 'cancel-keep',
          label: t('cancel.keep'),
          variant: 'ghost',
          onClick: () => this.closeDialog(),
        }),
        button({
          id: 'cancel-confirm',
          label: t('cancel.confirm'),
          variant: 'danger',
          onClick: () => {
            this.closeDialog();
            this.setup.data.progress = { ...this.setup.data.progress, cancelRequested: true };
            this.renderPage({ animate: false });
          },
        }),
      ],
    });
    return scrim;
  }

  showSnackbar(text) {
    clear(this.nodes.snackbar);
    const node = snackbarNode(text);
    this.nodes.snackbar.append(node);
    motion.popIn(node);
    if (this.snackbarTimer) clearTimeout(this.snackbarTimer);
    this.snackbarTimer = setTimeout(() => {
      clear(this.nodes.snackbar);
    }, 2600);
  }

  /* ------------------------------------------------------------ 探针接口 */

  exposeProbeApi() {
    window.__mipl = {
      state: () => ({
        page: this.setup.stepId,
        index: this.setup.index,
        steps: this.setup.steps,
        advanced: this.setup.advanced,
        language: this.i18n.language,
        theme: this.theme.theme,
        themeSource: this.theme.source,
        scale: this.scale.percent,
        data: JSON.parse(JSON.stringify(this.setup.data)),
      }),
      goTo: (id) => this.goToId(id),
      setLanguage: (code) => {
        const changed = this.i18n.setLanguage(code);
        return changed;
      },
      setTheme: (mode) => {
        if (mode === 'auto') this.theme.unfollow();
        else {
          this.theme.source = mode;
          this.theme.theme = mode;
          this.theme.apply();
        }
        this.renderShell();
        return this.theme.theme;
      },
      setScale: (mode) => {
        this.scale.setMode(mode === 'auto' ? 'auto' : Number(mode));
        this.renderShell();
        return this.scale.percent;
      },
      openThemeMenu: () => {
        const trigger = document.querySelector('#theme-menu');
        if (trigger) trigger.click();
        return !document.getElementById('theme-menu-popup').hidden;
      },
      openScaleMenu: () => {
        const trigger = document.querySelector('#scale-menu');
        if (trigger) trigger.click();
        return !document.getElementById('scale-menu-popup').hidden;
      },
      setAdvanced: (value) => {
        this.setup.setAdvanced(value);
        this.renderPage({ animate: false });
        return this.setup.steps;
      },
      setData: (key, value) => {
        this.setup.set(key, value);
        return this.setup.data[key];
      },
      rerender: () => this.renderPage({ animate: false }),
      scanWifi: async (options) => {
        await this.backend.scanWifi(options);
        this.renderPage({ animate: false });
        return this.backend.network.wifi.map((w) => w.ssid);
      },
      /**
       * 离屏自检用：模拟「外面的世界变了」（插上网线 / 拔掉网线）。
       *
       * 改的是 Mock 的**现状**、不是 `network`（上一次问回来的结果）—— 真实后端里
       * 这两件事发生在 nmcli 那边，界面要下一次 `refreshNetwork()` 才知道。
       * 靠这个时间差才验得出「停留在网络页时，网通了界面会不会自己发现」。
       * 只有 `launch.probe`（Mock）才挂这个入口，产品路径上没有它。
       */
      setLink: (connected) => {
        if (connected) this.backend.connectWired();
        else this.backend.disconnectNetwork();
        return this.backend.network;
      },
      countUndefinedStrings: () => {
        const html = document.getElementById('root').innerText || '';
        return (html.match(/⟨[^⟩]+⟩/g) || []).length;
      },
      openDialog: () => this.confirmCancel(),
      closeDialog: () => this.closeDialog(),
      finish: () => {
        window.mipl && window.mipl.reboot();
      },
    };
  }
}

const app = new App();

// 探针模式不自动跑到「已安装」这种终态；正常启动就一个入口
window.addEventListener('DOMContentLoaded', () => {
  app.boot().catch((error) => {
    console.error('[mipl-installer] 启动失败', error);
    document.getElementById('root').textContent = `启动失败：${error.message}`;
  });
});

export { app };
