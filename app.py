import asyncio
import datetime
import logging
import re
import shutil
from typing import Any

import python_socks

from telethon import TelegramClient, events, Button
import coloredlogs
from telethon.tl.functions.bots import SetBotCommandsRequest
from telethon.tl.types import BotCommand, BotCommandScopeDefault, Message

from async_aria2_client import AsyncAria2Client
from configer import (API_ID, API_HASH, PROXY_IP, PROXY_PORT, BOT_TOKEN, ADMIN_ID, RPC_SECRET,
                      RPC_URL, ARIANG_BASE, ARIANG_SHARE_SECRET)
from util import (get_file_name, progress, byte2_readable, hum_convert,
                  escape_html, is_admin, truncate_label,
                  is_safe_clean_path, build_aria2_web_reply)

coloredlogs.install(level='INFO')
log = logging.getLogger('bot')

proxy = (python_socks.ProxyType.HTTP, PROXY_IP, PROXY_PORT) if PROXY_IP is not None else None
bot = TelegramClient('./db/bot', API_ID, API_HASH, proxy=proxy).start(bot_token=BOT_TOKEN)
client = AsyncAria2Client(RPC_SECRET, f'ws://{RPC_URL}', bot)


@bot.on(events.NewMessage(pattern="/start"))
async def handler(event):
    await event.reply(f"aria2控制机器人,点击复制你的 ADMIN_ID:<code>{event.chat_id}</code>", parse_mode='html',
                      buttons=get_menu())


@bot.on(events.NewMessage(pattern="/web", from_users=ADMIN_ID))
async def handler(event):
    # 默认不下发密钥：深链里的 base64 密钥会永久留在 Telegram 云端聊天记录里
    message, _ = build_aria2_web_reply(RPC_URL, ARIANG_BASE, RPC_SECRET, ARIANG_SHARE_SECRET)
    await event.respond(message)


@bot.on(events.NewMessage(pattern="/info", from_users=ADMIN_ID))
async def handler(event):
    result = await client.get_global_option()
    await event.respond(
        f'下载目录: {result["dir"]}\n'
        f'最大同时下载数: {result["max-concurrent-downloads"]}\n'
        f'允许覆盖: {"是" if result["allow-overwrite"] else "否"}'
    )


@bot.on(events.NewMessage(pattern="/path", from_users=ADMIN_ID))
async def handler(event):
    text = event.raw_text
    text = text.replace('/path ', '').strip()
    params = [{"dir": text}]
    data = await client.change_global_option(params)
    if data['result'] == 'OK':
        await event.respond(f'默认路径设置成功 {text}\n'
                            f'注意: docker启动的话，要在配置文件docker-compose.yml中配置挂载目录')
    else:
        await event.respond(f'默认路径设置失败 {text}')


@bot.on(events.NewMessage(pattern="/help"))
async def handler(event):
    await event.reply(f'''
开启菜单: <code>/start</code>
关闭菜单: <code>/close</code>
系统信息: <code>/info</code>
更换默认下载目录: <code>/path 绝对路径（如 /root/）</code>
ADMIN_ID:<code>{event.chat_id}</code>
    ''', parse_mode='html', buttons=[
        Button.url('更多帮助', 'https://github.com/github-xihe/aria2bot')
    ])


@bot.on(events.NewMessage(from_users=ADMIN_ID))
async def send_welcome(event):
    text = event.raw_text
    log.info(str(datetime.datetime.now()) + ':' + text)
    if text == '⬇️正在下载':
        await downloading(event)
        return
    elif text == '⌛️ 正在等待':
        await waiting(event)
        return
    elif text == '✅ 已完成/停止':
        await stoped(event)
        return
    elif text == '⏸️暂停任务':
        await stop_task(event)
        return
    elif text == '▶️恢复任务':
        await unpause_task(event)
        return
    elif text == '❌ 删除任务':
        await remove_task(event)
        return
    elif text == '❌ ❌ 清空已完成/停止':
        await remove_all(event)
        return
    elif text == '关闭键盘':
        await event.reply("键盘已关闭,/menu 开启键盘", buttons=Button.clear())
        return
    # 获取输入信息
    if text.startswith('http'):
        url_arr = text.split('\n')
        for url in url_arr:
            await client.add_uri(
                uris=[url],
            )
    elif text.startswith('magnet'):
        pattern_res = re.findall(r'magnet:\?xt=urn:btih:[0-9a-fA-F]{40,}.*', text)
        for text in pattern_res:
            await client.add_uri(
                uris=[text],
            )
    elif event.media and event.media.document:
        if event.media.document.mime_type == 'application/x-bittorrent':
            await event.reply('收到了一个种子')
            path = await bot.download_media(event.message)
            await client.add_torrent(path)


