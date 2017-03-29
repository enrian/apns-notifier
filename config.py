# The port that the service listens on for notification requests.
#
servicePort = 8066

# Set to True to enable Flask debug mode
#
enableDebugMode = False

# The template to use when generating notification payloads. Takes two items:
# - alert text to show in banner or alert
# - badge count to show on app icon
#
payloadTemplate = '{{"aps":{{"alert":"{}", "badge":{}, "sound":"2beep.aiff"}}}}'

# Set to True to use Apple's development sandbox notification services. NOTE: must match right key/cert
#
useSandbox = True

# The certificate to present when connecting to APNs
#
apnsCertFile = "apns-cert.pem"

# The private key for the certificate.
#
apnsKeyFile = "apns-key.pem"

# Number of seconds to allow a socket to remain open with no traffic before recycling it.
#
socketAgeLimit = 2 * 60         # 2 minutes

# Number of seconds to allow a notification request to stay in the history list (worst-case).
#
historyAgeLimit = 1 * 60 * 60   # 1 hour

# Number of seconds to wait for data when reading from the APNs socket
#
socketReadTimeout = 2.0         # 2 seconds

# Number of times to try to post a notification before giving up on it.
#
maxPostRetries = 5
