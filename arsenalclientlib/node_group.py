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
from arsenalclientlib import Arsenal

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
        """Search for node_groups."""
    
        results = self.object_search(args)

        if results:
            return results


    # FIXME: duplicated in nodes
    def manage_tag_assignments(self, args, objects, action_object, api_action = 'put'):
        """Assign or De-assign tags to one or more node_groups."""

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
            r = self.api_submit('/api/tags', data, method='get_params')
            # FIXME: need checking on unique results
            if r['results']:
                tags.append(r['results'][0])
            else:
                if http_method == 'put':
                    log.info('tag not found, creating')
                    r = self.api_submit('/api/tags', data, method='put')
                    tags.append(r)

        for o in objects:
            for t in tags:
                log.info('{0} tag {1}={2} to {3}={4}'.format(api_action, t['tag_name'], t['tag_value'], o_name, o[o_name]))
                data = {o_id: o[o_id],
                        'tag_id': t['tag_id']}
                self.api_submit('/api/tag_{0}_assignments'.format(action_object), data, method=http_method)


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
