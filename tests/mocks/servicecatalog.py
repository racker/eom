# Copyright (c) 2013 Rackspace, Inc.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#    http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or
# implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime

from oslo_utils import timeutils


class ServiceCatalogGenerator(object):

    def __init__(self, auth_token, tenant_id):
        self.auth_token = auth_token
        self.tenant_id = tenant_id

    def token_section(self):
        # Calculate expiration timestamp 1 hour ahead
        exp_time = timeutils.utcnow() + datetime.timedelta(hours=1)
        exp_ts = timeutils.isotime(exp_time)

        return {
            'RAX-AUTH: authenticatedBy': ['TEST'],
            'expires': exp_ts,
            'id': self.auth_token,
            'tenant': {
                'id': self.tenant_id,
                'name': self.tenant_id
            }
        }

    def catalog_section(self, sec_type, sec_name, endpoints):
        return {
            'type': sec_type,
            'name': sec_name,
            'endpoints': [endpoints]
        }

    def user_section(self):
        return {
            'RAX-AUTH:defaultRegion': 'ORD',
            'id': '999999',
            'roles': [
                {
                    'description': 'RoleForMocking',
                    'id': '-1',
                    'name': 'compute:default',
                    'tenantId': self.tenant_id
                },
                {
                    'description': 'DefaultWithDiffTenant',
                    'id': '-2',
                    'name': 'compute:default',
                    'tenantId': '9999999'
                },
                {
                    'id': '3',
                    'description': 'User Admin Role.',
                    'name': 'identity:user-admin'
                }
            ],
            'name': 'mock_user'
        }

    def generate_service_catalog(self):
        service_cat = []

        # CDN
        sub = 'cdn2'
        dom = 'clouddrive.com'
        path = 'v1/mockId'
        service_cat.append(
            self.catalog_section(
                'rax: object-cdn',
                'cloudFilesCDN',
                {
                    'region': 'ORD',
                    'publicURL': 'https://' +
                                 sub +
                                 '.' +
                                 dom +
                                 '/' +
                                 path,
                    'tenantId': 'mockId'
                }
            )
        )

        # Cloud files
        sub = 'storage101.ord1'
        dom = 'clouddrive.com'
        path = 'v1/mockId'
        service_cat.append(
            self.catalog_section(
                'rax: object-store',
                'cloudFiles',
                {
                    'region': 'ORD',
                    'publicURL': 'https://' +
                                 sub +
                                 '.' +
                                 dom +
                                 '/' +
                                 path,
                    'internalURL': 'https://snet-' +
                                 sub +
                                 '.' +
                                 dom +
                                 '/' +
                                 path,
                    'tenantId': 'mockId'
                }
            )
        )

        # Cloud storage
        sub = 'ord.blockstorage.api'
        dom = 'rackspacecloud.com'
        path = 'v1/mockId'
        service_cat.append(
            self.catalog_section(
                'volume',
                'cloudBlockStorage',
                {
                    'region': 'ORD',
                    'publicURL': 'https://' +
                                 sub +
                                 '.' +
                                 dom +
                                 '/' +
                                 path,
                    'tenantId': 'mockId'
                }
            )
        )

        # Cloud load balancers
        sub = 'ord.loadbalancers.api'
        dom = 'rackspacecloud.com'
        path = 'v1.0/mockId'
        service_cat.append(
            self.catalog_section(
                'rax: load-balancer',
                'cloudLoadBalancers',
                {
                    'region': 'ORD',
                    'publicURL': 'https://' +
                                 sub +
                                 '.' +
                                 dom +
                                 '/' +
                                 path,
                    'tenantId': 'mockId'
                }
            )
        )

        # Cloud databases
        sub = 'ord.databases.api'
        dom = 'rackspacecloud.com'
        path = 'v1.0/mockId'
        service_cat.append(
            self.catalog_section(
                'rax: database',
                'cloudDatabases',
                {
                    'region': 'ORD',
                    'publicURL': 'https://' +
                                 sub +
                                 '.' +
                                 dom +
                                 '/' +
                                 path,
                    'tenantId': 'mockId'
                }
            )
        )

        # Cloud DNS
        sub = 'dns.api'
        dom = 'rackspacecloud.com'
        path = 'v1.0/mockId'
        service_cat.append(
            self.catalog_section(
                'rax: dns',
                'cloudDNS',
                {
                    'publicURL': 'https://' +
                                 sub +
                                 '.' +
                                 dom +
                                 '/' +
                                 path,
                    'tenantId': 'mockId'
                }
            )
        )

        # Cloud backup
        sub = 'ord.backup.api'
        dom = 'rackspacecloud.com'
        path = 'v1.0/mockId'
        service_cat.append(
            self.catalog_section(
                'rax: backup',
                'cloudBackup',
                {
                    'region': 'ORD',
                    'publicURL': 'https://' +
                                 sub +
                                 '.' +
                                 dom +
                                 '/' +
                                 path,
                    'tenantId': 'mockId'
                }
            )
        )

        # Cloud images
        sub = 'ord.images.api'
        dom = 'rackspacecloud.com'
        path = 'v2/mockId'
        service_cat.append(
            self.catalog_section(
                'image',
                'cloudImages',
                {
                    'region': 'ORD',
                    'publicURL': 'https://' +
                                 sub +
                                 '.' +
                                 dom +
                                 '/' +
                                 path,
                    'tenantId': 'mockId'
                }
            )
        )

        # Cloud servers OpenStack
        sub = 'ord.servers.api'
        dom = 'rackspacecloud.com'
        path = 'v2/mockId'
        service_cat.append(
            self.catalog_section(
                'compute',
                'cloudServersOpenStack',
                {
                    'region': 'ORD',
                    'versionId': '2',
                    'versionList': 'https://' +
                                   sub +
                                   '.' +
                                   dom +
                                   '/',
                    'versionInfo': 'https://' +
                                   sub +
                                   '.' +
                                   dom +
                                   '/v2',
                    'publicURL': 'https://' +
                                 sub +
                                 '.' +
                                 dom +
                                 '/' +
                                 path,
                    'tenantId': 'mockId'
                }
            )
        )

        # Cloud queues
        sub = 'ord.queues.api'
        dom = 'rackspacecloud.com'
        path = 'v1/mockId'
        service_cat.append(
            self.catalog_section(
                'rax: queues',
                'cloudQueues',
                {
                    'region': 'ORD',
                    'publicURL': 'https://' +
                                 sub +
                                 '.' +
                                 dom +
                                 '/' +
                                 path,
                    'internalURL': 'https://snet-' +
                                 sub +
                                 '.' +
                                 dom +
                                 '/' +
                                 path,
                    'tenantId': 'mockId'
                }
            )
        )

        # Cloud servers
        sub = 'servers.api'
        dom = 'rackspacecloud.com'
        path = 'v1.0/mockId'
        service_cat.append(
            self.catalog_section(
                'compute',
                'cloudServers',
                {
                    'region': 'ORD',
                    'versionId': '1.0',
                    'versionList': 'https://' +
                                   sub +
                                   '.' +
                                   dom +
                                   '/',
                    'versionInfo': 'https://' +
                                   sub +
                                   '.' +
                                   dom +
                                   '/v1.0',
                    'publicURL': 'https://' +
                                 sub +
                                 '.' +
                                 dom +
                                 '/' +
                                 path,
                    'tenantId': 'mockId'
                }
            )
        )

        # Cloud orchestration
        sub = 'ord.orchestration.api'
        dom = 'rackspacecloud.com'
        path = 'v1/mockId'
        service_cat.append(
            self.catalog_section(
                'orchestration',
                'cloudOrchestration',
                {
                    'region': 'ORD',
                    'publicURL': 'https://' +
                                 sub +
                                 '.' +
                                 dom +
                                 '/' +
                                 path,
                    'tenantId': 'mockId'
                }
            )
        )

        # Autoscale
        sub = 'ord.autoscale.api'
        dom = 'rackspacecloud.com'
        path = 'v1.0/mockId'
        service_cat.append(
            self.catalog_section(
                'rax: autoscale',
                'autoscale',
                {
                    'region': 'ORD',
                    'publicURL': 'https://' +
                                 sub +
                                 '.' +
                                 dom +
                                 '/' +
                                 path,
                    'tenantId': 'mockId'
                }
            )
        )

        # Cloud monitoring
        sub = 'monitoring.api'
        dom = 'rackspacecloud.com'
        path = 'v1.0/mockId'
        service_cat.append(
            self.catalog_section(
                'rax: monitor',
                'cloudMonitoring',
                {
                    'publicURL': 'https://' +
                                 sub +
                                 '.' +
                                 dom +
                                 '/' +
                                 path,
                    'tenantId': 'mockId'
                }
            )
        )

        return service_cat

    def generate_full_catalog(self):
        # 'version' key is included by keystone client
        return {
            'access': {
                'token': self.token_section(),
                'version': 'v2.0',
                'serviceCatalog': self.generate_service_catalog(),
                'user': self.user_section()
            }
        }
