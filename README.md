This is a very crude Flask app that accepts notification requests via REST call and creates and sends out APNs
push notifications. This app only works with Apple's legacy TCP connections, not the newer HTTP/2
transport.

You will need one or two certificates from Apple plus their matching private keys: one cert/key for the sandbox
environment and another for production APNs service.

To run:

```
% python notifier.py
 * Running on http://127.0.0.1:8066/ (Press CTRL+C to quit)
 ```

Testing. Get the device token returned to your mobile device from Apple. This should be a 32-byte value in a
Data instance. Convert to a 64-character hex string and plop in the `curl` command below replacing DEVICE_TOKEN
with your value:

```
curl -X POST -H 'Content-Type:application/json' -d '{"platform":"apple","device_id":"DEVICE_TOKEN","type":"message","channel_name":"taskme_foo"}' http://localhost:8066/api/v1/send_push
```
