#!/usr/bin/env python

import argparse
import os
import time

import googleapiclient.discovery
from six.moves import input


# [START list_instances]
# Allow to list all currently deployed instances in the project.
def list_instances(compute, project, zone):
    result = compute.instances().list(project=project, zone=zone).execute()
    return result['items'] if 'items' in result else None
# [END list_instances]


# [START create_rule]
# This method create a firewall rule based on the argument.
# This do not take in account IP ranges (internal or external rule), it can be use to setup port rules.
# If you want to use this method as blueprint, see the documentation here: https://cloud.google.com/compute/docs/reference/rest/v1/firewalls/insert
def create_rule(compute, project, zone, name, target_tags, ports, protocol='tcp', network='default', allow=True, direction='INGRESS'):
    network = 'projects/%s/global/networks/%s' % (project, network)
    auth = 'denied'
    if allow:
        auth = 'allowed'
    firewall_body = {
        'name': name,
        'network': network,
        'direction': direction,
        'priority': 1000,
        'targetTags': target_tags,
        auth: [
            {
                'IPProtocol': protocol,
                'ports': ports
            }
        ],
    }

    return compute.firewalls().insert(project=project, body=firewall_body).execute()
# [END create_rule]



# [START create_instance]
# This method creates an instance based on the argument of the method.
# This method only launch image (private or public) based on the "selfLink" in source_disk_image.
# tags is a list of network tags that will be applied on the VM. You can use these same tags
# within the method "create_rule"
# For the purpose of the TP, this method deploy every vm in the default network.
def create_instance(compute, project, zone, name, startup_script, source_disk_image, tags):
    # image_response = compute.images().getFromFamily(
    #    project='ubuntu-os-cloud', family='ubuntu-2004-lts').execute()
    #source_disk_image = image_response['selfLink']


    # Configure the machine
    machine_type = "zones/%s/machineTypes/e2-micro" % zone
    #startup_script = open(
    #    os.path.join(
    #        os.path.dirname(__file__), startup_script_path), 'r').read()

    config = {
        'name': name,
        'machineType': machine_type,

        'tags': {
            'items': tags
        },

        # Specify the boot disk and the image to use as a source.
        'disks': [
            {
                'boot': True,
                'autoDelete': True,
                'deviceName': name,
                'initializeParams': {
                    'siskSizeGb': 10,
                    'sourceImage': source_disk_image
                },
                'mode': 'READ_WRITE',
                'type': 'PERSISTENT',
            }
        ],

        # Specify a network interface with NAT to access the public
        # internet.
        'networkInterfaces': [{
            'network': 'global/networks/default',
            'subnet': 'default',

            'accessConfigs': [
                {'type': 'ONE_TO_ONE_NAT', 'name': 'External NAT'}
            ]
        }],

        # Metadata is readable from the instance and allows you to
        # pass configuration from deployment scripts to instances.
        'metadata': {
            'items': [{
                # Startup script is automatically executed by the
                # instance upon startup.
                'key': 'startup-script',
                'value': startup_script
            }]
        }
    }

    return compute.instances().insert(
        project=project,
        zone=zone,
        body=config).execute()
# [END create_instance]


# [START delete_instance]
# This method delete the instance based on its name given in parameter
def delete_instance(compute, project, zone, name):
    return compute.instances().delete(
        project=project,
        zone=zone,
        instance=name).execute()
# [END delete_instance]


# [START wait_for_operation]
# This method allows to wait on an deletion/insertion operation to be finished.
def wait_for_operation(compute, project, zone, operation):
    print('Waiting for operation to finish...')
    while True:
        result = compute.zoneOperations().get(
            project=project,
            zone=zone,
            operation=operation).execute()

        if result['status'] == 'DONE':
            print("done.")
            if 'error' in result:
                raise Exception(result['error'])
            return result

        time.sleep(1)
# [END wait_for_operation]

#[START create_ssh_firewall_for_db]
# Purpose: example. This method shows how to use the create_rule method.
def create_ssh_firewall_for_db(compute, project, zone):
    return create_rule(compute, project, zone, 'allow-ssh-db', ['mysql-db'], [22])
#[END create_ssh_firewall_for_db]


# [START run]


