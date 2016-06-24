# Copyright 2015 NEC Corporation.  All rights reserved.
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

from oslo_log import log as logging
from oslo_serialization import jsonutils as json

from tempest.lib.common import rest_client
from tempest.lib import exceptions
from tempest.lib.services.identity.v3 import token_client

import six

class K2KTokenClient(rest_client.RestClient):
    def __init__(self, auth_url,
                 disable_ssl_certificate_validation=None,
                 ca_certs=None, trace_requests=None):
	self.token_client = token_client.V3TokenClient(auth_url)
 
    def get_token(self, **kwargs):
        return self.token_client.get_token(**kwargs)
    
    def auth(self, **kwargs):
        return self.token_client.auth(**kwargs)

    def post(self, **kwargs):
        return self.token_client.post(**kwargs)

    def _get_ecp_assertion(self, sp_id, token=None):
	
	"""Obtains a token from the authentication service
        :param sp_id: registered Service Provider id in Identity Provider
        :param token: a token to perform K2K Federation.
        Accepts one combinations of credentials.
        - token, sp_id
        Validation is left to the Service Provider side.
        """
        body = {
            "auth": {
                "identity": {
                    "methods": [
                        "token"
                    ],
                    "token": {
                        "id": token
                    }
                },
                "scope": {
                    "service_provider": {
                        "id": sp_id
                    }
                }
            }
        }
	
	self.body = body
	url = 'http://localhost:5000/v3/auth/OS-FEDERATION/saml2/ecp'
        headers = {'Accept': 'application/json'}
        
	resp, body = self.token_client.raw_request(method='POST',
					url=url,
                                        headers=headers,
                                       	body=json.dumps(body, sort_keys=True))
 
	self.expected_success(200, resp.status)
        return six.text_type(body)


    def get_unscoped_token(self, assertion, sp_auth_url, ecp_url):
        """Send assertion to a Keystone SP and get an unscoped token"""
	
	headers={'Content-Type': 'application/vnd.paos+xml'}

	r, b = self.token_client.raw_request(method='POST',
						url=ecp_url,
						headers=headers,
						body=assertion)
	
	cookie = r['set-cookie'].split(';')[0]
        headers={'Content-Type': 'application/vnd.paos+xml',
                 'Cookie': cookie}

        resp, body = self.token_client.get(url=sp_auth_url, headers=headers)
        fed_token_id = resp['x-subject-token']
        return fed_token_id


    def get_scoped_token(self, _token, sp_auth_url, sp_projects_url):
	"""Send an unscoped token and get a scoped token"""

        # Getting proejct_id
	headers = {'X-Auth-Token': _token}
        r, b = self.token_client.get(url=sp_projects_url, headers=headers)
        project_id = str(b['projects'][0]['id'])

	headers = {'x-auth-token': _token,
                   'Content-Type': 'application/json'}
        body = {
            "auth": {
                "identity": {
                    "methods": [
                        "token"
                    ],
                    "token": {
                        "id": _token
                    }
                },
                "scope": {
                    "project": {
                        "id": project_id
                    }
                }
            }
        }

        resp, body = self.post(url=sp_auth_url,
                               body=json.dumps(body, sort_keys=True),
                               headers=headers)
        self.expected_success(201, resp.status)
        scoped_token_id = resp['x-subject-token']
	return scoped_token_id, dict(body['token'])
