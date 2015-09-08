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
