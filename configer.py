import yaml

with open('./db/config.yml', 'r', encoding='utf-8') as f:
    # safe_load 而不是 FullLoader：配置文件是纯数据，没必要允许 Python 标签构造
    result = yaml.safe_load(f)

API_ID = result['API_ID']
API_HASH = result['API_HASH']
BOT_TOKEN = result['BOT_TOKEN']
PROXY_IP = result['PROXY_IP']
PROXY_PORT = result['PROXY_PORT']
ADMIN_ID = result['ADMIN_ID']
FORWARD_ID = result['FORWARD_ID']
UP_TELEGRAM = result['UP_TELEGRAM']
RPC_SECRET = result['RPC_SECRET']
RPC_URL = result['RPC_URL']
# AriaNg 前端地址（/web 深链用）：留空回退到本机 127.0.0.1:6880
ARIANG_BASE = result.get('ARIANG_BASE') or 'http://127.0.0.1:6880'
# 是否允许 /web 下发内嵌 base64(RPC_SECRET) 的 AriaNg 深链，默认关闭
ARIANG_SHARE_SECRET = bool(result.get('ARIANG_SHARE_SECRET', False))
