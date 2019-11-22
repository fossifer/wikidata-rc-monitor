import re
import json
import config
import logging
import requests
from bs4 import BeautifulSoup
from time import sleep
from sseclient import SSEClient as EventSource
import threading
from telegram.ext import Updater, CommandHandler


logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                     level=logging.INFO)

# Telegram bot updater
updater, dispatcher = None, None

whitelist = []
adminlist = []
user_re = re.compile(r'^(.*?)（全域账户 \|')
comment_re = re.compile(r'/\* wbset(description|label|alias)(?:es)?-\w+:\d+\|(.+?) \*/')
item_re = re.compile(r'(描述|标签|别名) / (yue|wuu|gan|zh(-hans|-hant|-cn|-tw|-hk|-mo|-my|-sg|-classical|-yue|-gan)?)')


def normalize_username(username):
    rst = username.replace('_', ' ')
    return rst[0].upper() + rst[1:]


def add_whitelist_user(update, context):
    global whitelist
    msg = update.message
    rmsg = msg.reply_to_message
    target = None
    if rmsg:
        # Reply a previous bot message to add the corresponding user
        # Assuming it's from the bot itself
        match = user_re.search(rmsg.text)
        if match:
            target = normalize_username(match.group(1))
    if not target:
        # /adduser Example
        tmp = msg.text.split(' ', 1)
        target = normalize_username(tmp[1]) if len(tmp) > 1 else None
    if not target:
        context.bot.send_message(msg.chat.id, '错误：无法解析目标用户名，取消操作', reply_to_message_id=msg.message_id)
        return

    # TODO: IP range
    if target in whitelist:
        context.bot.send_message(msg.chat.id, '警告：目标已在白名单中，取消操作', reply_to_message_id=msg.message_id)
        return

    whitelist.append(target)
    update_whitelist_user()
    context.bot.send_message(msg.chat.id, f'已加入用户 <a href="https://www.wikidata.org/wiki/Special:Contribs/{target}">{target}</a> 至白名单', reply_to_message_id=msg.message_id, parse_mode='HTML', disable_web_page_preview=True)


def remove_whitelist_user(update, context):
    global whitelist
    msg = update.message
    rmsg = msg.reply_to_message
    target = None
    if rmsg:
        # Reply a previous bot message to add the corresponding user
        # Assuming it's from the bot itself
        match = user_re.search(rmsg.text)
        if match:
            target = normalize_username(match.group(1))
    if not target:
        # /deluser Example
        tmp = msg.text.split(' ', 1)
        target = normalize_username(tmp[1]) if len(tmp) > 1 else None
    if not target:
        context.bot.send_message(msg.chat.id, '错误：无法解析目标用户名，取消操作', reply_to_message_id=msg.message_id)
        return

    # TODO: IP range
    if target not in whitelist:
        context.bot.send_message(msg.chat.id, '警告：目标不在白名单中，取消操作', reply_to_message_id=msg.message_id)
        return

    whitelist = [i for i in whitelist if i != target]
    update_whitelist_user()
    context.bot.send_message(msg.chat.id, f'已从白名单中移除用户 <a href="https://www.wikidata.org/wiki/Special:Contribs/{target}">{target}</a>', reply_to_message_id=msg.message_id, parse_mode='HTML', disable_web_page_preview=True)


def load_whitelist_user():
    global whitelist
    try:
        whitelist = open(config.white_list_file, encoding='utf-8').readlines()
        whitelist = [i.strip() for i in whitelist if i.strip()]  # strip empty lines
    except:
        logging.warning(f'load_whitelist_user: cannot read file {config.white_list_file}; check your config file')
        return


def update_whitelist_user():
    global whitelist
    try:
        with open(config.white_list_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(whitelist))
    except:
        logging.warning(f'update_whitelist_user: cannot write to file {config.white_list_file}; check your config file')
        return


def add_admin(update, context):
    pass


def remove_admin(update, context):
    pass


def load_admin():
    try:
        adminlist = open(config.admin_list_file, encoding='utf-8').readlines()
        adminlist = [i for i in adminlist if i]  # strip empty lines
    except:
        logging.warning(f'load_admin: cannot read file {config.admin_list_file}; check your config file')
        return


def update_admin():
    try:
        with open(config.admin_list_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(adminlist))
    except:
        logging.warning(f'update_admin: cannot write to file {config.admin_list_file}; check your config file')
        return


