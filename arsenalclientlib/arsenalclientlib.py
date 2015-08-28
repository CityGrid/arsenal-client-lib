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
import ConfigParser
import logging
import subprocess
import collections
import requests
import json
import getpass
import ast

log = logging.getLogger(__name__)


# requests is chatty
logging.getLogger("requests").setLevel(logging.WARNING)
# FIXME: ssl issues
requests.packages.urllib3.disable_warnings()

session = requests.session()


class Arsenal(object):
    @classmethod
    def __init__(self, conf, secret_conf = None, args = None):
        self.conf = conf
        self.secret_conf = secret_conf
        self.api_host = None
        self.api_protocol = None
        self.ca_bundle_file = None
        self.verify_ssl = None
        self.log_file = None
        self.log_level = None
        self.login = None
        self.password = None
        self.cookie_file = None
        self.read_conf(args)

    @classmethod
    def read_conf(self, args):

        conf = ConfigParser.ConfigParser()
        conf.read(self.conf)

        
        self.api_host = conf.get('api', 'host')
        self.api_protocol = conf.get('api', 'protocol')
        self.ca_bundle_file = conf.get('ssl', 'ca_bundle_file')
        self.verify_ssl = bool(conf.get('ssl', 'verify_ssl'))
        self.log_file = conf.get('log', 'file_name')
        self.log_level = getattr(logging, conf.get('log', 'log_level'))
        self.login = conf.get('user', 'login')
        self.cookie_file = conf.get('user', 'cookie_file')

        # Read values from args if present
        if args:
            for k, v in args.__dict__.items():
                if v:
                    # FIXME: Try and find a way around logger not being configured yet other than print.
                    print ('overriding conf file with arg: {0}={1}'.format(k, v))
                    setattr(self, k, v)

            # FIXME: Should we write to the log file at INFO even when console is ERROR?
            if args.verbose:
                self.log_level = logging.DEBUG
            elif args.quiet:
                self.log_level = logging.ERROR

            # Set up logging to file
            if args.write_log:

                logging.basicConfig(level=self.log_level,
                                    format='%(asctime)s %(levelname)-8s- %(message)s',
                                    datefmt='%Y-%m-%d %H:%M:%S',
                                    filename=self.log_file,
                                    filemode='a')

        root = logging.getLogger()
        root.setLevel(self.log_level)

        console = logging.StreamHandler(sys.stdout)
        console.setLevel(self.log_level)
        formatter = logging.Formatter('%(levelname)-8s- %(message)s')
        console.setFormatter(formatter)
        root.addHandler(console)

        if self.secret_conf:
            log.info('reading from secret conf: {0}'.format(self.secret_conf))
            try:
                secrets_conf = ConfigParser.ConfigParser()
                secrets_conf.read(self.secret_conf)
                # FIXME: should be in passwords section
                self.password = secrets_conf.get('password', self.login)
            except:
                log.error('Secrets file missing or malformed!')
                sys.exit(1)

        if self.login == 'kaboom':
            self.check_root(self.login)
            # The kaboom password is not securable due to developers having root
            # dev systems, so we restrict this user to only be able to register
            # a node.
            self.password = 'password'
            # FIXME: Will need os checking here
            self.cookie_file = '/root/.arsenal_kaboom_cookie'

        if self.login == 'hvm':
            self.check_root(self.login)
            # FIXME: Will need os checking here
            self.cookie_file = '/root/.arsenal_hvm_cookie'

    @classmethod
    def check_root(self, login):
        """Check and see if we're running as root"""
        if not os.geteuid() == 0:
            log.error('Login {0} must run as root.'.format(self.login))


    def get_cookie_auth(self):
        """Gets cookies from cookie file or authenticates if no cookie file
           is present"""
    
        try:
            cookies = self.read_cookie()
            if not cookies:
                cookies = self.authenticate()
            else:
                cookies = ast.literal_eval(cookies)
    
            return cookies
    
        except Exception, e:
            log.error('Failed: %s' % e)
    
    
    def read_cookie(self):
        """Reads cookies from cookie file"""
    
        log.debug('Checking for cookie file: %s' % (self.cookie_file))
        if os.path.isfile(self.cookie_file):
            log.debug('Cookie file found: %s' % (self.cookie_file))
            with open(self.cookie_file, 'r') as contents:
                cookies = contents.read()
            return cookies
        else:
            log.debug('Cookie file does not exist: %s' % (self.cookie_file))
            return None
    
    
    def write_cookie(self, cookies):
        """Writes cookies to cookie file"""
    
        log.info('Writing cookie file: %s' % (self.cookie_file))
    
        try:
            cd = dict(cookies)
            with open(self.cookie_file, "w") as cf:
                cf.write(str(cd))
            os.chmod(self.cookie_file, 0600)
    
            return True
        except Exception as e:
            log.error('Unable to write cookie: %s' % self.cookie_file)
            log.error('Exception: %s' % e)


    def authenticate(self):
        """Prompts for user password and authenticates against the API.
           Writes response cookies to file for later use."""
    
        log.info('Authenticating login: %s' % (self.login))
        if not self.password:
            password = getpass.getpass('password: ')
    
        try:
            payload = {'form.submitted': True,
                       'api.client': True,
                       'return_url': '/api',
                       'login': self.login,
                       'password': password
            }
            r = session.post(self.api_protocol
                             + '://'
                             + self.api_host
                             + '/login', data=payload)
    
            if r.status_code == requests.codes.ok:
    
                cookies = session.cookies.get_dict()
                log.debug('Cookies are: %s' %(cookies))
                try:
                    self.write_cookie(cookies)
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
    
    
    def check_response_codes(self, r):
        """Checks the response codes and logs appropriate messaging for
           the client"""
    
        if r.status_code == requests.codes.ok:
            log.info('Command successful.')
            return r.json()
        elif r.status_code == requests.codes.conflict:
            log.info('Resource already exists.')
        elif r.status_code == requests.codes.forbidden:
            log.info('Authorization failed.')
        else:
            log.info('Command failed.')
            sys.exit(1)


    def api_submit(self, request, data=None, method='get'):
        """Manages http requests to the API."""
    
        headers = {'content-type': 'application/json'}
    
        api_url = (self.api_protocol
                   + '://'
                   + self.api_host
                   + request)
    
        if method == 'put':
    
            data = json.dumps(data, default=lambda o: o.__dict__)
            cookies = self.get_cookie_auth()
    
            log.debug('Submitting data to API: %s' % api_url)
    
            r = session.put(api_url, verify=self.verify_ssl, cookies=cookies, headers=headers, data=data)
    
            # re-auth if our cookie is invalid/expired
            if r.status_code == requests.codes.unauthorized:
                cookies = self.authenticate()
                r = session.put(api_url, verify=self.verify_ssl, cookies=cookies, headers=headers, data=data)
    
            return self.check_response_codes(r)
    
        elif method == 'delete':
    
            data = json.dumps(data, default=lambda o: o.__dict__)
            cookies = self.get_cookie_auth()
    
            log.debug('Deleting data from API: %s' % api_url)
    
            r = session.delete(api_url, verify=self.verify_ssl, cookies=cookies, headers=headers, data=data)
    
            # re-auth if our cookie is invalid/expired
            if r.status_code == requests.codes.unauthorized:
                cookies = self.authenticate()
                r = session.delete(api_url, verify=self.verify_ssl, cookies=cookies)
    
            return self.check_response_codes(r)
    
        elif method == 'get_params':
            r = session.get(api_url, verify=self.verify_ssl, params=data)
            if r.status_code == requests.codes.ok:
                return r.json()
    
        else:
            r = session.get(api_url, verify=self.verify_ssl)
            if r.status_code == requests.codes.ok:
                return r.json()
    
        return None


    def object_search(self, args):
        """Main serach function to query the API."""
    
        log.debug('Searching for {0}'.format(args.object_type))
        log.debug('action_command is: {0}'.format(args.action_command))
    
        search_terms = list(args.search.split(","))
        data = dict(u.split("=") for u in search_terms)
        data['exact_get'] = args.exact_get
        log.debug('data is: {0}'.format(data))
    
        api_endpoint = '/api/{0}'.format(args.object_type)
        results = self.api_submit(api_endpoint, data, method='get_params')
    
        # The client doesn't need metadata
        if not results['results']:
            log.info('No results found for search.')
            return None
        else:
            r = results['results']
            return r
    
    def facter(self):
        """Reads in facts from facter"""
    
        # need this for custom facts - can add additional paths if needed
        os.environ["FACTERLIB"] = "/var/lib/puppet/lib/facter"
        p = subprocess.Popen( ['facter'], stdout=subprocess.PIPE )
        p.wait()
        lines = p.stdout.readlines()
        lines = dict(k.split(' => ') for k in
                       [s.strip() for s in lines if ' => ' in s])
    
        return lines
    
    
    def gen_help(self, help_type):
        """Generte the list of searchable terms for help"""
    
        terms = {
            'nodes_search': [ 'node_id', 'node_name', 'unique_id', 'status_id',
                              'status', 'hardware_profile_id', 'hardware_profile',
                              'operating_system_id', 'operating_system', 'uptime',
                              'node_groups', 'created', 'updated', 'updated_by',
            ],
            'node_groups_search': [ 'node_group_id', 'node_group_name',
                                    'node_group_owner', 'description',
            ],
            'tags_search': [ 'tag_id', 'tag_name', 'tag_value',
            ],
            'hypervisor_vm_assignments_search': [ 'parent_id', 'child_id',
            ],
        }
    
        return '[ {0} ]'.format(', '.join(sorted(terms[help_type])))
    
    
    def ask_yes_no(self, question, answer_yes=None, default='no'):
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
    
    
    def convert(self, data):
        """Helper method to format output. (might not be final solution)"""
    
        if isinstance(data, basestring):
            return str(data)
        elif isinstance(data, collections.Mapping):
            return dict(map(self.convert, data.iteritems()))
        elif isinstance(data, collections.Iterable):
            return type(data)(map(self.convert, data))
        else:
            return data
