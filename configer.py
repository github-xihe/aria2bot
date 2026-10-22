import yaml

with open('./db/config.yml', 'r', encoding='utf-8') as f:
    result = yaml.load(f.read(), Loader=yaml.FullLoader)

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
# AriaNg 前端地址（/web 深链用）：本地部署优先，留空则回退到 ariang.js.org
ARIANG_BASE = result.get('ARIANG_BASE') or 'http://ariang.js.org'
