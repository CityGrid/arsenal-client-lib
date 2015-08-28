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


class Ec2(Arsenal):
    def __init__(self, 
                 ec2_instance_id = None,
                 ec2_ami_id = None,
                 ec2_hostname = None,
                 ec2_public_hostname = None,
                 ec2_instance_type = None,
                 ec2_security_groups = None,
                 ec2_placement_availability_zone = None):
        self.ec2_instance_id = ec2_instance_id
        self.ec2_ami_id = ec2_ami_id
        self.ec2_hostname = ec2_hostname
        self.ec2_public_hostname = ec2_public_hostname
        self.ec2_instance_type = ec2_instance_type
        self.ec2_security_groups = ec2_security_groups
        self.ec2_placement_availability_zone = ec2_placement_availability_zone
