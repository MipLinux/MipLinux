/**
 * app.js —— 外壳：顶栏 / 步骤轨道 / 内容区 / 动作区 + 页面生命周期
 *
 * 分工：
 *   - 页面（pages/*.js）只画内容、只表达「能不能走」；
 *   - 外壳决定导航、渲染动作区、跑页面切换动效、管对话框与提示；
 *   - 状态在 setup，候选数据在 mock，文案在 i18n —— 外壳自己不存业务状态。
 */

import { h, mount, clear, attachScrollFade } from './dom.js';
import { I18n, LANGUAGE_LABEL } from './i18n.js';
import { ThemeController } from './theme.js';
import { ScaleController, SCALE_AUTO, SCALE_PERCENTS } from './scale.js';
import { Setup } from './setup.js';
import { Mock } from './mock.js';
import { STEP_TITLE_KEY, NO_BACK } from './steps.js';
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
    this.mock = new Mock();
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

    // 首帧之后再扫 Wi-Fi（页面自己会显示「正在扫描…」）
    if (this.page && this.page.wantsWifiScan) {
      this.mock.scanWifi().then(() => this.renderPage({ animate: false }));
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
      mock: this.mock,
      theme: this.theme,
      scale: this.scale,
      /** 页面内部状态变了：只刷新动作区与轨道，不重画页面（不丢输入焦点）。 */
      refresh: () => {
        this.renderActions();
        this.renderShell();
      },
      /** 页面内容变了（例如扫描结果回来）：整页重画，但不跑进场动效。 */
      rerender: () => this.renderPage({ animate: false }),
      scanWifi: async () => {
        await this.mock.scanWifi();
        this.renderPage({ animate: false });
        return this.mock.network.wifi.map((w) => w.ssid);
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
    // 重新进入进度页 = 重跑一轮安装：不清掉上一轮的 100% 与 startedAt，环形进度会停在终点
    if (id === 'progress' && (this.setup.data.progress.done || this.setup.data.progress.cancelled)) {
      this.setup.data.progress = { percent: 0, phase: 0, done: false, cancelled: false };
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
    this.page = page;
    this.animateIn = Boolean(animate) && pageChanged;
    const wrapper = h('div', { class: 'stage__inner', id: `page-${id}`, dataset: { page: id } });
    wrapper.append(page.render(this.makeContext()));
    mount(this.nodes.stage, wrapper);
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
      actions.append(
        button({
          id: 'nav-cancel',
          label: t('progress.cancel'),
          variant: 'tonal',
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

  /** 进度页的「取消安装」：二次确认（不可逆动作用 danger 变体）。 */
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
            this.setup.data.progress = { ...this.setup.data.progress, cancelled: true };
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
      scanWifi: async () => {
        await this.mock.scanWifi();
        this.renderPage({ animate: false });
        return this.mock.network.wifi.map((w) => w.ssid);
      },
      fillAccount: ({ user = 'mipluser', password = 'mipl123456', confirm = password } = {}) => {
        this.setup.set('user', user);
        this.setup.set('password', password);
        this.setup.set('confirm', confirm);
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
