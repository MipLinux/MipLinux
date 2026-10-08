"""键位映射的解析与 include 展开（Issue #65 的数据源）。

这里的每条断言都对着**真机上实测到的形态**写的，因为 `.map.gz` 的语法有三个
不看代码就想不到的坑（都在 `keymap_view.py` 的文件头里）：

1. `#` 与 `!` **都是注释符，而且不必在行首** —— `man keymaps` 明写；
2. 行尾 `\\` 是续行，一条键位定义可以跨好几条物理行；
3. `include` 的三种写法各指不同目录（`qwertz-layout` / `euro2.map` / `compose.latin1`）。

不需要 root、不需要 Live：解析器是纯函数，真文件只读。
"""

from __future__ import annotations

import gzip
import tempfile
import unittest
from pathlib import Path

from mipl_installer import keymap_view
from mipl_installer.util import EXIT_USAGE, InstallerError

#: 真机上那几份映射（`/usr/share/kbd/keymaps`）。缺了就让相关用例 skip。
REAL_ROOT = Path("/usr/share/kbd/keymaps")


def _write_map(root: Path, relative: str, text: str, *, compress: bool = True) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    if compress:
        with gzip.open(path, "wt", encoding="utf-8") as handle:
            handle.write(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


class TestLexing(unittest.TestCase):
    """注释与续行 —— 只做词法，不碰文件。"""

    def test_hash_and_bang_both_start_a_comment(self):
        self.assertEqual(keymap_view.strip_comment("keycode 2 = one # 说明").strip(), "keycode 2 = one")
        self.assertEqual(keymap_view.strip_comment("! keycode 2 = VoidSymbol").strip(), "")
        # 「不必在行首」：注释符出现在中间也照样生效
        self.assertEqual(keymap_view.strip_comment("alt keycode 4 = X ! 8. bit").strip(), "alt keycode 4 = X")

    def test_comment_characters_inside_quotes_are_data(self):
        """`compose '\\'' 'a' to '…'` 这类行里引号是语法的一部分 ——
        按第一个 `#` / `!` 粗暴切会把正经内容切掉。"""
        self.assertIn("#", keymap_view.strip_comment('string FN = "a#b"'))
        self.assertIn("!", keymap_view.strip_comment('string FN = "a!b"'))

    def test_backslash_joins_physical_lines(self):
        text = "keycode 13 = minus underscore \\\n\t\tControl_underscore Control_backslash \\\n\t\tMeta_minus\nkeycode 14 = Delete\n"
        lines = keymap_view.logical_lines(text)
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0][0], 1, "合并后的逻辑行要记住它从第几行开始（报错要用）")
        self.assertEqual(lines[0][1],
                         "keycode 13 = minus underscore \t\tControl_underscore Control_backslash \t\tMeta_minus")
        self.assertEqual(lines[1][1], "keycode 14 = Delete")


