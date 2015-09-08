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
import sys
import subprocess
import re
import ConfigParser
import logging
import json
import yaml
import collections
import types
import getpass
import ast
import requests

import arsenalclientlib.settings as settings
from arsenalclientlib.node import Node
from arsenalclientlib.hardware_profile import HardwareProfile
from arsenalclientlib.operating_system import OperatingSystem
from arsenalclientlib.ec2 import Ec2

log = logging.getLogger(__name__)

# requests is chatty
logging.getLogger("requests").setLevel(logging.WARNING)
# FIXME: ssl issues
requests.packages.urllib3.disable_warnings()
session = requests.session()

"""
The arsenal client library.

:arg conf: The path to the conf file (required)
:arg secret_conf: The path to the secret_conf file
:arg args: An object with all the optional arguments. args also
           overrides any settings in the config file if they are
           passed in as part of the args object.

Usage::

  >>>
  >>> import arsenalclientlib as client
  >>> client.main('/path/to/my/arsenal.ini', '/path/to/my/secret/arsenal.ini', args)
  >>> client.manage_hypervisor_assignments('00:11:22:33:44:55', <object_search results>, 'put')
  <Response [200]>
"""



def facter():
    """Reads in facts from facter"""

    # need this for custom facts - can add additional paths if needed
    os.environ["FACTERLIB"] = "/var/lib/puppet/lib/facter"
    p = subprocess.Popen( ['facter'], stdout=subprocess.PIPE )
    p.wait()
    lines = p.stdout.readlines()
    lines = dict(k.split(' => ') for k in
                   [s.strip() for s in lines if ' => ' in s])

    return lines


def get_cookie_auth():
    """Gets cookies from cookie file or authenticates if no cookie file
       is present"""

    try:
        cookies = read_cookie()
        if not cookies:
            cookies = authenticate()
        else:
            cookies = ast.literal_eval(cookies)

        return cookies

    except Exception, e:
        log.error('Failed: %s' % e)


def read_cookie():
    """Reads cookies from cookie file"""

    log.debug('Checking for cookie file: %s' % (settings.cookie_file))
    if os.path.isfile(settings.cookie_file):
        log.debug('Cookie file found: %s' % (settings.cookie_file))
        with open(settings.cookie_file, 'r') as contents:
            cookies = contents.read()
        return cookies
    else:
        log.debug('Cookie file does not exist: %s' % (settings.cookie_file))
        return None


def write_cookie(cookies):
    """Writes cookies to cookie file"""

    log.info('Writing cookie file: %s' % (settings.cookie_file))

    try:
        cd = dict(cookies)
        with open(settings.cookie_file, "w") as cf:
            cf.write(str(cd))
        os.chmod(settings.cookie_file, 0600)

        return True
    except Exception as e:
        log.error('Unable to write cookie: %s' % settings.cookie_file)
        log.error('Exception: %s' % e)


def authenticate():
    """Prompts for user password and authenticates against the API.
       Writes response cookies to file for later use."""

    log.info('Authenticating login: %s' % (settings.login))
    if settings.login == 'kaboom':
        password = 'password'
    elif settings.login == 'hvm':
        password = settings.hvm_password
    else:
        password = getpass.getpass('password: ')

    try:
        payload = {'form.submitted': True,
                   'api.client': True,
                   'return_url': '/api',
                   'login': settings.login,
                   'password': password
        }
        # FIXME: api_submit?
        r = session.post(settings.api_protocol
                         + '://'
                         + settings.api_host
                         + '/login', data=payload)

        if r.status_code == requests.codes.ok:

            cookies = session.cookies.get_dict()
            log.debug('Cookies are: %s' %(cookies))
            try:
                write_cookie(cookies)
                return cookies
            except Exception, e:
                log.error('Exception: %s' % e)

        else:
            log.error('Authentication failed')
            sys.exit(1)

    except Exception, e:
        log.error('Exception: %s' % e)
        log.error('Authentication failed')
        sys.exit(1)