def get_media_from_message(message: "Message") -> Any:
    media_types = (
        "audio",
        "document",
        "photo",
        "sticker",
        "animation",
        "video",
        "voice",
        "video_note",
    )
    for attr in media_types:
        media = getattr(message, attr, None)
        if media:
            return media


async def remove_all(event):
    """清空已完成任务 + 删除下载目录：先做路径白名单校验，再让管理员二次确认。"""
    tasks = await client.tell_stopped(0, 500)
    result = await client.get_global_option()
    target = result.get('dir', '')

    ok, reason = is_safe_clean_path(target)
    if not ok:
        await event.respond(
            f'已拒绝清空：下载目录 {escape_html(target)} 未通过安全检查（{reason}）。\n'
            '如确需清空，请先用 /path 把目录设为专用的下载目录。',
            parse_mode='html'
        )
        return

    await event.respond(
        f'将要删除 {len(tasks)} 条已完成/停止任务，并清空目录：\n{escape_html(target)}\n'
        '该操作不可撤销（目录内所有文件都会被删除）。',
        parse_mode='html',
        buttons=[[Button.inline('确认清空', b'clear-all.ok'),
                  Button.inline('取消', b'clear-all.cancel')]],
    )


async def do_remove_all(event):
    """二次确认后的实际清空动作，执行前再校验一次路径。"""
    result = await client.get_global_option()
    target = result.get('dir', '')
    ok, reason = is_safe_clean_path(target)
    if not ok:
        await event.respond(f'清空已中止：{reason}')
        return

    tasks = await client.tell_stopped(0, 500)
    for task in tasks:
        await client.remove_download_result(task['gid'])
    log.info('清空目录 %s，删除任务 %s 条', target, len(tasks))
    shutil.rmtree(target, ignore_errors=True)
    await event.respond('任务已清空,所有文件已删除', parse_mode='html')


async def unpause_task(event):
    tasks = await client.tell_waiting(0, 50)
    # 筛选send_id对应的任务
    if len(tasks) == 0:
        await event.respond('没有已暂停的任务,无法恢复下载', parse_mode='markdown')
        return
    buttons = []
    for task in tasks:
        file_name = get_file_name(task)
        gid = task['gid']
        buttons.append([Button.inline(truncate_label(file_name), 'unpause-task.' + gid)])
    await event.respond('请选择要恢复▶️的任务', parse_mode='html', buttons=buttons)


async def remove_task(event):
    temp_task = []
    # 正在下载的任务
    tasks = await client.tell_active()
    for task in tasks:
        temp_task.append(task)
    # 正在等待的任务
    tasks = await  client.tell_waiting(0, 50)
    for task in tasks:
        temp_task.append(task)
    if len(temp_task) == 0:
        await event.respond('没有正在运行或等待的任务,无删除选项', parse_mode='markdown')
        return
    # 拼接所有任务
    buttons = []
    for task in temp_task:
        file_name = get_file_name(task)
        gid = task['gid']
        buttons.append([Button.inline(truncate_label(file_name), 'del-task.' + gid)])
    await event.respond('请选择要删除❌ 的任务', parse_mode='html', buttons=buttons)


async def stop_task(event):
    tasks = await client.tell_active()
    if len(tasks) == 0:
        await event.respond('没有正在运行的任务,无暂停选项,请先添加任务', parse_mode='markdown')
        return
    buttons = []
    for task in tasks:
        fileName = get_file_name(task)
        gid = task['gid']
        buttons.append([Button.inline(truncate_label(fileName), 'pause-task.' + gid)])

    await event.respond('请选择要暂停⏸️的任务', parse_mode='html', buttons=buttons)