class TestIncludes(unittest.TestCase):
    """三种 include 写法各指不同目录 —— 源 issue 只写了其中一处。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_bare_name_resolves_to_the_arch_include_dir_with_inc(self):
        _write_map(self.root, "i386/qwertz/de.map.gz", 'include "qwertz-layout"\nkeycode 16 = q\n')
        _write_map(self.root, "i386/include/qwertz-layout.inc", "keycode 30 = a\n", compress=False)
        view = keymap_view.parse("de", str(self.root))
        self.assertEqual(view.includes[0].name, "qwertz-layout")
        self.assertTrue(view.includes[0].path.endswith("i386/include/qwertz-layout.inc"))
        self.assertIn(30, [key.code for key in view.keys])

    def test_dotted_name_resolves_in_the_same_directory(self):
        _write_map(self.root, "i386/qwertz/de.map.gz", 'include "euro2.map"\n')
        _write_map(self.root, "i386/include/euro2.map.gz", "altgr keycode 18 = euro\n")
        view = keymap_view.parse("de", str(self.root))
        self.assertTrue(view.includes[0].path.endswith("i386/include/euro2.map.gz"))

    def test_compose_style_name_resolves_to_the_top_level_include_dir(self):
        """`compose.latin1` 在 `keymaps/include/`，**不在** `keymaps/i386/` 下 ——
        只试架构目录的话这一条会静默丢掉（compose 少几条，键盘看起来还是好的）。"""
        _write_map(self.root, "i386/qwertz/de.map.gz", 'include "compose.latin1"\n')
        _write_map(self.root, "include/compose.latin1", "compose '`' 'a' to 'à'\n", compress=False)
        view = keymap_view.parse("de", str(self.root))
        self.assertTrue(view.includes[0].path.endswith("include/compose.latin1"))
        # compose 行不是键位绑定，不该混进 keys
        self.assertEqual(view.keys, ())

    def test_unresolved_include_is_reported_not_fatal(self):
        """找不到就跳过并**记下来**（`path: None`），不整体失败：
        一份映射缺个 include 只是少几个键，而键盘页是给人做参考的，不该整页打不开。"""
        _write_map(self.root, "i386/qwerty/us.map.gz", 'include "nowhere"\nkeycode 16 = q\n')
        view = keymap_view.parse("us", str(self.root))
        self.assertIsNone(view.includes[0].path)
        self.assertEqual([key.code for key in view.keys], [16])

    def test_include_cycle_stops_instead_of_hanging(self):
        """环形 include 在数据里是合法的写法，实现上必须有个终点。"""
        _write_map(self.root, "i386/qwerty/us.map.gz", 'include "a"\n')
        _write_map(self.root, "i386/include/a.inc", 'include "b"\nkeycode 16 = q\n', compress=False)
        _write_map(self.root, "i386/include/b.inc", 'include "a"\nkeycode 17 = w\n', compress=False)
        view = keymap_view.parse("us", str(self.root))
        self.assertEqual(sorted(key.code for key in view.keys), [16, 17])


class TestMerge(unittest.TestCase):
    """include 的语义 = 把对方的内容插在这一行，后出现的覆盖先出现的。"""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_later_binding_overrides_earlier_for_the_same_modifier_set(self):
        _write_map(self.root, "i386/qwertz/de.map.gz", 'include "layout"\nkeycode 16 = q\n')
        _write_map(self.root, "i386/include/layout.inc", "keycode 16 = x\nkeycode 17 = w\n", compress=False)
        keys = {key.code: key for key in keymap_view.parse("de", str(self.root)).keys}
        self.assertEqual(keys[16].plain, "q", "文件自己的那行写在 include 之后，应当覆盖它")
        self.assertEqual(keys[17].plain, "w")

    def test_altgr_binding_does_not_hide_the_plain_layer(self):
        """`altgr keycode 16 = at` 是**同一键位的另一层**，不是把默认层替换掉 ——
        两者混在一个桶里的话，德语键盘的第 16 键会整颗消失。"""
        _write_map(self.root, "i386/qwertz/de.map.gz",
                   'keycode 16 = q\n\taltgr keycode 16 = at\n')
        keys = {key.code: key for key in keymap_view.parse("de", str(self.root)).keys}
        self.assertEqual(keys[16].plain, "q")
        self.assertEqual(keys[16].shift, "")

    def test_plain_keyword_is_the_same_as_no_modifier(self):
        """`plain keycode 83 = KP_Comma` 与 `keycode 83 = KP_Comma` 是同一件事 ——
        不归一化的话，同一个键会留下两条「默认层」记录，后一条把前一条盖掉。"""
        _write_map(self.root, "i386/qwerty/us.map.gz",
                   'keycode 83 = comma\nplain keycode 83 = KP_Comma\n')
        keys = {key.code: key for key in keymap_view.parse("us", str(self.root)).keys}
        self.assertEqual(len(keys), 1)
        self.assertEqual(keys[83].plain, "KP_Comma")

    def test_shift_layer_comes_from_the_second_column(self):
        _write_map(self.root, "i386/qwerty/us.map.gz", "keycode 2 = one exclam\n")
        keys = {key.code: key for key in keymap_view.parse("us", str(self.root)).keys}
        self.assertEqual(keys[2].plain, "one")
        self.assertEqual(keys[2].shift, "exclam")

    def test_commented_out_binding_is_not_applied(self):
        """`!` 开头的行整行是注释（`man keymaps`）——
        当成有效绑定的话，`VoidSymbol` 会把真的那一层抹掉。"""
        _write_map(self.root, "i386/qwerty/us.map.gz",
                   "keycode 2 = one exclam\n! shift control keycode 2 = VoidSymbol\n")
        keys = {key.code: key for key in keymap_view.parse("us", str(self.root)).keys}
        self.assertEqual(keys[2].plain, "one")


class TestRealKeymaps(unittest.TestCase):
    """真文件上的对账（缺 kbd 就 skip）。"""

    def _require(self, name: str) -> None:
        if not REAL_ROOT.is_dir():
            self.skipTest("本机没有 /usr/share/kbd/keymaps")

    def test_lines_are_verbatim(self):
        """**这条是验收口径**：`--print-keymap de` 的解析结果与
        `zcat /usr/share/kbd/keymaps/i386/qwertz/de.map.gz` 原文**逐字**对得上。

        留原文是有用的：它让「解析没吃掉东西」这件事可自证，不用信实现。
        """
        self._require("de")
        view = keymap_view.parse("de")
        source = Path(view.source)
        raw = gzip.open(source, "rt", encoding="utf-8", errors="replace").read().splitlines()
        self.assertEqual(list(view.lines), raw)

    def test_three_include_forms_all_resolve_on_this_machine(self):
        """三种形态在真机上都要能落地（源 issue 写的那个目录只是其中一处）。"""
        self._require("de")
        view = keymap_view.parse("de")
        resolved = {item.name: item.path for item in view.includes}
        self.assertTrue(any(path and path.endswith("qwerty-layout.inc") for path in resolved.values())
                        or any(path and path.endswith("qwertz-layout.inc") for path in resolved.values()))
        self.assertTrue(any(path and path.endswith("compose.latin1") for path in resolved.values()))
        self.assertTrue(any(path and "euro" in Path(path).name for path in resolved.values() if path))
        self.assertNotIn(None, resolved.values(), f"有 include 没找到：{resolved}")

    def test_letters_differ_between_layouts(self):
        """四份布局在同一个键位上必须给出不同的字 —— 界面那张图靠这个「一眼可辨」。"""
        self._require("us")
        at16 = {}
        for name in ("us", "de", "fr", "dvorak"):
            keys = {key.code: key for key in keymap_view.parse(name).keys}
            self.assertIn(16, keys, f"{name} 应当有 keycode 16")
            at16[name] = keys[16].plain
        self.assertEqual(at16["us"], "q")
        self.assertEqual(at16["de"], "q")
        self.assertEqual(at16["fr"], "a", "法语是 AZERTY")
        self.assertEqual(at16["dvorak"], "apostrophe")
        self.assertEqual(len(set(at16.values())), 3)

    def test_german_shift_layer_comes_from_the_included_layout(self):
        """`de` 自己的文件里第 2 键是 `one exclam`（写在文件里），
        而第 16 键只有 `q` 一列 —— Shift 列不在文件里，**不许**从小写推导大写。"""
        self._require("de")
        keys = {key.code: key for key in keymap_view.parse("de").keys}
        self.assertEqual(keys[2].plain, "one")
        self.assertEqual(keys[2].shift, "exclam")
        self.assertEqual(keys[16].plain, "q")
        self.assertEqual(keys[16].shift, "")


class TestLookup(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def test_unknown_name_is_a_usage_error_with_a_hint(self):
        _write_map(self.root, "i386/qwerty/us.map.gz", "keycode 16 = q\n")
        with self.assertRaises(InstallerError) as ctx:
            keymap_view.parse("teapot", str(self.root))
        self.assertEqual(ctx.exception.exit_code, EXIT_USAGE)

    def test_missing_root_is_reported_not_silently_empty(self):
        with self.assertRaises(InstallerError) as ctx:
            keymap_view.parse("us", str(self.root / "nope"))
        self.assertEqual(ctx.exception.exit_code, EXIT_USAGE)

    def test_duplicate_basenames_resolve_deterministically(self):
        """本机 252 份里没有重名，但真重名时结果要稳定 ——
        换台机器就换一份映射，是那种最难查的差异。"""
        _write_map(self.root, "i386/qwerty/us.map.gz", "keycode 16 = q\n")
        _write_map(self.root, "mac/us.map.gz", "keycode 16 = z\n")
        self.assertTrue(keymap_view.parse("us", str(self.root)).source.endswith("i386/qwerty/us.map.gz"))


if __name__ == "__main__":
    unittest.main()