def check_response_codes(r):
    """Checks the response codes and logs appropriate messaging for
       the client"""

    if r.status_code == requests.codes.ok:
        log.info('Command successful.')
        # FIXME: These are bogus respoonses
        return '<Response 200>'
    elif r.status_code == requests.codes.conflict:
        log.info('Resource already exists.')
        return '<Response 409>'
    elif r.status_code == requests.codes.not_found:
        log.info('Resource not found')
        return '<Response 404>'
    elif r.status_code == requests.codes.forbidden:
        log.info('Authorization failed.')
        return '<Response 404>'
    else:
        log.info('Command failed.')
        sys.exit(1)


def api_submit(request, data=None, method='get'):
    """Manages http requests to the API."""

    headers = {'content-type': 'application/json'}

    api_url = (settings.api_protocol
               + '://'
               + settings.api_host
               + request)

    if method == 'put':

        data = json.dumps(data, default=lambda o: o.__dict__)
        cookies = get_cookie_auth()

        log.debug('Submitting data to API: %s' % api_url)

        r = session.put(api_url, verify=settings.ssl_verify, cookies=cookies, headers=headers, data=data)

        # re-auth if our cookie is invalid/expired
        if r.status_code == requests.codes.unauthorized:
            cookies = authenticate()
            r = session.put(api_url, verify=settings.ssl_verify, cookies=cookies, headers=headers, data=data)

        return check_response_codes(r)

    elif method == 'delete':

        data = json.dumps(data, default=lambda o: o.__dict__)
        cookies = get_cookie_auth()

        log.debug('Deleting data from API: %s' % api_url)

        r = session.delete(api_url, verify=settings.ssl_verify, cookies=cookies, headers=headers, data=data)

        # re-auth if our cookie is invalid/expired
        if r.status_code == requests.codes.unauthorized:
            cookies = authenticate()
            r = session.delete(api_url, verify=settings.ssl_verify, cookies=cookies)

        return check_response_codes(r)

    elif method == 'get_params':
        r = session.get(api_url, verify=settings.ssl_verify, params=data)
        if r.status_code == requests.codes.ok:
            return r.json()

    else:
        r = session.get(api_url, verify=settings.ssl_verify)
        if r.status_code == requests.codes.ok:
            return r.json()

    return None


def object_search(args):
    """Main serach function to query the API."""

    log.debug('Searching for {0}'.format(args.object_type))
    log.debug('action_command is: {0}'.format(args.action_command))

    search_terms = list(args.search.split(","))
    data = dict(u.split("=") for u in search_terms)
    data['exact_get'] = args.exact_get
    log.debug('data is: {0}'.format(data))

    api_endpoint = '/api/{0}'.format(args.object_type)
    results = api_submit(api_endpoint, data, method='get_params')

    # FIXME: The client doesn't need metadata. or does it???
    if not results['results']:
        log.info('No results found for search.')
        return None
    else:
        r = results['results']
        return r


def get_unique_id(**facts):
    """Determines the unique_id of a node"""

    log.debug('determining unique_id...')
    if facts['kernel'] == 'Linux' or facts['kernel'] == 'FreeBSD':
        if 'ec2_instance_id' in facts:
            unique_id = facts['ec2_instance_id']
            log.debug('unique_id is from ec2_instance_id: {0}'.format(unique_id))
        elif os.path.isfile('/usr/sbin/dmidecode'):
            unique_id = get_uuid()
            if unique_id:
                log.debug('unique_id is from dmidecode: {0}'.format(unique_id))
            else:
                unique_id = facts['macaddress']
                log.debug('unique_id is from mac address: {0}'.format(unique_id))
        else:
            unique_id = facts['macaddress']
            log.debug('unique_id is from mac address: {0}'.format(unique_id))
    else:
        unique_id = facts['macaddress']
        log.debug('unique_id is from mac address: {0}'.format(unique_id))
    return unique_id


def get_uuid():
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


