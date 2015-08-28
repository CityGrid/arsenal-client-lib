#
#  Copyright 2015 CityGrid Media, LLC
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
import os
import subprocess
import re
import json
import yaml
import types
import logging

from arsenalclientlib import Arsenal
from hardware_profile import HardwareProfile
from operating_system import OperatingSystem
from ec2 import Ec2
from tag import Tag

log = logging.getLogger(__name__)


class Node(Arsenal):

    def __init__(self,
                 unique_id = None,
                 node_name = None,
                 puppet_version = None,
                 facter_version = None,
                 uptime = None,
                 ec2 = None,
                 network = None):
        self.unique_id = unique_id
        self.node_name = node_name
        self.puppet_version = puppet_version
        self.facter_version = facter_version
        self.hardware_profile = HardwareProfile()
        self.operating_system = OperatingSystem()
        self.uptime = uptime
        self.ec2 = ec2
        self.network = network
        self.facts = self.facter()


    def get_unique_id(self):
        """Determines the unique_id of a node"""
    
        log.debug('determining unique_id...')
        if self.facts['kernel'] == 'Linux' or self.facts['kernel'] == 'FreeBSD':
            if 'ec2_instance_id' in self.facts:
                unique_id = self.facts['ec2_instance_id']
                log.debug('unique_id is from ec2_instance_id: {0}'.format(unique_id))
            elif os.path.isfile('/usr/sbin/dmidecode'):
                unique_id = self.get_uuid()
                if unique_id:
                    log.debug('unique_id is from dmidecode: {0}'.format(unique_id))
                else:
                    unique_id = self.facts['macaddress']
                    log.debug('unique_id is from mac address: {0}'.format(unique_id))
            else:
                unique_id = self.facts['macaddress']
                log.debug('unique_id is from mac address: {0}'.format(unique_id))
        else:
            unique_id = self.facts['macaddress']
            log.debug('unique_id is from mac address: {0}'.format(unique_id))
        return unique_id
    
    
    def get_uuid(self):
        """Gets the uuid of a node from dmidecode if available."""
    
        FNULL = open(os.devnull, 'w')
        p = subprocess.Popen( ['/usr/sbin/dmidecode', '-s', 'system-uuid'], stdout=subprocess.PIPE, stderr=FNULL )
        p.wait()
        uuid = p.stdout.readlines()
        # FIXME: Need some validation here
        if uuid:
            return uuid[0].rstrip()
        else:
            # Support older versions of dmidecode
            p = subprocess.Popen( ['/usr/sbin/dmidecode', '-t', '1'], stdout=subprocess.PIPE )
            p.wait()
            dmidecode_out = p.stdout.readlines()
            xen_match = "\tUUID: "
            for line in dmidecode_out:
                if re.match(xen_match, line):
                    return line[7:].rstrip()
    
        return None
    
    
    def get_hardware_profile(self):
        """Collets hardware_profile details of a node."""
    
        log.debug('Collecting hardware profile data.')
        hardware_profile = HardwareProfile()
        try:
            hardware_profile.manufacturer = self.facts['manufacturer']
            hardware_profile.model = self.facts['productname']
            log.debug('Hardware profile from dmidecode.')
        except KeyError:
            try:
                xen_match = "xen"
                if re.match(xen_match, self.facts['virtual']) and self.facts['is_virtual'] == 'true':
                    hardware_profile.manufacturer = 'Citrix'
                    hardware_profile.model = 'Xen Guest'
                    log.debug('Hardware profile is virtual.')
            except KeyError:
                log.error('Unable to determine hardware profile.')
        return hardware_profile


    def get_operating_system(self):
        """Collets operating_system details of a node."""
    
        log.debug('Collecting operating_system data.')
        operating_system = OperatingSystem()
        try:
            operating_system.variant = self.facts['operatingsystem']
            operating_system.version_number = self.facts['operatingsystemrelease']
            operating_system.architecture = self.facts['architecture']
            operating_system.description = self.facts['lsbdistdescription']
        except KeyError:
            log.error('Unable to determine operating system.')
    
        return operating_system
    
    
    def collect_data(self):
        """Main data collection function use to register a node."""
    
        log.debug('Collecting data for node.')

        self.unique_id = self.get_unique_id()
    
        # EC2 facts
        if 'ec2_instance_id' in self.facts:
            ec2 = Ec2()
            ec2.ec2_instance_id = self.facts['ec2_instance_id']
            ec2.ec2_ami_id = self.facts['ec2_ami_id']
            ec2.ec2_hostname = self.facts['ec2_hostname']
            ec2.ec2_public_hostname = self.facts['ec2_public_hostname']
            ec2.ec2_instance_type = self.facts['ec2_instance_type']
            ec2.ec2_security_groups = self.facts['ec2_security_groups']
            ec2.ec2_placement_availability_zone = self.facts['ec2_placement_availability_zone']
            self.ec2 = ec2
    
        # puppet & facter versions
        if 'puppetversion' in self.facts:
            self.puppet_version = self.facts['puppetversion']
            self.facter_version = self.facts['facterversion']
    
        # Report uptime
        self.uptime = self.facts['uptime']
    
        self.hardware_profile = self.get_hardware_profile()
    
        self.operating_system = self.get_operating_system()
    
    #    data[operating_system[version_number]] = self.facts['lsbdistrelease']
    
        #
        # Gather software-related information
        #
        # Use our custom fact for aws. Required since hostname -f
        # doens't work on ec2 hosts.
        # FIXME: need regex match
        if 'ct_fqdn' in self.facts and self.facts['ct_loc'] == 'aws1':
           self.node_name = self.facts['ct_fqdn']
        else:
           self.node_name = self.facts['fqdn']
    

    def register(self):
        """Collect all the data about a node and register
           it with the server"""

        self.collect_data()
    
        log.debug('data is: {0}'.format(json.dumps(self, default=lambda o: o.__dict__)))
        self.api_submit('/api/register', self, method='put')


    def search_nodes(self, args):
        """Search for nodes and perform optional assignment
           actions."""
    
        log.debug('action_command is: {0}'.format(args.action_command))
        log.debug('object_type is: {0}'.format(args.object_type))
    
        # FIXME: Ths is going to get ugly real fast