#################################################################################
#
#                       WARNING: READ CAREFULLY
#   During this TP, I decided to use the predefined firewall rules
#   of the gcloud firewall. Like so, I just add tags like "http-server" to
#   the VM that must be accessible from outside. I think there is no need 
#   of changing what already exists (and it must be compliant with google 
#   security policy). But, in the case you may think I did this only to
#   not make too much effort, I also created two methods named  "create_rule"
#   and "create_ssh_firewall_for_db" that I don't use that show
#   how to create a rule and apply it to a vm (here mysql-db). 
#
#################################################################################

# Main method of the program. This method launch 3 VMs step by step, the user must confirm for
# proceding to the other steps. When everything is deployed, if the user press "enter" it will delete all
# the created VMs.
def main(wait=True):
    compute = googleapiclient.discovery.build('compute', 'v1')

    # Defining some constants
    project = "cloudsys-2021"
    zone = "europe-west2-b"
    source_disk_image_backend = "projects/cloudsys-2021/global/images/backend-1"
    source_disk_image_db = "projects/cloudsys-2021/global/images/mysql-db"
    source_disk_image_frontend = "projects/cloudsys-2021/global/images/frontend"
    mysql_instance = "mysql-db"
    backend_instance = "backend"
    frontend_instance = "frontend"

    # Database deployement
    print('Creating mysql-db instance.')
    startup_script_db = "sudo systemctl start mysql.service"
    operation = create_instance(compute, project, zone, mysql_instance, startup_script_db, source_disk_image_db, ["mysql-db"])
    wait_for_operation(compute, project, zone, operation['name'])


    print('Getting info of the instance: mysql')
    myslq_instance_info = compute.instances().get(project=project, zone=zone, instance=mysql_instance).execute()
    mysql_db_IP = myslq_instance_info['networkInterfaces'][0]['networkIP']
    print("IP Address of MySQL DB: %s" % mysql_db_IP)

    # BACKEND deployement
    print("Press enter to deploy backend image!")
    if wait:
        input()

    print('Creating backend instance.')
    # Adding startup line in the script with the correct IP:
    startup_script_backend = 'cd /home/romain_agostinelli/backend && sudo mvn spring-boot:run -Dspring-boot.run.arguments=--spring.datasource.url=jdbc:mysql://%s:3306/db_counter' % mysql_db_IP
    operation = create_instance(compute, project, zone, backend_instance, startup_script_backend, source_disk_image_backend, ["http-server", "backend"])
    wait_for_operation(compute, project, zone, operation['name'])

    print('Getting info of the instance: backend')
    backend_instance_info = compute.instances().get(project=project, zone=zone, instance=backend_instance).execute()
    backend_public_IP = backend_instance_info['networkInterfaces'][0]['accessConfigs'][0]['natIP']
    print("IP Address of Backend: %s" % backend_public_IP)

    # FRONTEND
    print("Press enter to deploy frontend image!")
    if wait:
        input()


    startup_script_frontend = "cd /home/romain_agostinelli/frontend && sudo node app.js %s" % backend_public_IP
    operation = create_instance(compute, project, zone, frontend_instance, startup_script_frontend, source_disk_image_frontend, ["http-server", "frontend"])
    wait_for_operation(compute, project, zone, operation['name'])

    print('Getting info of the instance: Frontend')
    frontend_instance_info = compute.instances().get(project=project, zone=zone, instance=frontend_instance).execute()
    frontend_public_IP = frontend_instance_info['networkInterfaces'][0]['accessConfigs'][0]['natIP']
    print("The frontend is accessible on: http://%s" % frontend_public_IP)
    
    # Just printing all the instances in the project
    instances = list_instances(compute, project, zone)
    print('Instances in project %s and zone %s:' % (project, zone))
    for instance in instances:
        print(' - ' + instance['name'])

    # DELETION Part
    print("Press enter to delete all of the 3 instances")
    if wait:
        input()

    print("Deleting frontend...")
    operation = delete_instance(compute, project, zone, frontend_instance)
    wait_for_operation(compute, project, zone, operation['name'])
    print("Deleting backend...")
    operation = delete_instance(compute, project, zone, backend_instance)
    wait_for_operation(compute, project, zone, operation['name'])
    print("Deleting DB...")
    operation = delete_instance(compute, project, zone, mysql_instance)
    wait_for_operation(compute, project, zone, operation['name'])
    print("Everything clean! Bye!")


if __name__ == '__main__':
    main(wait=True)
# [END run]