def get_hardware_profile(facts):
    """Collets hardware_profile details of a node."""

    log.debug('Collecting hardware profile data.')
    hardware_profile = HardwareProfile()
    try:
        hardware_profile.manufacturer = facts['manufacturer']
        hardware_profile.model = facts['productname']
        log.debug('Hardware profile from dmidecode.')
    except KeyError:
        try:
            xen_match = "xen"
            if re.match(xen_match, facts['virtual']) and facts['is_virtual'] == 'true':
                hardware_profile.manufacturer = 'Citrix'
                hardware_profile.model = 'Xen Guest'
                log.debug('Hardware profile is virtual.')
        except KeyError:
            log.error('Unable to determine hardware profile.')
    return hardware_profile


def get_operating_system(facts):
    """Collets operating_system details of a node."""

    log.debug('Collecting operating_system data.')
    operating_system = OperatingSystem()
    try:
        operating_system.variant = facts['operatingsystem']
        operating_system.version_number = facts['operatingsystemrelease']
        operating_system.architecture = facts['architecture']
        operating_system.description = facts['lsbdistdescription']
    except KeyError:
        log.error('Unable to determine operating system.')

    return operating_system


def collect_data():
    """Main data collection function use to register a node."""

    log.debug('Collecting data for node.')
    data = Node()
    facts = facter()
    unique_id = get_unique_id(**facts)
    data.unique_id = unique_id

    # EC2 facts
    if 'ec2_instance_id' in facts:
        ec2 = Ec2()
        ec2.ec2_instance_id = facts['ec2_instance_id']
        ec2.ec2_ami_id = facts['ec2_ami_id']
        ec2.ec2_hostname = facts['ec2_hostname']
        ec2.ec2_public_hostname = facts['ec2_public_hostname']
        ec2.ec2_instance_type = facts['ec2_instance_type']
        ec2.ec2_security_groups = facts['ec2_security_groups']
        ec2.ec2_placement_availability_zone = facts['ec2_placement_availability_zone']
        data.ec2 = ec2

    # puppet & facter versions
    if 'puppetversion' in facts:
        data.puppet_version = facts['puppetversion']
        data.facter_version = facts['facterversion']

    # Report uptime
    data.uptime = facts['uptime']

    data.hardware_profile = get_hardware_profile(facts)

    data.operating_system = get_operating_system(facts)

#    data[operating_system[version_number]] = facts['lsbdistrelease']

    #
    # Gather software-related information
    #
    # Use our custom fact for aws. Required since hostname -f
    # doens't work on ec2 hosts.
    # FIXME: need regex match
    if 'ct_fqdn' in facts and facts['ct_loc'] == 'aws1':
       data.node_name = facts['ct_fqdn']
    else:
       data.node_name = facts['fqdn']

    return data


def ask_yes_no(question, answer_yes=None, default='no'):
    """Ask a yes/no question via raw_input() and return their answer.

    "question" is a string that is presented to the user.
    "default" is the presumed answer if the user just hits <Enter>.
        It must be "yes" (the default), "no" or None (meaning
        an answer is required of the user).

    The "answer" return value is True for "yes" or False for "no".
    """

    if answer_yes:
        return True

    valid = {"yes": True, "y": True, "ye": True,
             "no": False, "n": False}
    if default is None:
        prompt = " [y/n] "
    elif default == "yes":
        prompt = " [Y/n] "
    elif default == "no":
        prompt = " [y/N] "
    else:
        raise ValueError("invalid default answer: '%s'" % default)

    while True:
        sys.stdout.write(question + prompt)
        choice = raw_input().lower()
        if default is not None and choice == '':
            return valid[default]
        elif choice in valid:
            return valid[choice]
        else:
            sys.stdout.write("Please respond with 'yes' or 'no' "
                             "(or 'y' or 'n').\n")


## NODES
def register():
        """Collect all the data about a node and register
           it with the server"""

        data = collect_data()
        data.register = True

        log.debug('data is: {0}'.format(json.dumps(data, default=lambda o: o.__dict__)))
        api_submit('/api/register', data, method='put')


