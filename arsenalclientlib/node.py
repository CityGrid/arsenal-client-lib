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
class Node(object):
    def __init__(self,
                 register = False,
                 unique_id = None,
                 node_name = None,
                 puppet_version = None,
                 facter_version = None,
                 hardware_profile = None,
                 operating_system = None,
                 uptime = None,
                 ec2 = None,
                 network = None):
        self.register = register
        self.unique_id = unique_id
        self.node_name = node_name
        self.puppet_version = puppet_version
        self.facter_version = facter_version
        self.hardware_profile = hardware_profile
        self.operating_system = operating_system
        self.uptime = uptime
        self.ec2 = ec2
        self.network = network
