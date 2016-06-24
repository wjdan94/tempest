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
            
from tempest.lib.services.identity.v3 import k2k_token_client
from tempest import config
import json  
import os

CONF = config.CONF

class scoped_token_client():
    def get_scoped_token(self):
        idp_auth_url = 'http://localhost:5000/v3/auth/tokens'
	username = CONF.auth.admin_username 	
	password = CONF.auth.admin_password
	project_name = CONF.auth.admin_project_name
	
	k2k_client = k2k_token_client.K2KTokenClient(
						auth_url=idp_auth_url) 		
        idp_token, b = k2k_client.get_token(auth_data=True,
						project_name=project_name,
						password=password,
						username=username)
       	#get sp's info 
	sp_id = b['service_providers'][0]['id']
        ecp_url = str(b['service_providers'][0]['sp_url'])
        sp_auth_url = str(b['service_providers'][0]['auth_url'])
        #self.sp_ip contains the port number 5000
        sp_ip = ecp_url.split('/')[2]
        sp_projects_url = 'http://%s/v3/OS-FEDERATION/projects' % sp_ip
        sp_token_auth_url = 'http://%s/v3/auth/tokens' % sp_ip
       
	assertion = k2k_client._get_ecp_assertion(sp_id=sp_id, token=idp_token)
        unscoped_token = k2k_client.get_unscoped_token(assertion, sp_auth_url, ecp_url)  

        sp_client = k2k_token_client.K2KTokenClient(auth_url=sp_token_auth_url) 
        scoped_token, body = sp_client.get_scoped_token(unscoped_token, sp_token_auth_url,
									sp_projects_url)
	return scoped_token, body
