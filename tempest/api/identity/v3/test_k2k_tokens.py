#Copyright 2015 OpenStack Foundation
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

from oslo_utils import timeutils
import six
from tempest.api.identity import base
from tempest import test

from tempest.lib.services.identity.v3 import k2k_token_client

import json  
import os

from tempest import config
CONF = config.CONF

class K2KTokensV3Test(base.BaseIdentityV3Test):

    @test.idempotent_id('6f8e4436-fc96-4282-8122-e41df57197a9')
    def test_get_unscoped_scoped_token(self):

        idp_auth_url = 'http://localhost:5000/v3/auth/tokens'
	username = CONF.auth.admin_username 	
	password = CONF.auth.admin_password
	project_name = CONF.auth.admin_project_name
        
        r, b = self.get_credentials(idp_auth_url, password)
        #idp_auth_url = r['content-location']
        sp_id = b['token']['service_providers'][0]['id']
        ecp_url = str(b['token']['service_providers'][0]['sp_url'])
        sp_auth_url = str(b['token']['service_providers'][0]['auth_url'])
	#self.sp_ip contains the port number 5000
        sp_ip = str(b['token']['service_providers'][0]['sp_url'].split('/')[2])
	sp_token_auth_url = 'http://'+ sp_ip  +'/v3/auth/tokens'


	k2k_client = k2k_token_client.K2KTokenClient(
						auth_url=idp_auth_url) 		
        idp_token, resp = k2k_client.get_token(auth_data=True,
						project_name=project_name,
						password=password,
						username=username)
        # check if idp_token is valid
        self.assertNotEmpty(idp_token)
        self.assertIsInstance(idp_token, six.string_types)
        now = timeutils.utcnow()
        expires_at = timeutils.normalize_time(
            timeutils.parse_isotime(resp['expires_at']))
        self.assertGreater(resp['expires_at'],
                           resp['issued_at'])
        self.assertGreater(expires_at, now)
        subject_name = resp['user']['name']
        self.assertEqual(subject_name, username)
        self.assertEqual(resp['methods'][0], 'password')


        assertion = k2k_client._get_ecp_assertion(sp_id=sp_id, token=idp_token)
        unscoped_token = k2k_client.get_unscoped_token(assertion, sp_auth_url, ecp_url)  
	# check if unscoped_token is valid
        self.assertNotEmpty(unscoped_token)
        self.assertIsInstance(unscoped_token, six.string_types)
        now = timeutils.utcnow()
        expires_at = timeutils.normalize_time(
            timeutils.parse_isotime(resp['expires_at']))
        self.assertGreater(resp['expires_at'],
                           resp['issued_at'])
        self.assertGreater(expires_at, now)
        subject_name = resp['user']['name']
        self.assertEqual(subject_name, username)
        self.assertEqual(resp['methods'][0], 'password')
	

        sp_client = k2k_token_client.K2KTokenClient(auth_url=sp_token_auth_url) 
        scoped_token = sp_client.get_scoped_token(unscoped_token)
	# check if scoped_token is valid
        self.assertNotEmpty(scoped_token)
        self.assertIsInstance(scoped_token, six.string_types)
        now = timeutils.utcnow()
        expires_at = timeutils.normalize_time(
            timeutils.parse_isotime(resp['expires_at']))
        self.assertGreater(resp['expires_at'],
                           resp['issued_at'])
        self.assertGreater(expires_at, now)
        subject_name = resp['user']['name']
        self.assertEqual(subject_name, username)
        self.assertEqual(resp['methods'][0], 'password')


    def get_credentials(self, idp_auth_url, password):
        """ Get a token with default scope containing the service
            provider's credentials"""
        body = {
            "auth": {
              "identity": {
                "methods": ["password"
                 ],
                 "password": {
                   "user": {
                     "name": "admin",
                     "domain": { "id": "default"
                      },
                     "password": password
                  }
                }
              }
            }
          }

        headers = {"Content-Type": "application/json"}
	# there has to be a nicer way. I think a cleaner way is to import rest_client 
	# directly instead of accessing it through k2k_token_client THEN token_client
	# THEN rest_client
        token_client = k2k_token_client.K2KTokenClient(idp_auth_url).token_client
	r, b = token_client.post(url=idp_auth_url, headers=headers, body=json.dumps(body))
        return r, b

