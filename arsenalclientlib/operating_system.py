class OperatingSystem(object):
    def __init__(self,
                 variant = 'Unknown',
                 version_number = 'Unknown',
                 architecture = 'Unknown',
                 description = 'Unknown'):
        self.variant = variant
        self.version_number = version_number
        self.architecture = architecture
        self.description = description
