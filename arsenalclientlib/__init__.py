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


def facter():
    """
    Reads in facts from facter.

    Returns:
        A dict.
    """

    # need this for custom facts - can add additional paths if needed
    os.environ["FACTERLIB"] = "/var/lib/puppet/lib/facter"
    p = subprocess.Popen( ['facter'], stdout=subprocess.PIPE )
    p.wait()
    lines = p.stdout.readlines()
    lines = dict(k.split(' => ') for k in
                   [s.strip() for s in lines if ' => ' in s])

    return lines


def get_cookie_auth():
    """
    Gets cookies from cookie file or authenticates if no cookie file
    is present

    Returns:
        A dict of all cookies.
    """

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
    """
    Reads cookies from cookie file

    Returns:
        A dict of all cookies if cookie_file is present, None otherwise.
    """

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
    """
    Writes cookies to cookie file

    Returns:
        True if successful, False otherwise.
    """

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
    """
    Prompts for user password and authenticates against the API. Writes
    response cookies to file for later use.

    Returns:
        A dict of all cookies if successful, None otherwise.
    """

    log.info('Authenticating login: %s' % (settings.user_login))
    if settings.user_login == 'kaboom':
        password = 'password'
    elif settings.user_login == 'hvm':
        password = settings.hvm_password
    else:
        password = getpass.getpass('password: ')

    try:
        payload = {'form.submitted': True,
                   'api.client': True,
                   'return_url': '/api',
                   'login': settings.user_login,
                   'password': password
        }
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
    """
    Checks the response codes and logs appropriate messaging for the client.

    Parameters:
        r (requests.response): A response object from the requests package.

    Returns:
        Json if successful, http response code otherwise.
    """

    if r.status_code == requests.codes.ok:
        log.info('Command successful.')
        return r.json()
    # FIXME: These are bogus respoonses
    elif r.status_code == requests.codes.unauthorized:
        log.info('Unauthorized.')
        return '<Response 401>'
    elif r.status_code == requests.codes.forbidden:
        log.info('Access Forbidden.')
        return '<Response 403>'
    elif r.status_code == requests.codes.not_found:
        log.info('Resource not found')
        return '<Response 404>'
    elif r.status_code == requests.codes.conflict:
        log.info('Resource already exists.')
        return '<Response 409>'
    else:
        log.info('Command failed. status_code={0}'.format(r.status_code))
        sys.exit(1)


def api_submit(request, data=None, method='get'):
    """
    Manages http requests to the API.

    Usage:

        >>> data = {'unique_id': '12345'}
        >>> api_submit('/api/nodes/1')
        <{json object}>
        >>> api_submit('/api/nodes', data, 'put')
        <{json object}>
        >>> api_submit('/api/nodes', data, 'delete')
        <{json object}>
        >>> api_submit('/api/nodes', data, 'get_params')
        <{json object}>
        >>> api_submit('/api/invalid', data, 'get_params')
        <Response 404>

    Args:
        request (str): The uri endpoint to request.
        data (dict): A dict of paramters to send with the http request.
        method (str): The http method to use. Valid choices are:
            put
            delete
            get_params
            delete

    Returns:
        check_response_codes() if 'put' or 'delete', json if sccessful
        'get', None otherwise.
    """

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


def object_search(object_type, search, exact_get = None):
    """
    Main serach function to query the API.

    Usage:

      >>> client.object_search('nodes', 'node_name=myserver,unique_id=1234', True)
      <Response [200]>
      >>> client.object_search('nodes', 'node_name=invalid', True)
      <Response [404]>

    Args:
        object_type (str): The type of object we are searching for (nodes,
            node_groups, statuses, etc.)
        search (str): The key=value search terms. Multiple values separated
            by comma (,). Multiple keys sparated by ampersand (&). If multiple
            keys are used, string must be quoted.
        exact_get (str): Whether to search for terms exactly or use wildcard
            matching.
    """

    search_terms = list(search.split("&"))
    data = dict(u.split("=") for u in search_terms)
    data['exact_get'] = exact_get

    log.debug('Searching for: {0}'.format(data))

    api_endpoint = '/api/{0}'.format(object_type)
    results = api_submit(api_endpoint, data, method='get_params')

    # FIXME: The client doesn't need metadata. or does it???
    if not results['results']:
        log.info('No results found for search.')
        return None
    else:
        r = results['results']
        return r


