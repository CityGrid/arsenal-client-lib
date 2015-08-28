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
import logging
import types
import yaml
from arsenalclientlib import Arsenal
from tag import Tag

log = logging.getLogger(__name__)


class NodeGroup(Arsenal):
    def __init__(self,
                 node_group_name = None,
                 node_group_owner = None,
                 description = None):
        self.node_group_name = node_group_name
        self.node_group_owner = node_group_owner
        self.description = description


    def search_node_groups(self, args):
        """Search for node groups and perform optional assignment
           actions."""
    
        log.debug('action_command is: {0}'.format(args.action_command))
        log.debug('object_type is: {0}'.format(args.object_type))
    
        if (args.set_tags or args.del_tags):
            results = self.object_search(args)
            if results:
                r_names = []
                for ng in results:
                    r_names.append('node_group_name={0},node_group_id={1}'.format(ng['node_group_name'], ng['node_group_id']))
                if self.ask_yes_no("We are ready to update the following node_groups: \n{0}\n Continue?".format("\n".join(r_names)), args.answer_yes):
                    api_action = 'set'
                    if args.del_tags:
                        api_action = 'delete'
                    # FIXME: don't love this
                    Tag.manage_tag_assignments(args, results, 'node_group', api_action)
     
        if not any((args.set_tags, args.del_tags)):
    
            results = self.object_search(args)
    
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
    
    
    def create_node_groups(self, args):
        """Create a new node_group."""
    
        log.debug('action_command is: {0}'.format(args.action_command))
        log.debug('object_type is: {0}'.format(args.object_type))
    
        data = {'node_group_name': args.node_group_name,
                'node_group_owner': args.node_group_owner,
                'node_group_description': args.node_group_description,
               }
    
        log.info('Creating node_group node_group_name={0},node_group_owner={1},node_group_description={2}'.format(args.node_group_name, args.node_group_owner, args.node_group_description))
        self.api_submit('/api/{0}'.format(args.object_type), data, method='put')
    
    
    def delete_node_groups(self, args):
        """Delete an existing node_group."""
    
        # FIXME: Support name and id or ?
        log.debug('action_command is: {0}'.format(args.action_command))
        log.debug('object_type is: {0}'.format(args.object_type))
    
        args.search = 'node_group_name={0}'.format(args.node_group_name)
        # FIXME: do we want exact_get to be optional on delete? i.e. put it in argparse?
        args.exact_get = True
        results = self.object_search(args)
    
        if results:
            r_names = []
            for n in results:
                r_names.append(n['node_group_name'])
    
            if self.ask_yes_no("We are ready to delete the following {0}: \n{1}\n Continue?".format(args.object_type, "\n".join(r_names)), args.answer_yes):
                for n in results:
                    log.info('Deleting node_group_name={0}'.format(n['node_group_name']))
                    data = {'node_group_id': n['node_group_id']}
                    # FIXME: name? id? both?
                    self.api_submit('/api/{0}/{1}'.format(args.object_type, n['node_group_id']), data, method='delete')