#        actions = ['set_tags', 'set_status', 'set_node_groups', 'del_node_groups']
#        for a in actions:
#            foo = getattr(args, a)()
#            print "FOO IS: ", foo
#            if foo:
#               globals()[foo](args)
        # FIXME: duped code for set and del
        if args.set_tags:
            results = self.object_search(args)
            if results:
                r_names = []
                for n in results:
                    r_names.append('{0}: {1}'.format(n['node_name'], n['unique_id']))
                if self.ask_yes_no("We are ready to update the following nodes: \n{0}\n Continue?".format("\n".join(r_names)), args.answer_yes):
                    Tag.manage_tag_assignments(args, results, 'node')
        if args.del_tags:
            results = self.object_search(args)
            if results:
                r_names = []
                for n in results:
                    r_names.append('{0}: {1}'.format(n['node_name'], n['unique_id']))
                if self.ask_yes_no("We are ready to update the following nodes: \n{0}\n Continue?".format("\n".join(r_names)), args.answer_yes):
                    # FIXME: don't love this
                    Tag.manage_tag_assignments(args, results, 'node', 'delete')
        if args.set_status:
            results = self.object_search(args)
            if results:
                r_names = []
                for n in results:
                    r_names.append('{0}: {1}'.format(n['node_name'], n['unique_id']))
                if self.ask_yes_no("We are ready to update the following nodes: \n{0}\n Continue?".format("\n".join(r_names)), args.answer_yes):
                    self._set_status(args, results)
        if args.set_node_groups:
            results = self.object_search(args)
            if results:
                r_names = []
                for n in results:
                    r_names.append('{0}: {1}'.format(n['node_name'], n['unique_id']))
                if self.ask_yes_no("We are ready to update the following nodes: \n{0}\n Continue?".format("\n".join(r_names)), args.answer_yes):
                    self._manage_node_group_assignments(args, results)
        if args.del_node_groups:
            results = self.object_search(args)
            if results:
                r_names = []
                for n in results:
                    r_names.append('{0}: {1}'.format(n['node_name'], n['unique_id']))
                if self.ask_yes_no("We are ready to update the following nodes: \n{0}\n Continue?".format("\n".join(r_names)), args.answer_yes):
                    self._manage_node_group_assignments(args, results)
        if args.set_hypervisor:
            results = self.object_search(args)
            if results:
                r_names = []
                for n in results:
                    r_names.append('{0}: {1}'.format(n['node_name'], n['unique_id']))
                if self.ask_yes_no("We are ready to update the following nodes: \n{0}\n Continue?".format("\n".join(r_names)), args.answer_yes):
                    self._manage_hypervisor_assignments(args, results)
        if args.del_hypervisor:
            results = self.object_search(args)
            if results:
                r_names = []
                for n in results:
                    r_names.append('{0}: {1}'.format(n['node_name'], n['unique_id']))
                if self.ask_yes_no("We are ready to update the following nodes: \n{0}\n Continue?".format("\n".join(r_names)), args.answer_yes):
                    self._manage_hypervisor_assignments(args, results)
    
        if not any((args.set_tags,
                    args.del_tags,
                    args.set_status,
                    args.set_node_groups,
                    args.del_node_groups,
                    args.set_hypervisor,
                    args.del_hypervisor)):
    
            results = self.object_search(args)
    
            if results:
                # FIXME: Doesn't work beyond the top level for individual fields
                if args.fields:
                    for r in results:
                        print '- {0}\n'.format(r['node_name'])