def get_unique_id(**facts):
    """
    Determines the unique_id of a node.
    """

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


## NODES
def register():
    """Collect all the data about a node and register
       it with the server"""

    data = collect_data()

    log.debug('data is: {0}'.format(json.dumps(data, default=lambda o: o.__dict__)))
    api_submit('/api/register', data, method='put')


def set_status(status_name, nodes):
    """Set the status of one or more nodes.

    :arg status: The name of the status you wish to set the node to.
    :arg nodes: The nodes from the search results to set the status to.

    Usage::

      >>> client.set_status('inservice', <object_search results>)
      <Response [200]>
    """

    data = {'status_name': status_name,
            'exact_get': True,
    }
    status = api_submit('/api/statuses', data, method='get_params')

    data = {'status_id': status['results'][0]['status_id']}

    for n in nodes:
        log.info('Setting status node={0},status={1}'.format(n['node_name'], status['results'][0]['status_name']))
        api_submit('/api/nodes/{0}'.format(n['node_id']), data, method='put')


def create_node(unique_id, node_name, status_id):
    """Create a new node.

    :arg unique_id: The unique_id of the node you wish to create.
    :arg node_name: The name of the node you wish to create.
    :arg status_id: The status_id of the status you wish to assign to the node.

    Usage::

      >>> client.create_node('12345', 'myserver.mycompany.com', '1')
      <Response [200]>
    """

    # FIXME: Support hardware_profile, and operating_system?
    data = {'node_name': node_name,
            'unique_id': unique_id,
            'node_status_id': status_id,
           }

    return api_submit('/api/nodes', data, method='put')


def delete_node(node_id):
    """Delete an existing node.

    :arg node_id: The node_id you wish to delete.

    Usage::

      >>> client.delete_node('1')
      <Response [200]>
    """

    data = {'node_id': node_id}
    return api_submit('/api/nodes/{0}'.format(node_id), data, method='delete')


## NODE_GROUPS
def create_node_group(node_group_name, node_group_owner, node_group_description):
    """Create a new node_group.

    :arg node_group_name: The name of the node_group you wish to create.
    :arg node_group_owner: The email address of the owner of the node group.
    :arg node_group_description: A text description of the members of this node_group.

    Usage::

      >>> client.create_node_group('my_node_group', 'email@mycompany.com', 'The nodegroup for all the magical servers')
      <Response [200]>
    """

    data = {'node_group_name': node_group_name,
            'node_group_owner': node_group_owner,
            'node_group_description': node_group_description,
           }

    log.info('Creating node_group node_group_name={0},node_group_owner={1},node_group_description={2}'.format(node_group_name, node_group_owner, node_group_description))
    return api_submit('/api/node_groups', data, method='put')


def delete_node_group(node_group_id):
    """Delete an existing node_group.

    :arg node_group_id: The id of the node_group you wish to delete.

    Usage::

      >>> client.delete_node_group('1')
      <Response [200]>
    """

    # FIXME: Support name and id or ?
    data = {'node_group_id': node_group_id}
    return api_submit('/api/node_groups/{0}'.format(node_group_id), data, method='delete')


