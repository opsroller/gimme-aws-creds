"""
Copyright 2018-present SYNETIS.
Licensed under the Apache License, Version 2.0 (the "License");
You may not use this file except in compliance with the License.
You may obtain a copy of the License at
      http://www.apache.org/licenses/LICENSE-2.0
Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and* limitations under the License.*
"""

from __future__ import print_function, absolute_import, unicode_literals

import sys
import base64

from fido2.hid import CtapHidDevice, STATUS
from fido2.client import Fido2Client, ClientError
from threading import Event, Thread

class FakeAssertion(object):
    def __init__(self):
        self.signature = b'fake'
        self.auth_data = b'fake'

class NoFIDODeviceFoundError(Exception):
    pass

class FIDODeviceTimeoutError(Exception):
    pass

class WebAuthnClient(object):

    def __init__(self, okta_org_url, challenge, credentialid):
        """
        :param okta_org_url: Base URL string for Okta IDP.
        :param verify_ssl_certs: Enable/disable SSL verification
        """
        self._okta_org_url = okta_org_url
        self._clients = None
        self._has_prompted = False
        self._challenge = challenge
        self._cancel = Event()
        self._assertions = None
        self._client_data = None 
        self._rp = {'id': okta_org_url[8:], 'name': okta_org_url[8:]}
        self._allow_list = [{
            'type': 'public-key',
            'id': base64.urlsafe_b64decode(credentialid)
        }]

    def locate_device(self):
        # Locate a device
        devs = list(CtapHidDevice.list_devices())
        if not devs:
            print('No FIDO device found', file=sys.stderr)
            raise NoFIDODeviceFoundError

        self._clients = [Fido2Client(d, self._okta_org_url) for d in devs]

    def on_keepalive(self, status):
        if status == STATUS.UPNEEDED and not self._has_prompted:
            print('\nTouch your authenticator device now...\n', file=sys.stderr)
            self._has_prompted = True

    def work(self, client):
        try:
            self._assertions, self._client_data = client.get_assertion(
                self._rp['id'], self._challenge, self._allow_list, timeout=self._cancel, on_keepalive=self.on_keepalive
            )
        except ClientError as e:
            if e.code == ClientError.ERR.DEVICE_INELIGIBLE:
                print('Security key is ineligible', file=sys.stderr) #TODO extract key info
                return
            elif e.code != ClientError.ERR.TIMEOUT:
                raise
            else:
                return
        self._cancel.set()

    def verify(self):
        # If authenticator is not found, prompt
        try:
            self.locate_device()
        except NoFIDODeviceFoundError:
            print('Please insert your security key and press enter...', file=sys.stderr)
            input()
            self.locate_device()

        threads = []
        for client in self._clients:
            t = Thread(target=self.work, args=(client,))
            threads.append(t)
            t.start()

        for t in threads:
            t.join()

        if not self._cancel.is_set():
            print('Operation timed out or no valid Security Key found !', file=sys.stderr)
            raise FIDODeviceTimeoutError

        return self._client_data, self._assertions[0]