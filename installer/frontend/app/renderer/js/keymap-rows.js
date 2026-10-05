/**
 * keymap-rows.js —— 主键区怎么排、键帽上写什么（纯函数，无 DOM）
 *
 * `keymap_view.py` 给的是**事实**：`[{code, plain, shift}]`，一个键一条。
 * 「哪几个 code 是一行」「Backspace 该多宽」「`minus` 该画成 `-`」都是**界面**的事，
 * 所以在这里，不在后端，也不在页面里 —— 页面只管把这些行画成 DOM。
 *
 * ## 为什么不把单列的键推导出大写
 *
 * `qwertz-layout.inc` 里是 `keycode 16 = q`，德语键盘上 Shift+Q 确实打出 `Q` ——
 * 但**这一列不在文件里**。`man keymaps` 写得很清楚：生效的是「按下的修饰键权重之和」
 * 指向的那一列，文件只写了一列，其余列由**内核默认键盘表**兜底。
 * 也就是说 `Q` 的出处是内核，不是这份映射；这一层看不到内核默认表，
 * 画出来就是替文件说了它没说的话。所以只画 `plain` 与**文件里真写了**的 `shift`。
 */

/** 主键区（不画功能键区、数字小键盘、方向键 —— Issue #65 明确只要主键区）。 */
export const MAIN_ROWS = [
  [1, 41, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14],
  [15, 16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27, 28],
  [29, 30, 31, 32, 33, 34, 35, 36, 37, 38, 39, 40, 43],
  [42, 86, 44, 45, 46, 47, 48, 49, 50, 51, 52, 53, 54],
  [56, 57, 100],
];

/** 宽度（flex 份数）。只给明显不同的那几个：其余一律 1。 */
const WIDTH = {
  14: 1.8, // Backspace
  15: 1.4, // Tab
  28: 1.8, // Enter
  42: 2.2, // 左 Shift
  54: 2.2, // 右 Shift
  56: 1.3, // Alt
  57: 6.0, // 空格
  100: 1.3, // AltGr
};

/**
 * keysym → 键帽上的字。
 *
 * 只收**有约定俗成写法**的那些：`minus` 画 `-`、`bracketleft` 画 `[`。
 * 认不出来的一律原样显示（`VoidSymbol` 就写 `VoidSymbol`）——
 * 编一个更好看的名字，比显示一个看不懂的真名字更糟。
 */
const KEYSYM_LABELS = {
  space: '',
  // 数字键的 keysym 是**单词**，不是字符 —— `man keymaps` 明说这是为了不和
  // 数字记法（`keycode 2 = ...`）撞车。不映射的话整排会画成
  // `one two three four` —— 第一版就是这么画出来的，图能看，但没人认得出那是数字排。
  zero: '0',
  one: '1',
  two: '2',
  three: '3',
  four: '4',
  five: '5',
  six: '6',
  seven: '7',
  eight: '8',
  nine: '9',
  Return: '⏎',
  BackSpace: '⌫',
  Escape: 'Esc',
  Tab: '⇥',
  Caps_Lock: 'Caps',
  Shift: 'Shift',
  Control: 'Ctrl',
  Alt: 'Alt',
  AltGr: 'AltGr',
  minus: '-',
  equal: '=',
  bracketleft: '[',
  bracketright: ']',
  backslash: '\\',
  semicolon: ';',
  apostrophe: "'",
  grave: '`',
  comma: ',',
  period: '.',
  slash: '/',
  less: '<',
  greater: '>',
  bar: '|',
  asciitilde: '~',
  asciicircum: '^',
  quotedbl: '"',
  numbersign: '#',
  dollar: '$',
  percent: '%',
  ampersand: '&',
  asterisk: '*',
  parenleft: '(',
  parenright: ')',
  underscore: '_',
  plus: '+',
  braceleft: '{',
  braceright: '}',
  colon: ':',
  question: '?',
  exclam: '!',
  at: '@',
  euro: '€',
  cent: '¢',
  mu: 'µ',
  KP_Comma: ',',
  Meta_space: '␣',
};

export function keycapLabel(keysym) {
  if (!keysym) return '';
  if (Object.prototype.hasOwnProperty.call(KEYSYM_LABELS, keysym)) {
    return KEYSYM_LABELS[keysym];
  }
  // `U+20AC` 这种写法原样留着：它是 unicode 记法，认得出的人一眼认得出
  return keysym;
}

/**
 * `[{code, plain, shift}]` → 主键区的行。
 *
 * 映射里没有的 code 也照样出一个**空键位**（`label: ''`）——
 * 键盘的物理排布不因为映射少写一个键就变窄，缺的键留白比整行错位更能说明问题。
 */
export function buildRows(keys) {
  const byCode = new Map();
  for (const key of keys || []) byCode.set(key.code, key);

  return MAIN_ROWS.map((codes) =>
    codes.map((code) => {
      const found = byCode.get(code);
      const plain = found ? found.plain || '' : '';
      const shift = found ? found.shift || '' : '';
      return {
        code,
        plain,
        shift,
        label: keycapLabel(plain),
        shiftLabel: keycapLabel(shift),
        width: WIDTH[code] || 1,
      };
    })
  );
}

/** 这张图值不值得画：一个键都没解析出来时页面不画空框（`仅静态检查` 也不该显示假图）。 */
export function hasAnyKey(rows) {
  return (rows || []).some((row) => row.some((key) => key.label || key.shiftLabel));
}