# FIXME: Duplicate code with other manage_* functions
def manage_node_group_assignments(node_groups, nodes, api_action = 'put'):
    """Assign or De-assign node_groups to one or more nodes.

    :arg node_groups: The list of node groups to de-assign from the node.
    :arg nodes: The nodes from the search results to assign or de-assign to/from the node_group.
    :arg api_action: Whether to put or delete.

    Usage::

      >>> client.manage_node_group_assignments('node_group1,node_group2', <object_search results>, 'put')
      <Response [200]>
    """

    if api_action == 'delete':
        log_a = 'Removing'
        log_p = 'from'
    else:
        log_a = 'Assigning'
        log_p = 'to'

    node_groups_list = []
    for ng in node_groups.split(','):
        data = {'node_group_name': ng}
        r = api_submit('/api/node_groups', data, method='get_params')
        if r['results']:
            for i in r['results']:
                node_groups_list.append(i)
        else:
            log.info('Not found: node_group={0}'.format(ng))

    if node_groups_list:
        for n in nodes:
            for ng in node_groups_list:
                log.info('{0} node_group={1} {2} node={3}'.format(log_a, ng['node_group_name'], log_p, n['node_name']))
                data = {'node_id': n['node_id'],
                        'node_group_id': ng['node_group_id']}
                return api_submit('/api/node_group_assignments', data, method=api_action)


## TAGS
# FIXME: Duplicate code with other manage_* functions
def manage_tag_assignments(tags, action_object, objects, api_action = 'put'):
    """Assign or De-assign tags to one or more objects (nodes or node_groups).

    :arg tags: The list of key=value tags to assign/de-assign to/from the node or nodegroup. Multiple tags separated by comma(,).
    :arg action_object: The type of object you are tagging. Currently supported types are node and node_group.
    :arg objects: The nodes or node_groups search results to assign or de-assign the tags to/from.
    :arg api_action: Whether to put or delete.

    Usage::

      >>> client.manage_tag_assignments('mytag=value1', 'node', <object_search results>)
      <Response [200]>
      >>> client.manage_tag_assignments('mytag=value1,another_tag=value2', 'node_group', <object_search results>)
      <Response [200]>
      >>> client.manage_tag_assignments('mytag=value1', 'node', <object_search results>, 'delete')
      <Response [200]>
    """

    o_id = action_object + '_id'
    o_name = action_object + '_name'
    if api_action == 'delete':
        log_a = 'Removing'
        log_p = 'from'
    else:
        log_a = 'Assigning'
        log_p = 'to'

    # FIXME: clunky
    my_tags = []
    for t in tags.split(','):
        lst = t.split('=')
        data = {'tag_name': lst[0],
                'tag_value': lst[1],
                'exact_get': True,
        }
        r = api_submit('/api/tags', data, method='get_params')
        if r['results']:
            my_tags.append(r['results'][0])
        else:
            log.info('No existing tag found, creating...')
            r = api_submit('/api/tags', data, method='put')
            my_tags.append(r)

    for o in objects:
        for t in my_tags:
            log.info('{0} tag {1}={2} {3} {4}={5}'.format(log_a, t['tag_name'], t['tag_value'], log_p, o_name, o[o_name]))
            data = {o_id: o[o_id],
                    'tag_id': t['tag_id']}
            api_submit('/api/tag_{0}_assignments'.format(action_object), data, method=api_action)


def create_tag(tag_name, tag_value):
    """Create a new tag.

    :arg tag_name: The name of the tag you wish to create.
    :arg tag_value: The value you wish to assign to the tag_name.

    Usage::

      >>> client.create_tag('mytag', 'value1')
      <Response [200]>
    """

    data = {'tag_name': tag_name,
            'tag_value': tag_value,
           }

    log.info('Creating tag tag_name={0},tag_value={1}'.format(tag_name, tag_value))
    return api_submit('/api/tags', data, method='put')


def delete_tag(tag_id):
    """Delete an existing tag.

    :arg tag_id: The id of the tag you wish to delete.

    Usage::

      >>> client.delete_tags('1')
      <Response [200]>
    """

    data = {'tag_id': tag_id}
    return api_submit('/api/tags/{0}'.format(tag_id), data, method='delete')


