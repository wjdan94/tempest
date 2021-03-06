#!/usr/bin/env python
#
# Copyright 2014 Dell Inc.
# Licensed under the Apache License, Version 2.0 (the "License"); you may
# not use this file except in compliance with the License. You may obtain
# a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
# WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.  See the
# License for the specific language governing permissions and limitations
# under the License.

"""
Utility for cleaning up environment after Tempest run

Runtime Arguments
-----------------

**--init-saved-state**: Before you can execute cleanup you must initialize
the saved state by running it with the **--init-saved-state** flag
(creating ./saved_state.json), which protects your deployment from
cleanup deleting objects you want to keep.  Typically you would run
cleanup with **--init-saved-state** prior to a tempest run. If this is not
the case saved_state.json must be edited, removing objects you want
cleanup to delete.

**--dry-run**: Creates a report (dry_run.json) of the tenants that will be
cleaned up (in the "_tenants_to_clean" array), and the global objects
that will be removed (tenants, users, flavors and images).  Once
cleanup is executed in normal mode, running it again with **--dry-run**
should yield an empty report.

**NOTE**: The _tenants_to_clean array in dry-run.json lists the
tenants that cleanup will loop through and delete child objects, not
delete the tenant itself. This may differ from the tenants array as you
can clean the tempest and alternate tempest tenants but by default,
cleanup deletes the objects in the tempest and alternate tempest tenants
but does not delete those tenants unless the **--delete-tempest-conf-objects**
flag is used to force their deletion.

**Normal mode**: running with no arguments, will query your deployment and
build a list of objects to delete after filtering out the objects found in
saved_state.json and based on the **--delete-tempest-conf-objects** flag.

By default the tempest and alternate tempest users and tenants are not
deleted and the admin user specified in tempest.conf is never deleted.

Please run with **--help** to see full list of options.
"""
import sys
import traceback

from cliff import command
from oslo_log import log as logging
from oslo_serialization import jsonutils as json

from tempest import clients
from tempest.cmd import cleanup_service
from tempest.common import credentials_factory as credentials
from tempest.common import identity
from tempest import config

SAVED_STATE_JSON = "saved_state.json"
DRY_RUN_JSON = "dry_run.json"
LOG = logging.getLogger(__name__)
CONF = config.CONF