def search_nodes(args):
    """Search for nodes and perform optional assignment
       actions."""

    log.debug('action_command is: {0}'.format(args.action_command))
    log.debug('object_type is: {0}'.format(args.object_type))

    return object_search(args)


def convert(data):
    """Helper method to format output. (might not be final solution)"""

    if isinstance(data, basestring):
        return str(data)
    elif isinstance(data, collections.Mapping):
        return dict(map(convert, data.iteritems()))
    elif isinstance(data, collections.Iterable):
        return type(data)(map(convert, data))
    else:
        return data


def set_status(args, nodes):
    """Set the status of one or more nodes."""

    log.debug('action_command is: {0}'.format(args.action_command))
    log.debug('object_type is: {0}'.format(args.object_type))

    data = {'status_name': args.set_status}
    status = api_submit('/api/statuses', data, method='get_params')

    data = {'status_id': status['status_id']}

    for n in nodes:
        log.info('Setting status node={0},status={1}'.format(n['node_name'], status['status_name']))
        api_submit('/api/nodes/{0}'.format(n['node_id']), data, method='put')


# FIXME: Not currently in use, are these needed? It makes it nicer on the command line for a user to type more straightforward commands like 'set' and 'delete', rahter than 'manage' with additional params.
def set_node_group_assignments(node_groups, nodes):
    """Assign or De-assign node_groups to one or more nodes.

    :arg node_groups: The list of node groups to assign to the node.
    :arg nodes: The nodes from the search results to assign to from the node_group.

    Usage::

      >>> client.set_node_group_assignments('defaul_install,node_group1', <object_search results>)
      <Response [200]>
    """

    return manage_node_group_assignments(node_groups, nodes, 'put')


# FIXME: Not currently in use, are these needed? It makes it nicer on the command line for a user to type more straightforward commands like 'set' and 'delete', rahter than 'manage' with additional params.
def del_node_group_assignments(node_groups, nodes):
    """De-assign node_groups from one or more nodes.

    :arg node_groups: The list of node groups to de-assign from the node.
    :arg nodes: The nodes from the search results to de-assign to from the node_group.

    Usage::

      >>> client.set_node_group_assignments('defaul_install,node_group1', <object_search results>)
      <Response [200]>
    """

    return manage_node_group_assignments(node_groups, nodes, 'delete')


# FIXME: Duplicate code with the next function
def manage_node_group_assignments(node_groups, nodes, api_action = 'put'):
    """Assign or De-assign node_groups to one or more nodes.

    :arg node_groups: The list of node groups to de-assign from the node.
    :arg nodes: The nodes from the search results to assign or de-assign to/from the node_group.
    :arg api_action: Whether to put or delete.

    Usage::

      >>> client.manage_node_group_assignments('defaul_install,node_group1', <object_search results>, 'put')
      <Response [200]>
    """

    if api_action == 'delete':
        log_a = 'Deleting'
        log_p = 'from'
    else:
        log_a = 'Assigning'
        log_p = 'to'

    node_groups_list = []
    for ng in node_groups.split(','):
        data = {'node_group_name': ng}
        r = api_submit('/api/node_groups', data, method='get_params')
        if r:
            node_groups_list.append(r['results'][0])

    for n in nodes:
        for ng in node_groups_list:
            log.info('{0} node_group={1} {2} node={3}'.format(log_a, ng['node_group_name'], log_p, n['node_name']))
            data = {'node_id': n['node_id'],
                    'node_group_id': ng['node_group_id']}
            return api_submit('/api/node_group_assignments', data, method=api_action)