# used by the event source loop
def handle_rc_item(item):
    """
    params:
        item: a json object, representing a recent change item
    return: none
    raise: none"""

    def pattern_match(pattern):
        # All of the items in the pattern must match
        # Note that if a key does not exist it will be treated as an empty string
        return all([re.search(v, item.get(k, '')) for k, v in pattern.items()])


    def convert_into_str():
        # convert the rc item into string in order to output
        urls = {
            'wikidata': 'https://www.wikidata.org/wiki/',
            'sul': 'https://meta.wikimedia.org/wiki/Special:CentralAuth/',
            'zhwiki': 'https://zh.wikipedia.org/wiki/'
        }
        if item.get('custom_label'):
            item['custom_title'] = f"{item['custom_label']}（{item['title']}）"
        else:
            item['custom_title'] = item['title']
        item['custom_diff'] = ''
        for k in item.keys():
            if k.startswith('diff_old_'):
                prop = k[len('diff_old_'):]
                item['custom_diff'] += f'旧 {prop}：{item[k]}\n新 {prop}：{item["diff_new_"+prop]}\n'
        return (
            '<a href="{wikidata}Special:Contribs/{user}">{user}</a>'
            '（<a href="{sul}{user}">全域账户</a> |'
            ' <a href="{zhwiki}Special:Contribs/{user}">中文维基</a>）'
            '编辑了<a href="{wikidata}{title}">{custom_title}</a>'
            '（<a href="{wikidata}Special:diff/{new_rev}">差异</a> |'
            ' <a href="{wikidata}{title}?action=edit&undoafter={old_rev}&undo={new_rev}">撤销</a> |'
            ' <a href="{wikidata}{title}?action=history">历史</a>）\n'
            '摘要：{comment}\n'
            '{custom_diff}'
        ).format(**item, **urls,
            old_rev=item['revision']['old'], new_rev=item['revision']['new'])

    def fetch_data():
        # fetch additional data including alias, label and description in corresponding language
        # the function will directly manipulate `item` and return nothing

        # get the term & language being edited
        match = comment_re.search(item['comment'])
        if not match: return
        term, language = match.group(1), match.group(2)
        # get the label
        r = requests.get('https://www.wikidata.org/w/api.php', params={
            'uselang': language,
            'action': 'query',
            'revids': item['revision']['new'],
            'prop': 'pageterms',
            'wbptterms': 'label',
            'utf8': 1,
            'format': 'json'
        })
        rst = None
        try:
            rst = r.json()
        except ValueError:
            logging.warning(f"Failed to decode data about revid {item['revision']['new']}")
            return
        rst = rst.get('query', {}).get('pages', {})
        if not len(rst.values()):
            logging.warning(f"Empty data about revid {item['revision']['new']}")
            return
        label = list(rst.values())[0].get('terms', {}).get('label', [None])[0]

        # all manipulated keys will begin with 'custom_'
        item['custom_label'] = label


    def get_diff():
        # get detailed diff if the edit summary is fuzzy
        r = requests.get('https://www.wikidata.org/w/api.php', params={
            'uselang': 'zh',
            'action': 'compare',
            'fromrev': item['revision']['old'],
            'torev': item['revision']['new'],
            'utf8': 1,
            'format': 'json'
        })
        rst = None
        try:
            rst = r.json()
        except ValueError:
            logging.warning(f"Failed to decode data about revid {item['revision']['new']}")
            return False
        rst = rst.get('compare', {}).get('*', '')
        soup = BeautifulSoup(rst, 'html.parser')
        tr = soup.find_all('tr')
        will_report = False
        for i in range(0, len(tr), 2):
            td = tr[i].find_all('td')
            if not td: continue
            match = item_re.match(td[0].get_text())
            if match:
                addedlines = tr[i+1].select('.diff-addedline')
                item[f'diff_old_{match.group(2)} {match.group(1)}'] = '\n'.join([e.get_text() for e in tr[i+1].select('.diff-deletedline')])
                item[f'diff_new_{match.group(2)} {match.group(1)}'] = '\n'.join([e.get_text() for e in tr[i+1].select('.diff-addedline')])
                will_report = True
        return will_report


    # ignore whitelisted users
    # TODO: IP range
    if item['user'] in whitelist:
        return

    will_report = False
    for rule in config.rc_report_rules:
        patterns = rule.get('patterns', [])
        if rule.get('logic', 'all') == 'all':
            will_report = all(map(pattern_match, patterns))
        else:  # the logic is 'any'
            will_report = any(map(pattern_match, patterns))
        if will_report:
            if re.search(r'wbeditentity-update-languages|(restore|undo):0\|\|', item['comment']):
                if not get_diff():
                    continue
            fetch_data()
            # Report the item to the telegram group
            updater.bot.send_message(chat_id=config.telegram_group_id,
                text=convert_into_str(), parse_mode='HTML', disable_web_page_preview=True)
            # If we decided to report, there is no need to do further checks
            break


def start_telegram_loop():
    global updater
    updater = Updater(token=config.telegram_token, use_context=True)
    dispatcher = updater.dispatcher
    #dispatcher.add_handler(CommandHandler('start', lambda update, context: context.bot.send_message(update.message.chat.id, str(update.message.chat.id), reply_to_message_id=update.message.message_id)))
    dispatcher.add_handler(CommandHandler('au', add_whitelist_user))
    dispatcher.add_handler(CommandHandler('adduser', add_whitelist_user))
    dispatcher.add_handler(CommandHandler('aa', add_admin))
    dispatcher.add_handler(CommandHandler('addadmin', add_admin))
    dispatcher.add_handler(CommandHandler('du', remove_whitelist_user))
    dispatcher.add_handler(CommandHandler('deluser', remove_whitelist_user))
    dispatcher.add_handler(CommandHandler('da', remove_admin))
    dispatcher.add_handler(CommandHandler('deladmin', remove_admin))
    updater.start_polling()


def start_event_source_loop():
    url = 'https://stream.wikimedia.org/v2/stream/recentchange'
    for event in EventSource(url):
        if event.event != 'message':
            continue
        try:
            change = json.loads(event.data)
        except ValueError:
            logging.warning('Failed to decode the event\n' + event.data)
            continue

        # We only need recent changes from wikidata
        if change['wiki'] != 'wikidatawiki':
            continue

        handle_rc_item(change)


def main():
    load_whitelist_user()
    load_admin()
    threading.Thread(target=start_telegram_loop).start()
    threading.Thread(target=start_event_source_loop).start()
    while True:
        try:
            sleep(600)
        except KeyboardInterrupt:
            exit(0)


if __name__ == '__main__':
    main()
