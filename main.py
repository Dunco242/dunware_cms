import valkey


def main():
    valkey_uri = 'valkeys://default:AVNS_6zRSMSjL8_4v5QXSzil@dunco-cms-chat-dunware-crm-beta-1.g.aivencloud.com:23350'
    valkey_client = valkey.from_url(valkey_uri)

    valkey_client.set('key', 'hello world')
    key = valkey_client.get('key').decode('utf-8')

    print('The value of key is:', key)

if __name__ == '__main__':
    main()