def manage_hypervisor_assignments(hypervisor, nodes, api_action = 'put'):
    """Assign or De-assign a hypervisor to one or more nodes.

    :arg hypervisor: The unique_id of the hypervisor you wish to assign.
    :arg nodes: The nodes from the search results to assign or de-assign to/from the hypervisor.
    :arg api_action: Whether to put or delete.

    Usage::

      >>> client.manage_hypervisor_assignments('00:11:22:33:44:55', <object_search results>, 'put')
      <Response [200]>
    """

    if api_action == 'delete':
        log_a = 'Deleting'
        log_p = 'from'
    else:
        log_a = 'Assigning'
        log_p = 'to'

    data = {'unique_id': hypervisor}
    r = api_submit('/api/nodes', data, method='get_params')
    if r['results']:
        hypervisor = r['results'][0]

        for n in nodes:
            log.info('{0} hypervisor={1},node={2}'.format(log_a, hypervisor['node_name'], log_p, n['node_name']))
            data = {'parent_node_id': hypervisor['node_id'],
                    'child_node_id': n['node_id']}
            api_submit('/api/hypervisor_vm_assignments', data, method=api_action)


def create_nodes(args):
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
    r = api_submit('/api/nodes', data, method='get_params')

    data = {'register': False,
            'node_name': args.node_name,
            'unique_id': args.unique_id,
            'node_status_id': args.status_id,
           }

    if r:
        if ask_yes_no('Entry already exists: {0}: {1}\n Would you like to update it?'.format(r[0]['node_name'], r[0]['unique_id']), args.answer_yes):
            log.info('Updating node node_name={0},unique_id={1},status_id={2}'.format(args.node_name, args.unique_id, args.status_id))
            api_submit('/api/{0}'.format(args.object_type), data, method='put')

    else:
        log.info('Creating node node_name={0},unique_id={1},status_id={2}'.format(args.node_name, args.unique_id, args.status_id))
        api_submit('/api/{0}'.format(args.object_type), data, method='put')


def delete_nodes(args):
    """Delete an existing node."""

    log.debug('action_command is: {0}'.format(args.action_command))
    log.debug('object_type is: {0}'.format(args.object_type))

    if args.node_id:
        # FIXME: do we want exact_get to be optional on delete? i.e. put it in argparse?
        args.exact_get = True
        api_endpoint = '/api/nodes/{0}'.format(args.node_id)
        r = api_submit(api_endpoint, method='get')
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
        results = _search(args)

    if results:
        r_names = []
        for n in results:
            r_names.append('{0}: {1}'.format(n['node_name'], n['unique_id']))

        if ask_yes_no("We are ready to delete the following {0}: \n{1}\n Continue?".format(args.object_type, "\n".join(r_names)), args.answer_yes):
            for n in results:
                log.info('Deleting node_name={0},unique_id={1}'.format(n['node_name'], n['unique_id']))
                data = {'node_id': n['node_id']}
                api_submit('/api/{0}/{1}'.format(args.object_type, n['node_id']), data, method='delete')


## NODE_GROUPS
def search_node_groups(args):
    """Search for node groups and perform optional assignment
       actions."""

    log.debug('action_command is: {0}'.format(args.action_command))
    log.debug('object_type is: {0}'.format(args.object_type))

    if (args.set_tags or args.del_tags):
        results = _search(args)
        if results:
            r_names = []
            for ng in results:
                r_names.append('node_group_name={0},node_group_id={1}'.format(ng['node_group_name'], ng['node_group_id']))
            if ask_yes_no("We are ready to update the following node_groups: \n{0}\n Continue?".format("\n".join(r_names)), args.answer_yes):
                api_action = 'set'
                if args.del_tags:
                    api_action = 'delete'
                _manage_tag_assignments(args, results, 'node_group', api_action)

    if not any((args.set_tags, args.del_tags)):

        results = _search(args)

        if results:
            if args.fields:
                for r in results:
                    print '- {0}'.format(r['node_group_name'])
                    #FIXME: gross output, duplicate code
                    if args.fields == 'all':
                        for f in r.keys():
                            if f == 'node_group_name':
                                continue
                            if type(r[f]) is types.ListType:
                                print '{0}: \n{1}'.format(f, yaml.safe_dump(r[f], encoding='utf-8', allow_unicode=True))
                            else:
                                print '    {0}: {1}'.format(f, r[f])
                    else:
                        for f in list(args.fields.split(",")):
                            if f == 'node_group_name':
                                continue
                            if type(r[f]) is types.ListType:
                                print '{0}: \n{1}'.format(f, yaml.safe_dump(r[f], encoding='utf-8', allow_unicode=True))
                            else:
                                print '    {0}: {1}'.format(f, r[f])

            # Default to returning just the node_group name
            else:
                for r in results:
                    print r['node_group_name']


