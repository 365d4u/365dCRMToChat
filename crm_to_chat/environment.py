"""Select an explicit server-owned database environment; never export secrets."""


def mysql_config(environment):
    style = environment.get('CRM_TO_CHAT_DB_ENV_STYLE', 'conv')
    names = {
        'conv': ('CONV_DB_HOST', 'CONV_DB_PORT', 'CONV_DB_USER', 'CONV_DB_PASSWORD', 'CONV_DB_NAME'),
        'respond': ('DB_HOST', 'DB_PORT', 'DB_USER', 'DB_PASSWORD', 'CHAT_DB_NAME'),
    }
    if style not in names:
        raise ValueError('Unknown CRM_TO_CHAT_DB_ENV_STYLE')
    host, port, user, password, database = names[style]
    if any(not environment.get(name) for name in (host, user, password, database)):
        raise ValueError('Required chat_db runtime configuration missing')
    port_number = int(environment.get(port, '3306'))
    if not 1 <= port_number <= 65535:
        raise ValueError('Invalid chat_db port')
    return {'host': environment[host], 'port': port_number, 'user': environment[user],
            'password': environment[password], 'database': environment[database]}
