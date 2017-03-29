import config
import Logger
import emitter
import json

from flask import (Flask, abort, jsonify, request)

apns = emitter.APNs()

app = Flask(__name__)

OK = ('', 200, {})
BAD = ('', 400, {})

@app.route('/api/v1/send_push', methods = ['POST'])
def notify():
    ''' Accepts JSON payloads describing a notification to send.
    '''
    data = json.loads(request.data)
    gLog.info(data)
    type = data.get('type')
    if type != 'message':
        gLog.error('invalid message type:', type)
        return BAD

    platform = data.get('platform')
    if platform != 'apple':
        gLog.error('invalid platform:', platform)
        return BAD

    deviceToken = data.get('device_id', '')
    if len(deviceToken) != 64:
        gLog.error('invalid device token:', deviceToken)
        return BAD

    channelName = data.get('channel_name', '')
    if not channelName.startswith('taskme'):
        gLog.info('skipping channel', channelName)
        return OK

    badge = data.get('badge', 1)
    gLog.debug('badge:', badge)

    apns.post(deviceToken, "You have a new message", badge)
    return OK

if __name__ == '__main__':
    gLog.setLevel(gLog.kDebug)
    app.run(port = config.servicePort, debug = config.enableDebugMode)