## HYPERVISOR_ASSIGNMENTS
# FIXME: Duplicate code with other manage_* functions
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
        log_a = 'Removing'
        log_p = 'from'
    else:
        log_a = 'Assigning'
        log_p = 'to'

    data = {'unique_id': hypervisor,
            'exact_get': True,
    }
    r = api_submit('/api/nodes', data, method='get_params')
    if r['results']:
        hypervisor = r['results'][0]

        for n in nodes:
            log.info('{0} hypervisor={1} {2} node={3}'.format(log_a, hypervisor['node_name'], log_p, n['node_name']))
            data = {'parent_node_id': hypervisor['node_id'],
                    'child_node_id': n['node_id']}
            api_submit('/api/hypervisor_vm_assignments', data, method=api_action)
    else:
        log.info('No hypervisor found: unique_id={0}'.format(hypervisor))


## MAIN_SETTINGS
def check_root():
    """Check and see if we're running as root"""

    if not os.geteuid() == 0:
        log.error('Login {0} must run as root.'.format(settings.user_login))
        sys.exit(1)


def configSettings(conf, secret_conf = None):
    """Read in all our configuration settings from the main .ini and
       from the secrets.ini, if specified."""

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

    # Have to do this becasue it can be a boolean or a string.
    if (settings.ssl_verify == 'True' or settings.ssl_verify == 'False'):
        settings.ssl_verify = bool(settings.ssl_verify)

    return log_lines


def main(conf, secret_conf = None, args = None):
    """
    The arsenal client library.

    Usage::

      >>> import arsenalclientlib as client
      >>> client.main('/path/to/my/arsenal.ini', '/path/to/my/secret/arsenal.ini', args)
      >>> results = client.object_search('nodes', 'node_name=myserver.mycompany.com', True)
      >>> client.manage_hypervisor_assignments('00:11:22:33:44:55', results)
      <Response [200]>

    Args:
        conf (str): The path to the conf file
        secret_conf (Optional[str]): The path to the secret_conf file
        args (Optional[obj]): An object with all the optional arguments. args
            also overrides any settings in the config file if they are passed
            in as part of the args object.
    """

    log_lines = configSettings(conf, secret_conf)

    for z in [a for a in dir(args) if not a.startswith('__') and not callable(getattr(args,a))]:
        if getattr(args, z):
            log_lines.append('Assigning arg: {0}={1}'.format(z, getattr(args, z)))
            setattr(settings, z, getattr(args, z))

    # FIXME: Should we write to the log file at INFO even when console is ERROR?
    # FIXME: Should we write to a log at all for regular users? Perhaps only if they ask for it i.e another option?
    if settings.log_level:
        settings.log_level = getattr(logging, settings.log_level)
    else:
        settings.log_level = logging.INFO

    # FIXME: need better way to deal with args not being passed
    if args:
        if args.verbose:
            settings.log_level = logging.DEBUG
        elif args.quiet:
            settings.log_level = logging.ERROR

        # Set up logging to file
        if args.write_log:

            logging.basicConfig(level=settings.log_level,
                                format='%(asctime)s %(levelname)-8s- %(message)s',
                                datefmt='%Y-%m-%d %H:%M:%S',
                                filename=settings.log_file,
                                filemode='a')

    root = logging.getLogger()
    root.setLevel(settings.log_level)

    console = logging.StreamHandler(sys.stdout)
    console.setLevel(settings.log_level)
    formatter = logging.Formatter('%(levelname)-8s- %(message)s')
    console.setFormatter(formatter)
    root.addHandler(console)

    # log our overrides now that logging is configured.
    for line in log_lines:
        log.debug(line)

    # FIXME: need better way to deal with args not being passed
    if args:
       if args.write_log:
           log.info('Messages are being written to the log file : %s'
                    % settings.log_file)

    log.info('Using server: %s'
             % settings.api_host)

    if settings.user_login == 'kaboom':
        check_root()
        # FIXME: Will need os checking here
        settings.cookie_file = '/root/.arsenal_kaboom_cookie'

    if settings.user_login == 'hvm':
        check_root()
        # FIXME: Will need os checking here
        settings.cookie_file = '/root/.arsenal_hvm_cookie'
