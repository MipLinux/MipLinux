/**
 * dom.js —— 极小的 DOM 构件帮助函数（不引框架：安装器只有 12 个页面）
 *
 * 为什么不用框架：Live 里没有 npm、也不想为界面加一层构建；页面是静态表单流，
 * `h()` + 事件委托足够，而且 DOM 结构对探针是透明的（探针直接查选择器）。
 */

/** 创建元素：`h('div', { class: 'x', onclick: fn }, child, '文本')`。 */
export function h(tag, props, ...children) {
  const el = document.createElement(tag);
  applyProps(el, props);
  append(el, children);
  return el;
}

export function applyProps(el, props) {
  if (!props) return;
  for (const [key, value] of Object.entries(props)) {
    if (value === null || value === undefined || value === false) continue;
    if (key === 'class') el.className = value;
    else if (key === 'text') el.textContent = String(value);
    else if (key === 'dataset') Object.assign(el.dataset, value);
    else if (key === 'style' && typeof value === 'object') Object.assign(el.style, value);
    else if (key === 'ref' && typeof value === 'function') value(el);
    else if (key.startsWith('on') && typeof value === 'function') {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value === true) el.setAttribute(key, '');
    else el.setAttribute(key, String(value));
  }
}

export function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false || child === true) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

/** 文档片段（一次插入多个节点，少一次重排）。 */
export function frag(...children) {
  const f = document.createDocumentFragment();
  append(f, children);
  return f;
}

export function clear(el) {
  while (el.firstChild) el.firstChild.remove();
  return el;
}

export function mount(el, ...children) {
  clear(el);
  append(el, children);
  return el;
}

export const $ = (selector, root = document) => root.querySelector(selector);
export const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

/**
 * 同一页重画时，把滚动位置记下来 / 还回去。
 *
 * 为什么需要：`renderPage` 是**整棵子树重建** —— 旧列表连同它的 `scrollTop` 一起被丢掉，
 * 新的从 0 开始。表现就是「在几百条语言里挑了一条，列表跳回开头」（维护者 2026-10-05）。
 *
 * 只认**会滚的容器**（内容区 + 面板里的列表，见 components.css 的 `.list`），
 * 不遍历整棵子树：按下标与文档顺序配对，只有这两个层级的**数量**在同一页的两次
 * 渲染之间是稳定的（列表项增减、密码框展开都不影响它）。
 */
const SCROLLERS = '.list';

function scrollerNodes(root) {
  return [root, ...root.querySelectorAll(SCROLLERS)];
}

export function captureScroll(root) {
  return scrollerNodes(root).map((el) => el.scrollTop);
}

export function restoreScroll(root, positions) {
  if (!positions) return;
  const nodes = scrollerNodes(root);
  positions.forEach((top, index) => {
    const el = nodes[index];
    // 没滚过的不赋值：赋值本身会触发布局，而这一趟已经够多布局了
    if (el && top > 0) el.scrollTop = top;
  });
}

/**
 * 滚动渐隐：按「当前能不能滚 / 滚到哪」给元素打 `data-scroll-fade`，
 * CSS 据此只在**确实还有内容**的那一侧加渐隐遮罩。
 *
 * 为什么不用固定遮罩：列表短到不用滚时，固定遮罩会把最后一项的底部啃掉一块
 * （维护者 2026-10-05 实机反馈）。取值：`none` / `top` / `bottom` / `both`。
 */
export function attachScrollFade(el) {
  if (!el) return () => {};
  const update = () => {
    if (el.scrollHeight - el.clientHeight <= 1) {
      el.dataset.scrollFade = 'none';
      return;
    }
    const atTop = el.scrollTop <= 1;
    const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 1;
    el.dataset.scrollFade = atTop ? 'bottom' : atBottom ? 'top' : 'both';
  };
  el.addEventListener('scroll', update, { passive: true });
  if (typeof ResizeObserver === 'function') {
    const observer = new ResizeObserver(update);
    observer.observe(el);
    el.__miplFadeObserver = observer;
  }
  update();
  requestAnimationFrame(update);
  return () => {
    el.removeEventListener('scroll', update);
    if (el.__miplFadeObserver) el.__miplFadeObserver.disconnect();
  };
}
