import time
import sys
from boto.ec2 import connect_to_region

from loads.deploy.deploy import deploy


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


def aws_deploy(access_key, secret_key, ssh_user, ssh_key, image_id,
               python_deps=None, system_deps=None, test_dir=None):
    # first task: create the AWS boxes
    aws = AWSConnection(access_key, secret_key)
    nodes = aws.create_nodes(image_id, 1)
    master, master_id = nodes[0]
    ssh = {'username': ssh_user, 'key': ssh_key}
    master = {'host': master}
    slaves = []
    try:
        deploy(master, slaves, ssh, python_deps=python_deps,
               system_deps=system_deps, test_dir=test_dir)
        time.sleep(30)
    except Exception:
        aws.terminate_nodes([master_id])
        raise

    return master, master_id


def aws_shutdown(access_key, secret_key, node_id):
    aws = AWSConnection(access_key, secret_key)
    print aws.terminate_nodes([node_id])
