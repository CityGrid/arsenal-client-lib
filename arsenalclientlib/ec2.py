class Ec2(object):
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
