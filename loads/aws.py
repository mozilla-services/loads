import time
import sys
from boto.ec2 import connect_to_region


class AWSConnection(object):

    def __init__(self, access_key, secret_key, region='us-west-2'):
        self.access_key = access_key
        self.secret_key = secret_key
        self.conn = connect_to_region(region,
                                      aws_access_key_id=self.access_key,
                                      aws_secret_access_key=self.secret_key)

    def create_nodes(self, image_id, count, instance_type='t1.micro',
                     security_groups=['marteau'], key_name='tarek'):

        reservation = self.conn.run_instances(image_id=image_id,
                                              instance_type=instance_type,
                                              security_groups=security_groups,
                                              key_name=key_name,
                                              min_count=count,
                                              max_count=count)

        sys.stdout.write('Creating nodes')
        for instance in reservation.instances:
            while instance.state != 'running':
                time.sleep(5)
                instance.update()
                sys.stdout.write('.')
                sys.stdout.flush()

        sys.stdout.write('\n')

        return [(instance.public_dns_name, instance.id)
                for instance in reservation.instances]

    def terminate_nodes(self, nodes):
        return self.conn.terminate_instances(nodes)
