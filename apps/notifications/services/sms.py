import http.client
import json
from datetime import datetime, timedelta
import random
from django.conf import settings

class OTPService:
    def __init__(self):
        self.base_url = "g9wrl8.api.infobip.com"
        self.api_key = "fdd391fd5cc3ceba12de7de84c46433f-028422eb-3796-47c2-ba21-b5d66a77de30"
        self.app_id = None  # Will be set after initialization

    def initialize_2fa(self):
        conn = http.client.HTTPSConnection(self.base_url)
        payload = json.dumps({
            "name": "WapangajiKiganjani 2FA",
            "enabled": True,
            "configuration": {
                "pinAttempts": 10,
                "allowMultiplePinVerifications": True,
                "pinTimeToLive": "15m",
                "verifyPinLimit": "1/3s",
                "sendPinPerApplicationLimit": "100/1d",
                "sendPinPerPhoneNumberLimit": "10/1d"
            }
        })
        headers = {
            'Authorization': f'App {self.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        conn.request("POST", "/2fa/2/applications", payload, headers)
        response = conn.getresponse()
        data = json.loads(response.read().decode("utf-8"))
        self.app_id = data.get('applicationId')
        return data

    def send_otp(self, phone_number):
        conn = http.client.HTTPSConnection(self.base_url)
        payload = json.dumps({
            "applicationId": self.app_id,
            "messageId": "verify_registration",
            "from": "ServiceSMS",
            "to": str(phone_number)
        })
        headers = {
            'Authorization': f'App {self.api_key}',
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        conn.request("POST", "/2fa/2/pin", payload, headers)
        response = conn.getresponse()
        return json.loads(response.read().decode("utf-8"))