#                        print res['status']['status_name']
                        if args.fields == 'all':
                            # FIXME: Is this really the best way?
                            # This produces ugly formatting
                            # print(yaml.safe_dump(r, encoding='utf-8', allow_unicode=True))
                            #print(yaml.dump(r, default_flow_style=False))
                            c = self.convert(r)
#                            f = (yaml.dump(c, default_flow_style=False, encoding='utf-8', allow_unicode=True, indent=2))
#                            print textwrap.fill(f, initial_indent='', subsequent_indent='    ')
                            print(yaml.dump(c, default_flow_style=False, encoding='utf-8', allow_unicode=True, indent=2))
    
#                            print json.dumps(r, default=lambda o: o.__dict__, sort_keys=True,
#                                             indent=2, separators=(',', ': ')).
    
                            #for f in r.keys():
                            #    if f == 'node_name':
                            #        continue
                            #    print '    {0}: {1}'.format(f, r[f])
                        else:
                            for f in list(args.fields.split(",")):
                                if f == 'node_name':
                                    continue
                                if type(r[f]) is types.ListType:
                                    print '{0}: \n{1}'.format(f, yaml.safe_dump(r[f], encoding='utf-8', allow_unicode=True))
                                else:
                                    print '    {0}: {1}'.format(f, r[f])
                # Default to returning just the node name
                else:
                    for r in results:
                        print r['node_name']


    def _set_status(self, args, nodes):
        """Set the status of one or more nodes."""
    
        log.debug('action_command is: {0}'.format(args.action_command))
        log.debug('object_type is: {0}'.format(args.object_type))
    
        data = {'status_name': args.set_status}
        status = self.api_submit('/api/statuses', data, method='get_params')
    
        data = {'status_id': status['status_id']}
    
        for n in nodes:
            log.info('Setting status node={0},status={1}'.format(n['node_name'], status['status_name']))
            self.api_submit('/api/nodes/{0}'.format(n['node_id']), data, method='put')
    
    
    def _manage_node_group_assignments(self, args, nodes):
        """Assign or De-assign node_groups to one or more nodes."""
    
        log.debug('action_command is: {0}'.format(args.action_command))
        log.debug('object_type is: {0}'.format(args.object_type))
    
        if args.del_node_groups:
            node_groups_list = args.del_node_groups
            api_action = 'delete'
            log_action = 'Deleting'
        else:
            node_groups_list = args.set_node_groups
            api_action = 'put'
            log_action = 'Assigning'
    
        node_groups = []
        for ng in node_groups_list.split(','):
            data = {'node_group_name': ng}
            r = self.api_submit('/api/node_groups', data, method='get_params')
            if r:
                node_groups.append(r[0])
    
        for n in nodes:
            for ng in node_groups:
                log.info('{0} node_group={1} to node={2}'.format(log_action, ng['node_group_name'], n['node_name']))
                data = {'node_id': n['node_id'],
                        'node_group_id': ng['node_group_id']}
                self.api_submit('/api/node_group_assignments', data, method=api_action)
    
    
    def _manage_hypervisor_assignments(self, args, nodes):
        """Assign or De-assign a hypervisor to one or more nodes."""
    
        log.debug('action_command is: {0}'.format(args.action_command))
        log.debug('object_type is: {0}'.format(args.object_type))
    
        if args.del_hypervisor:
            hypervisor = args.del_hypervisor
            api_action = 'delete'
            log_action = 'Deleting'
        else:
            hypervisor = args.set_hypervisor
            api_action = 'put'
            log_action = 'Assigning'
    
        data = {'unique_id': hypervisor}
        r = self.api_submit('/api/nodes', data, method='get_params')
        if r:
            hypervisor = r['results'][0]
    
        for n in nodes:
            log.info('{0} hypervisor={1},node={2}'.format(log_action, hypervisor['node_name'], n['node_name']))
            data = {'parent_node_id': hypervisor['node_id'],
                    'child_node_id': n['node_id']}
            self.api_submit('/api/hypervisor_vm_assignments', data, method=api_action)


    def create_node(self, args):
        """Create a new node."""
    
        # FIXME: Support hardware_profile, and operating_system?
        log.debug('action_command is: {0}'.format(args.action_command))
        log.debug('object_type is: {0}'.format(args.object_type))
    
        # Check if the node exists (by checking unique_id) first
        # so it can ask if you want to update the existing entry, which
        # essentially would just be changing either the node_name or status_id.
        # FIXME: do we want exact_get to be optional on delete? i.e. put it in argparse?
        data = { 'unique_id': args.unique_id,
                 'exact_get': True, }

        r = self.api_submit('/api/nodes', data, method='get_params')
    
        data = {'node_name': args.node_name,
                'unique_id': args.unique_id,
                'node_status_id': args.status_id,
               }
    
        if r['results']:
            if self.ask_yes_no('Entry already exists: {0}: {1}\n Would you like to update it?'.format(r['results'][0]['node_name'], r['results'][0]['unique_id']), args.answer_yes):
                log.info('Updating node node_name={0},unique_id={1},status_id={2}'.format(args.node_name, args.unique_id, args.status_id))
                self.api_submit('/api/{0}'.format(args.object_type), data, method='put')
    
        else:
            log.info('Creating node node_name={0},unique_id={1},status_id={2}'.format(args.node_name, args.unique_id, args.status_id))
            self.api_submit('/api/{0}'.format(args.object_type), data, method='put')
    
    
    def delete_nodes(self, args):
        """Delete an existing node."""
    
        log.debug('action_command is: {0}'.format(args.action_command))
        log.debug('object_type is: {0}'.format(args.object_type))
    
        if args.node_id:
            # FIXME: do we want exact_get to be optional on delete? i.e. put it in argparse?
            args.exact_get = True
            api_endpoint = '/api/nodes/{0}'.format(args.node_id)
            r = self.api_submit(api_endpoint, method='get')
            # FIXME: individual records don't return a list. Is that ok, or should the api always return a list?
            if r:
                results = [r]
            else:
                results = None
        else:
    
            search = ''
            if args.node_name:
                search = 'node_name={0},'.format(args.node_name)
            if args.unique_id:
                search = 'unique_id={0},'.format(args.unique_id)
    
            args.search = search.rstrip(',')
    
            # FIXME: do we want exact_get to be optional on delete? i.e. put it in argparse?
            args.exact_get = True
            results = self.object_search(args)
    
        if results:
            r_names = []
            for n in results:
                r_names.append('{0}: {1}'.format(n['node_name'], n['unique_id']))
    
            if self.ask_yes_no("We are ready to delete the following {0}: \n{1}\n Continue?".format(args.object_type, "\n".join(r_names)), args.answer_yes):
                for n in results:
                    log.info('Deleting node_name={0},unique_id={1}'.format(n['node_name'], n['unique_id']))
                    data = {'node_id': n['node_id']}
                    self.api_submit('/api/{0}/{1}'.format(args.object_type, n['node_id']), data, method='delete')