def create_node_groups(args):
    """Create a new node_group."""

    log.debug('action_command is: {0}'.format(args.action_command))
    log.debug('object_type is: {0}'.format(args.object_type))

    data = {'node_group_name': args.node_group_name,
            'node_group_owner': args.node_group_owner,
            'node_group_description': args.node_group_description,
           }

    log.info('Creating node_group node_group_name={0},node_group_owner={1},node_group_description={2}'.format(args.node_group_name, args.node_group_owner, args.node_group_description))
    api_submit('/api/{0}'.format(args.object_type), data, method='put')


def delete_node_groups(args):
    """Delete an existing node_group."""

    # FIXME: Support name and id or ?
    log.debug('action_command is: {0}'.format(args.action_command))
    log.debug('object_type is: {0}'.format(args.object_type))

    args.search = 'node_group_name={0}'.format(args.node_group_name)
    # FIXME: do we want exact_get to be optional on delete? i.e. put it in argparse?
    args.exact_get = True
    results = _search(args)

    if results:
        r_names = []
        for n in results:
            r_names.append(n['node_group_name'])

        if ask_yes_no("We are ready to delete the following {0}: \n{1}\n Continue?".format(args.object_type, "\n".join(r_names)), args.answer_yes):
            for n in results:
                log.info('Deleting node_group_name={0}'.format(n['node_group_name']))
                data = {'node_group_id': n['node_group_id']}
                # FIXME: name? id? both?
                api_submit('/api/{0}/{1}'.format(args.object_type, n['node_group_id']), data, method='delete')


## TAGS
def search_tags(args):
    """Search for tags and perform optional assignment
       actions."""

    log.debug('action_command is: {0}'.format(args.action_command))
    log.debug('object_type is: {0}'.format(args.object_type))

    if args.set_tags:
        set_tag(args)

    # switch to any if there's more than one
    if not args.set_tags:

        results = _search(args)

        if args.fields:
            for r in results:
                print '- {0}'.format(r['tag_name'])
                if args.fields == 'all':
                    for f in r.keys():
                        if f == 'tag_name':
                            continue
                        print '    {0}: {1}'.format(f, r[f])
                else:
                    for f in list(args.fields.split(",")):
                        if f == 'tag_name':
                            continue
                        print '    {0}: {1}'.format(f, r[f])
        # Default to returning just the tag name
        else:
            for r in results:
                print r['tag_name']


def manage_tag_assignments(args, objects, action_object, api_action = 'set'):
    """Assign or De-assign tags to one or more objects (nodes or node_groups)."""

    log.debug('action_command is: {0}'.format(args.action_command))
    log.debug('object_type is: {0}'.format(args.object_type))

    o_id = action_object + '_id'
    o_name = action_object + '_name'
    # FIXME: clunky
    if api_action == 'delete':
        my_tags = args.del_tags
        http_method = 'delete'
    else:
        my_tags = args.set_tags
        http_method = 'put'

    tags = []
    for t in my_tags.split(','):
        lst = t.split('=')
        data = {'tag_name': lst[0],
                'tag_value': lst[1]
        }
        r = api_submit('/api/tags', data, method='get_params')
        if r:
            tags.append(r[0])
        else:
            log.info('tag not found, creating')
            r = api_submit('/api/tags', data, method='put')
            tags.append(r)

    for o in objects:
        for t in tags:
            log.info('{0} tag {1}={2} to {3}={4}'.format(api_action, t['tag_name'], t['tag_value'], o_name, o[o_name]))
            data = {o_id: o[o_id],
                    'tag_id': t['tag_id']}
            api_submit('/api/tag_{0}_assignments'.format(action_object), data, method=http_method)