class TempestCleanup(command.Command):

    def __init__(self, app, cmd):
        super(TempestCleanup, self).__init__(app, cmd)

    def take_action(self, parsed_args):
        try:
            self.init(parsed_args)
            if not parsed_args.init_saved_state:
                self._cleanup()
        except Exception:
            LOG.exception("Failure during cleanup")
            traceback.print_exc()
            raise
        return 0

    def init(self, parsed_args):
        cleanup_service.init_conf()
        self.options = parsed_args
        self.admin_mgr = credentials.AdminManager()
        self.dry_run_data = {}
        self.json_data = {}

        self.admin_id = ""
        self.admin_role_id = ""
        self.admin_tenant_id = ""
        self._init_admin_ids()

        self.admin_role_added = []

        # available services
        self.tenant_services = cleanup_service.get_tenant_cleanup_services()
        self.global_services = cleanup_service.get_global_cleanup_services()

        if parsed_args.init_saved_state:
            self._init_state()
            return

        self._load_json()

    def _cleanup(self):
        print ("Begin cleanup")
        is_dry_run = self.options.dry_run
        is_preserve = not self.options.delete_tempest_conf_objects
        is_save_state = False

        if is_dry_run:
            self.dry_run_data["_tenants_to_clean"] = {}

        admin_mgr = self.admin_mgr
        # Always cleanup tempest and alt tempest tenants unless
        # they are in saved state json. Therefore is_preserve is False
        kwargs = {'data': self.dry_run_data,
                  'is_dry_run': is_dry_run,
                  'saved_state_json': self.json_data,
                  'is_preserve': False,
                  'is_save_state': is_save_state}
        tenant_service = cleanup_service.TenantService(admin_mgr, **kwargs)
        tenants = tenant_service.list()
        print ("Process %s tenants" % len(tenants))

        # Loop through list of tenants and clean them up.
        for tenant in tenants:
            self._add_admin(tenant['id'])
            self._clean_tenant(tenant)

        kwargs = {'data': self.dry_run_data,
                  'is_dry_run': is_dry_run,
                  'saved_state_json': self.json_data,
                  'is_preserve': is_preserve,
                  'is_save_state': is_save_state}
        for service in self.global_services:
            svc = service(admin_mgr, **kwargs)
            svc.run()

        if is_dry_run:
            with open(DRY_RUN_JSON, 'w+') as f:
                f.write(json.dumps(self.dry_run_data, sort_keys=True,
                                   indent=2, separators=(',', ': ')))

        self._remove_admin_user_roles()

    def _remove_admin_user_roles(self):
        tenant_ids = self.admin_role_added
        LOG.debug("Removing admin user roles where needed for tenants: %s"
                  % tenant_ids)
        for tenant_id in tenant_ids:
            self._remove_admin_role(tenant_id)

    def _clean_tenant(self, tenant):
        print ("Cleaning tenant:  %s " % tenant['name'])
        is_dry_run = self.options.dry_run
        dry_run_data = self.dry_run_data
        is_preserve = not self.options.delete_tempest_conf_objects
        tenant_id = tenant['id']
        tenant_name = tenant['name']
        tenant_data = None
        if is_dry_run:
            tenant_data = dry_run_data["_tenants_to_clean"][tenant_id] = {}
            tenant_data['name'] = tenant_name

        kwargs = {"username": CONF.auth.admin_username,
                  "password": CONF.auth.admin_password,
                  "tenant_name": tenant['name']}
        mgr = clients.Manager(credentials=credentials.get_credentials(
            **kwargs))
        kwargs = {'data': tenant_data,
                  'is_dry_run': is_dry_run,
                  'saved_state_json': None,
                  'is_preserve': is_preserve,
                  'is_save_state': False,
                  'tenant_id': tenant_id}
        for service in self.tenant_services:
            svc = service(mgr, **kwargs)
            svc.run()

    def _init_admin_ids(self):
        tn_cl = self.admin_mgr.tenants_client
        rl_cl = self.admin_mgr.roles_client

        tenant = identity.get_tenant_by_name(tn_cl,
                                             CONF.auth.admin_project_name)
        self.admin_tenant_id = tenant['id']

        user = identity.get_user_by_username(tn_cl, self.admin_tenant_id,
                                             CONF.auth.admin_username)
        self.admin_id = user['id']

        roles = rl_cl.list_roles()['roles']
        for role in roles:
            if role['name'] == CONF.identity.admin_role:
                self.admin_role_id = role['id']
                break

    def get_parser(self, prog_name):
        parser = super(TempestCleanup, self).get_parser(prog_name)
        parser.add_argument('--init-saved-state', action="store_true",
                            dest='init_saved_state', default=False,
                            help="Creates JSON file: " + SAVED_STATE_JSON +
                            ", representing the current state of your "
                            "deployment,  specifically object types "
                            "tempest creates and destroys during a run. "
                            "You must run with this flag prior to "
                            "executing cleanup in normal mode, which is with "
                            "no arguments.")
        parser.add_argument('--delete-tempest-conf-objects',
                            action="store_true",
                            dest='delete_tempest_conf_objects',
                            default=False,
                            help="Force deletion of the tempest and "
                            "alternate tempest users and tenants.")
        parser.add_argument('--dry-run', action="store_true",
                            dest='dry_run', default=False,
                            help="Generate JSON file:" + DRY_RUN_JSON +
                            ", that reports the objects that would have "
                            "been deleted had a full cleanup been run.")
        return parser

    def get_description(self):
        return 'Cleanup after tempest run'

    def _add_admin(self, tenant_id):
        rl_cl = self.admin_mgr.roles_client
        needs_role = True
        roles = rl_cl.list_user_roles(tenant_id, self.admin_id)['roles']
        for role in roles:
            if role['id'] == self.admin_role_id:
                needs_role = False
                LOG.debug("User already had admin privilege for this tenant")
        if needs_role:
            LOG.debug("Adding admin privilege for : %s" % tenant_id)
            rl_cl.assign_user_role(tenant_id, self.admin_id,
                                   self.admin_role_id)
            self.admin_role_added.append(tenant_id)

    def _remove_admin_role(self, tenant_id):
        LOG.debug("Remove admin user role for tenant: %s" % tenant_id)
        # Must initialize AdminManager for each user role
        # Otherwise authentication exception is thrown, weird
        id_cl = credentials.AdminManager().identity_client
        if (self._tenant_exists(tenant_id)):
            try:
                id_cl.delete_user_role(tenant_id, self.admin_id,
                                       self.admin_role_id)
            except Exception as ex:
                LOG.exception("Failed removing role from tenant which still"
                              "exists, exception: %s" % ex)

    def _tenant_exists(self, tenant_id):
        tn_cl = self.admin_mgr.tenants_client
        try:
            t = tn_cl.show_tenant(tenant_id)
            LOG.debug("Tenant is: %s" % str(t))
            return True
        except Exception as ex:
            LOG.debug("Tenant no longer exists? %s" % ex)
            return False

    def _init_state(self):
        print ("Initializing saved state.")
        data = {}
        admin_mgr = self.admin_mgr
        kwargs = {'data': data,
                  'is_dry_run': False,
                  'saved_state_json': data,
                  'is_preserve': False,
                  'is_save_state': True}
        for service in self.global_services:
            svc = service(admin_mgr, **kwargs)
            svc.run()

        with open(SAVED_STATE_JSON, 'w+') as f:
            f.write(json.dumps(data,
                    sort_keys=True, indent=2, separators=(',', ': ')))

    def _load_json(self):
        try:
            with open(SAVED_STATE_JSON) as json_file:
                self.json_data = json.load(json_file)

        except IOError as ex:
            LOG.exception("Failed loading saved state, please be sure you"
                          " have first run cleanup with --init-saved-state "
                          "flag prior to running tempest. Exception: %s" % ex)
            sys.exit(ex)
        except Exception as ex:
            LOG.exception("Exception parsing saved state json : %s" % ex)
            sys.exit(ex)
