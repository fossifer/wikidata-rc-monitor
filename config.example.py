# Edit this file as you want, then move this file to `config.py`
# The bot token provided by @BotFather
telegram_token = ''
# ID of the group in which the bot works
telegram_group_id = -12345
# Rules of recent changes which will be reported to the group
# If a rc item match any of the rules (which may include multiple patterns and
# a complex logic), it will be reported
rc_report_rules = [
    {
        # You can add other keys as comments, eg.
        # 'name': 'foobar',
        'logic': 'any',  # all|any
        'patterns': [
            {
                # All of these key-value pairs must match if
                # a pattern is considered matched
                'comment': r'(wbsetlabeldescriptionaliases|wbsetdescription|wbsetlabel|wbsetaliases)-\w+:\d+\|(yue|wuu|gan|zh(-hans|-hant|-cn|-tw|-hk|-mo|-my|-sg|-classical|-yue|-gan)?)((?!#suggestededit).)+$',
                'type': r'edit'
            },
            {
                'comment': r'wbeditentity-update-languages((?!nameGuzzler).)+$',
                'type': r'edit'
            },
            {
                'comment': r'(restore|undo):0\|\|',
                'type': r'edit'
            }
        ]
    }
]

# one telegram id per line
admin_list_file = './admin.txt'
# one username per line
white_list_file = './white.txt'

# I18n related
language = 'zh'
i18n = {
    'edited': {
        'zh': '编辑',
        'en': ' edited '
    }
}
