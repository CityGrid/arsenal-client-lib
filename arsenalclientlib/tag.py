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


class Tag(Arsenal):
    def __init__(self, 
                 tag_name = None,
                 tag_value = None):
        self.tag_name = tag_name
        self.tag_value = tag_value


    def search_tags(self, args):
        """Search for tags and perform optional assignment
           actions."""
    
        results = self.object_search(args)

        if results:
            return results
    
    
    def create_tags(self, args):
        """Create a new tag."""
    
        log.debug('action_command is: {0}'.format(args.action_command))
        log.debug('object_type is: {0}'.format(args.object_type))
    
        data = {'tag_name': args.tag_name,
                'tag_value': args.tag_value,
               }
    
        log.info('Creating tag tag_name={0},tag_value={1}'.format(args.tag_name, args.tag_value))
        self.api_submit('/api/{0}'.format(args.object_type), data, method='put')
    
    
    def delete_tags(self, args):
        """Delete an existing tag."""
    
        # FIXME: Support name and id or ?
        log.debug('action_command is: {0}'.format(args.action_command))
        log.debug('object_type is: {0}'.format(args.object_type))
    
        args.search = 'tag_name={0},tag_value={1}'.format(args.tag_name, args.tag_value)
        # FIXME: do we want exact_get to be optional on delete? i.e. put it in argparse?
        args.exact_get = True
        results = self.object_search(args)
    
        if results:
            r_names = []
            for n in results:
                r_names.append('{0}={1}'.format(n['tag_name'], n['tag_value']))
    
            if self.ask_yes_no("We are ready to delete the following {0}: \n{1}\n Continue?".format(args.object_type, "\n".join(r_names)), args.answer_yes):
                for n in results:
                    log.info('Deleting tag_name={0},tag_value={1}'.format(n['tag_name'], n['tag_value']))
                    data = {'tag_id': n['tag_id']}
                    # FIXME: name? id? both?
                    self.api_submit('/api/{0}/{1}'.format(args.object_type, n['tag_id']), data, method='delete')
