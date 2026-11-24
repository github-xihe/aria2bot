import base64
import html
import os
import secrets
from pathlib import Path
from urllib.parse import urlparse

import ffmpy3


# 这些目录一旦被 rmtree 会直接毁掉系统或容器本体，清空下载目录前一律拒绝
FORBIDDEN_CLEAN_PATHS = {
    os.sep,
    '/bin', '/boot', '/dev', '/etc', '/home', '/lib', '/lib64', '/media',
    '/mnt', '/opt', '/proc', '/root', '/run', '/sbin', '/srv', '/sys',
    '/usr', '/var', '/app', '/tmp',
}


def escape_html(value):
    """转义不可信文本，用于 parse_mode='html' 的消息插值。

    aria2 里种子名/文件名完全由下载源决定，直接拼接会让对方有机会注入
    <a href>、<b> 之类的标签（钓鱼链接、伪造管理员消息样式）。
    """
    if value is None:
        return ''
    return html.escape(str(value), quote=False)


def is_admin(sender_id, admin_id):
    """容错比较发送者 id 与 ADMIN_ID（配置里可能是 int 或 str）。"""
    try:
        return int(sender_id) == int(admin_id)
    except (TypeError, ValueError):
        return False


def truncate_label(text, limit=60):
    """截断 inline 按钮文本：Telegram 限制 64 字符，超长会导致发送失败。"""
    label = str(text or '').strip() or '未命名'
    if len(label) <= limit:
        return label
    return label[:max(limit - 1, 1)] + '…'


def mask_secret(secret):
    """脱敏提示：只告诉长度，不回显任何明文字符。"""
    if not secret:
        return '未配置'
    return f'已隐藏（{len(str(secret))} 位）'


def is_safe_clean_path(path, home=None):
    """清空下载目录前的白名单校验。

    返回 (ok, reason)。只有明确指向一个层级足够深的真实目录时才允许删除，
    避免 /path 被设成 /、/etc、家目录之类的位置后一键清空误伤。
    """
    raw = str(path or '').strip()
    if not raw:
        return False, '目录为空'
    if '\x00' in raw:
        return False, '路径包含非法字符'

    real = os.path.realpath(raw)
    if real in FORBIDDEN_CLEAN_PATHS:
        return False, '拒绝对系统目录执行清空'

    if len(Path(real).parts) < 2:
        return False, '目录层级过浅'

    home_dir = os.path.realpath(home or os.path.expanduser('~'))
    if real == home_dir:
        return False, '拒绝清空用户主目录'

    if not os.path.isdir(real):
        return False, '目录不存在'

    return True, ''


async def imgCoverFromFile(input, output):
    # ffmpeg -i 001.jpg -vf 'scale=320:320'  001_1.jpg
    ff = ffmpy3.FFmpeg(
        inputs={input: None},
        outputs={output: ['-y', '-vframes', '1', '-loglevel', 'quiet']}
    )
    await ff.run_async()
    await ff.wait()


def get_file_name(task):
    if task.__contains__('bittorrent'):
        if task['bittorrent'].__contains__('info'):
            # bt下载
            return task['bittorrent']['info']['name']
        # bt元信息
        return task['files'][0]['path']
    filename = task['files'][0]['path'].split('/')[-1]
    if filename == '':
        pa = urlparse(task['files'][0]['uris'][0]['uri'])
        filename = os.path.basename(pa.path)
    return filename


def progress(total_length, completed_length):
    if total_length != 0:
        return '{:.2f}%'.format(completed_length / total_length * 100)
    else:
        return "0"


def byte2_readable(size):
    '''
    auth: wangshengke@kedacom.com ；科达柯大侠
    递归实现，精确为最大单位值 + 小数点后三位
    '''

    def strofsize(integer, remainder, level):
        if integer >= 1024:
            remainder = integer % 1024
            integer //= 1024
            level += 1
            return strofsize(integer, remainder, level)
        else:
            return integer, remainder, level

    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    integer, remainder, level = strofsize(size, 0, 0)
    if level + 1 > len(units):
        level = -1
    return ('{}.{:>03d}{}'.format(integer, remainder, units[level]))

def hum_convert(value):
    units = ["B", "KB", "MB", "GB", "TB", "PB"]
    size = 1024.0
    for i in range(len(units)):
        if (value / size) < 1:
            return "%.2f%s" % (value, units[i])
        value = value / size


def generate_hex_string(length=16):
    """
    生成16位gid
    :param length:
    :return:
    """
    # 生成随机字节
    random_bytes = secrets.token_bytes(length // 2)  # 每个字节对应两个十六进制字符
    # 将字节转换为十六进制字符串
    hex_string = random_bytes.hex()
    return hex_string

def build_aria2_web_reply(rpc_url, ariang_base, rpc_secret, share_secret=False):
    """生成 /web 的回复文本。

    默认（share_secret=False）只给地址和脱敏提示，绝不会把 RPC 密钥写进消息；
    显式开启后才生成内嵌 base64(密钥) 的 AriaNg 深链。返回 (文本, 是否含明文密钥)。
    """
    host_port, _, rpc_path = str(rpc_url or '').partition('/')
    rpc_port = host_port.partition(':')[2] or '6808'
    ws_host = urlparse(ariang_base or '').hostname or host_port.partition(':')[0]
    base = str(ariang_base or '').rstrip('/')

    if not share_secret:
        return (
            f'AriaNg: {base}/\n'
            f'RPC 地址: ws://{ws_host}:{rpc_port}/{rpc_path}\n'
            f'RPC 密钥: {mask_secret(rpc_secret)}（请在 AriaNg 设置页手动填写）\n'
            '如需直接生成带密钥的深链，在 config.yml 里设置 ARIANG_SHARE_SECRET: true'
        ), False

    key = base64.b64encode(str(rpc_secret).encode('utf-8')).decode('utf-8')
    return (
        f'{base}/#!/settings/rpc/set/ws/{ws_host}/{rpc_port}/{rpc_path}/{key}\n'
        '⚠️ 该链接内嵌 RPC 密钥（ARIANG_SHARE_SECRET=true），会留在聊天记录里，请勿转发或截图外发。'
    ), True