def create_tags(args):
    """Create a new tag."""

    log.debug('action_command is: {0}'.format(args.action_command))
    log.debug('object_type is: {0}'.format(args.object_type))

    data = {'tag_name': args.tag_name,
            'tag_value': args.tag_value,
           }

    log.info('Creating tag tag_name={0},tag_value={1}'.format(args.tag_name, args.tag_value))
    api_submit('/api/{0}'.format(args.object_type), data, method='put')


def delete_tags(args):
    """Delete an existing tag."""

    # FIXME: Support name and id or ?
    log.debug('action_command is: {0}'.format(args.action_command))
    log.debug('object_type is: {0}'.format(args.object_type))

    args.search = 'tag_name={0},tag_value={1}'.format(args.tag_name, args.tag_value)
    # FIXME: do we want exact_get to be optional on delete? i.e. put it in argparse?
    args.exact_get = True
    results = _search(args)

    if results:
        r_names = []
        for n in results:
            r_names.append('{0}={1}'.format(n['tag_name'], n['tag_value']))

        if ask_yes_no("We are ready to delete the following {0}: \n{1}\n Continue?".format(args.object_type, "\n".join(r_names)), args.answer_yes):
            for n in results:
                log.info('Deleting tag_name={0},tag_value={1}'.format(n['tag_name'], n['tag_value']))
                data = {'tag_id': n['tag_id']}
                # FIXME: name? id? both?
                api_submit('/api/{0}/{1}'.format(args.object_type, n['tag_id']), data, method='delete')


def check_root():
    """Check and see if we're running as root"""
    if not os.geteuid() == 0:
        log.error('Login {0} must run as root.'.format(login))
        sys.exit(1)


def configSettings(conf, secret_conf = None):

    log_lines = []
    cp = ConfigParser.ConfigParser()
    cp.read(conf)
    for s in cp._sections.keys():
        for k,v in cp.items(s):
            if v:
                log_lines.append('Assigning setting: {0}={1}'.format(k, v))
                setattr(settings, k, v)

    if secret_conf:
        scp = ConfigParser.SafeConfigParser()
        scp.read(secret_conf)
        for s in scp._sections.keys():
            for k,v in scp.items(s):
                if v:
                    log_lines.append('Assigning secret setting: {0}_password={1}'.format(k, v))
                    setattr(settings, k + '_password', v)

    return log_lines


def main(conf, secret_conf = None, args = None):

    log_lines = configSettings(conf, secret_conf)

    for z in [a for a in dir(args) if not a.startswith('__') and not callable(getattr(args,a))]:
        if getattr(args, z):
            log_lines.append('Assigning arg: {0}={1}'.format(z, getattr(args, z)))
            setattr(settings, z, getattr(args, z))

    # FIXME: Should we write to the log file at INFO even when console is ERROR?
    # FIXME: Should we write to a log at all for regular users? Perhaps only if they ask for it i.e another option?
    if args.verbose:
        log_level = logging.DEBUG
    elif args.quiet:
        log_level = logging.ERROR
    else:
        log_level = logging.INFO

    # Set up logging to file
    if args.write_log:

        logging.basicConfig(level=log_level,
                            format='%(asctime)s %(levelname)-8s- %(message)s',
                            datefmt='%Y-%m-%d %H:%M:%S',
                            filename=settings.log_file,
                            filemode='a')

    root = logging.getLogger()
    root.setLevel(log_level)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(log_level)
    formatter = logging.Formatter('%(levelname)-8s- %(message)s')
    console.setFormatter(formatter)
    root.addHandler(console)

    # log our overrides now that logging is configured.
    for line in log_lines:
        log.info(line)

    if args.write_log:
        log.info('Messages are being written to the log file : %s'
                 % settings.log_file)
    log.info('Using server: %s'
             % settings.api_host)

    if settings.login == 'kaboom':
        check_root()
        # FIXME: Will need os checking here
        settings.cookie_file = '/root/.arsenal_kaboom_cookie'

    if settings.login == 'hvm':
        check_root()
        # FIXME: Will need os checking here
        settings.cookie_file = '/root/.arsenal_hvm_cookie'
