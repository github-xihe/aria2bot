"""util.py 安全辅助函数的单元测试（标准库 unittest，无需额外依赖）。

运行：python -m unittest discover -s tests -v
"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from util import (  # noqa: E402
    build_aria2_web_reply,
    escape_html,
    is_admin,
    is_safe_clean_path,
    mask_secret,
    truncate_label,
)


class TestEscapeHtml(unittest.TestCase):
    def test_escapes_tags_and_ampersand(self):
        self.assertEqual(escape_html('<b>x</b>&y'), '&lt;b&gt;x&lt;/b&gt;&amp;y')

    def test_keeps_plain_text(self):
        self.assertEqual(escape_html('我的电影 1080p.mkv'), '我的电影 1080p.mkv')

    def test_handles_none_and_numbers(self):
        self.assertEqual(escape_html(None), '')
        self.assertEqual(escape_html(42), '42')

    def test_blocks_injected_anchor(self):
        payload = '<a href="https://evil.example">点我</a>'
        escaped = escape_html(payload)
        self.assertNotIn('<a ', escaped)
        self.assertIn('&lt;a href=', escaped)


class TestIsAdmin(unittest.TestCase):
    def test_same_id_int_and_str(self):
        self.assertTrue(is_admin(123456, 123456))
        self.assertTrue(is_admin('123456', 123456))
        self.assertTrue(is_admin(123456, '123456'))

    def test_other_user(self):
        self.assertFalse(is_admin(999999, 123456))

    def test_garbage_input(self):
        self.assertFalse(is_admin(None, 123456))
        self.assertFalse(is_admin('abc', 123456))
        self.assertFalse(is_admin(123456, '管理员ID'))  # 示例配置里的占位符


class TestTruncateLabel(unittest.TestCase):
    def test_short_label_untouched(self):
        self.assertEqual(truncate_label('abc'), 'abc')

    def test_long_label_truncated_to_limit(self):
        label = truncate_label('x' * 200)
        self.assertEqual(len(label), 60)
        self.assertTrue(label.endswith('…'))

    def test_empty_label_gets_placeholder(self):
        self.assertEqual(truncate_label(''), '未命名')
        self.assertEqual(truncate_label(None), '未命名')


class TestMaskSecret(unittest.TestCase):
    def test_never_returns_plaintext(self):
        masked = mask_secret('super-secret-token')
        self.assertNotIn('super-secret-token', masked)
        self.assertIn('18', masked)

    def test_empty(self):
        self.assertEqual(mask_secret(''), '未配置')


class TestIsSafeCleanPath(unittest.TestCase):
    def test_allows_real_download_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            ok, reason = is_safe_clean_path(os.path.join(tmp, 'downloads'))
            self.assertFalse(ok)  # 目录还不存在
            self.assertIn('不存在', reason)

            target = os.path.join(tmp, 'downloads')
            os.makedirs(target)
            ok, reason = is_safe_clean_path(target)
            self.assertTrue(ok, reason)

    def test_rejects_root_and_system_dirs(self):
        for path in ('/', '', '/etc', '/usr', '/var', '/root', '/app'):
            ok, _ = is_safe_clean_path(path)
            self.assertFalse(ok, f'{path!r} 不应通过')

    def test_rejects_home_dir(self):
        with tempfile.TemporaryDirectory() as fake_home:
            ok, reason = is_safe_clean_path(fake_home, home=fake_home)
            self.assertFalse(ok)
            self.assertIn('主目录', reason)

    def test_rejects_symlink_to_system_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            link = os.path.join(tmp, 'link-to-etc')
            os.symlink('/etc', link)
            ok, _ = is_safe_clean_path(link)
            self.assertFalse(ok)

    def test_rejects_nul_byte(self):
        ok, _ = is_safe_clean_path('/tmp/bad\x00path')
        self.assertFalse(ok)


class TestBuildAria2WebReply(unittest.TestCase):
    RPC_URL = '127.0.0.1:6808/jsonrpc'
    ARIANG_BASE = 'http://192.168.1.10:6880'
    SECRET = 'my-super-rpc-secret'

    def test_default_reply_never_contains_secret(self):
        message, contains_secret = build_aria2_web_reply(
            self.RPC_URL, self.ARIANG_BASE, self.SECRET, share_secret=False)
        self.assertFalse(contains_secret)
        self.assertNotIn(self.SECRET, message)
        self.assertNotIn('bXktc3VwZXItcnBjLXNlY3JldA', message)  # base64(secret)
        self.assertIn('已隐藏', message)

    def test_default_reply_still_has_endpoint(self):
        message, _ = build_aria2_web_reply(self.RPC_URL, self.ARIANG_BASE, self.SECRET)
        self.assertIn('AriaNg: http://192.168.1.10:6880/', message)
        self.assertIn('ws://192.168.1.10:6808/jsonrpc', message)

    def test_share_secret_opt_in_embeds_base64(self):
        import base64
        message, contains_secret = build_aria2_web_reply(
            self.RPC_URL, self.ARIANG_BASE, self.SECRET, share_secret=True)
        self.assertTrue(contains_secret)
        expected = base64.b64encode(self.SECRET.encode()).decode()
        self.assertIn(expected, message)
        self.assertIn('请勿转发', message)

    def test_missing_port_falls_back_to_6808(self):
        message, _ = build_aria2_web_reply('127.0.0.1/jsonrpc', 'http://h:6880', 'x')
        self.assertIn('ws://h:6808/jsonrpc', message)



if __name__ == '__main__':
    unittest.main()