async def downloading(event):
    tasks = await client.tell_active()
    if len(tasks) == 0:
        await event.respond('没有正在运行的任务', parse_mode='html')
        return
    send_msg = ''
    for task in tasks:
        completedLength = task['completedLength']
        totalLength = task['totalLength']
        downloadSpeed = task['downloadSpeed']
        fileName = get_file_name(task)
        if fileName == '':
            continue
        prog = progress(int(totalLength), int(completedLength))
        size = byte2_readable(int(totalLength))
        speed = hum_convert(int(downloadSpeed))

        send_msg = (send_msg + '任务名称: <b>' + escape_html(fileName) + '</b>\n进度: ' + prog
                   + '\n大小: ' + size + '\n速度: ' + speed + '/s\n\n')
    if send_msg == '':
        await event.respond('个别任务无法识别名称，请使用aria2Ng查看', parse_mode='html')
        return
    await event.respond(send_msg, parse_mode='html')


async def waiting(event):
    tasks = await client.tell_waiting(0, 30)
    if len(tasks) == 0:
        await event.respond('没有正在等待的任务', parse_mode='markdown')
        return
    send_msg = ''
    for task in tasks:
        completedLength = task['completedLength']
        totalLength = task['totalLength']
        downloadSpeed = task['downloadSpeed']
        fileName = get_file_name(task)
        prog = progress(int(totalLength), int(completedLength))
        size = byte2_readable(int(totalLength))
        speed = hum_convert(int(downloadSpeed))
        send_msg = (send_msg + '任务名称: ' + escape_html(fileName) + '\n进度: ' + prog
                   + '\n大小: ' + size + '\n速度: ' + speed + '\n\n')
    await event.respond(send_msg, parse_mode='html')


async def stoped(event):
    tasks = await client.tell_stopped(0, 30)
    if len(tasks) == 0:
        await event.respond('没有已完成或停止的任务', parse_mode='markdown')
        return
    send_msg = ''
    for task in reversed(tasks):
        completedLength = task['completedLength']
        totalLength = task['totalLength']
        downloadSpeed = task['downloadSpeed']
        fileName = get_file_name(task)
        prog = progress(int(totalLength), int(completedLength))
        size = byte2_readable(int(totalLength))
        speed = hum_convert(int(downloadSpeed))
        send_msg = (send_msg + '任务名称: ' + escape_html(fileName) + '\n进度: ' + prog
                   + '\n大小: ' + size + '\n速度: ' + speed + '\n\n')
    await event.respond(send_msg, parse_mode='html')


@events.register(events.CallbackQuery)
async def BotCallbackHandler(event):
    # inline 按钮的回调同样要鉴权：没有这一步，任何拿到按钮的人都能暂停/删除任务
    if not is_admin(event.sender_id, ADMIN_ID):
        await event.answer('无权限', alert=True)
        log.warning('拒绝非管理员回调: sender_id=%s data=%r', event.sender_id, event.data)
        return

    try:
        action, gid = str(event.data, encoding="utf-8").split('.', 1)
    except ValueError:
        await event.answer('无效的操作', alert=True)
        return

    await event.answer()

    if action == 'pause-task':
        await client.pause(gid)
    elif action == 'unpause-task':
        await client.unpause(gid)
    elif action == 'del-task':
        data = await client.remove(gid)
        if 'error' in data:
            await bot.send_message(ADMIN_ID, data['error']['message'])
        else:
            await bot.send_message(ADMIN_ID, '删除成功')
    elif action == 'clear-all':
        if gid == 'ok':
            await do_remove_all(event)
        else:
            await event.respond('已取消清空')


def get_menu():
    return [
        [
            Button.text('⬇️正在下载', resize=True),
            Button.text('⌛️ 正在等待', resize=True),
            Button.text('✅ 已完成/停止', resize=True)
        ],
        [
            Button.text('⏸️暂停任务', resize=True),
            Button.text('▶️恢复任务', resize=True),
            Button.text('❌ 删除任务', resize=True),
        ],
        [
            Button.text('❌ ❌ 清空已完成/停止', resize=True),
            Button.text('关闭键盘', resize=True),
        ],
    ]


# 入口
async def main():
    await client.connect()
    bot.add_event_handler(BotCallbackHandler)
    bot_me = await bot.get_me()
    commands = [
        BotCommand(command="start", description='开始使用'),
        BotCommand(command="help", description='帮助'),
        BotCommand(command="info", description='设置信息'),
        BotCommand(command="web", description='ariaNg在线地址'),
    ]
    await bot(
        SetBotCommandsRequest(
            scope=BotCommandScopeDefault(),
            lang_code='',
            commands=commands
        )
    )
    log.info(f'{bot_me.username} bot启动成功...')


loop = asyncio.get_event_loop()
try:
    loop.create_task(main())
    loop.run_forever()
except KeyboardInterrupt:
    pass
