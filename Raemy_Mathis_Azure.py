from azure.identity import AzureCliCredential
from azure.mgmt.resource import ResourceManagementClient
from azure.mgmt.network import NetworkManagementClient
from azure.mgmt.compute import ComputeManagementClient
import os
import paramiko

print(f"Provisioning a virtual machine in Azure using Python.")

# Acquire credential object using CLI-based authentication.
credential = AzureCliCredential()

# Retrieve subscription ID from environment variable.
subscription_id = os.environ["AZURE_SUBSCRIPTION_ID"] = "cc5bde41-bcae-493f-a03a-74c29147549d"


# 1 - create a resource group

# Get the management object for resources, this uses the credentials from the CLI login.
resource_client = ResourceManagementClient(credential, subscription_id)

# Set constants we need in multiple places.
RESOURCE_GROUP_NAME = "Lab1"
LOCATION = "switzerlandnorth"
USERNAME = "Mathis"
PASSWORD = "azureuser10!"


DATABASE_NAME = "DataBase"
DATABASE_IMAGE_REF = "/subscriptions/cc5bde41-bcae-493f-a03a-74c29147549d/resourceGroups/Lab1/providers/Microsoft.Compute/images/DataBase-image-20211014185632"
DATABASE_NETWORK_INTERFACE_REF = "/subscriptions/cc5bde41-bcae-493f-a03a-74c29147549d/resourceGroups/Lab1/providers/Microsoft.Network/networkInterfaces/database335"

BACKEND_NAME = "BackEnd"
BACKEND_IMAGE_REF = "/subscriptions/cc5bde41-bcae-493f-a03a-74c29147549d/resourceGroups/Lab1/providers/Microsoft.Compute/images/BackEnd-image-20211018090729"
BACKEND_NETWORK_INTERFACE_REF = "/subscriptions/cc5bde41-bcae-493f-a03a-74c29147549d/resourceGroups/Lab1/providers/Microsoft.Network/networkInterfaces/backend237"

FRONTEND_NAME = "FrontEnd"
FRONTEND_IMAGE_REF = "/subscriptions/cc5bde41-bcae-493f-a03a-74c29147549d/resourceGroups/Lab1/providers/Microsoft.Compute/images/FrontEnd-image-20211018091203"
FRONTEND_NETWORK_INTERFACE_REF = "/subscriptions/cc5bde41-bcae-493f-a03a-74c29147549d/resourceGroups/Lab1/providers/Microsoft.Network/networkInterfaces/frontend949"



# 6 - Create the virtual machine

# Get the management object for virtual machines
compute_client = ComputeManagementClient(credential, subscription_id)


#return private ip address of database VM
def create_database():
    poller = compute_client.virtual_machines.begin_create_or_update(RESOURCE_GROUP_NAME, DATABASE_NAME,
    {
        "location": LOCATION,
        "storage_profile": {
            "image_reference": {
                "id": DATABASE_IMAGE_REF
            }
        },
        "hardware_profile": {
            "vm_size": "Standard_DS1_v2"
        },
        "os_profile": {
            "computer_name": DATABASE_NAME,
            "admin_username": USERNAME,
            "admin_password": PASSWORD
        },
        "network_profile": {
            "network_interfaces": [{
                "id": DATABASE_NETWORK_INTERFACE_REF,
            }]
        }
    })
    vm_result = poller.result()
    
    print(f"Provisioned virtual machine {vm_result.name}")
    database_private_address = ""
    network_client = NetworkManagementClient(credential,subscription_id)
    database_net_inter_name = vm_result.network_profile.network_interfaces[0].id.split('/')[-1]
    db_interfaces = network_client.network_interfaces.get(RESOURCE_GROUP_NAME, database_net_inter_name).ip_configurations
    for i in db_interfaces:
        database_private_address = i.private_ip_address
    print(F"Private ip of database is : {database_private_address}")
    return database_private_address

def create_backend():
    poller = compute_client.virtual_machines.begin_create_or_update(RESOURCE_GROUP_NAME, BACKEND_NAME,
    {
        "location": LOCATION,
        "storage_profile": {
            "image_reference": {
                "id": BACKEND_IMAGE_REF
            }
        },
        "hardware_profile": {
            "vm_size": "Standard_DS1_v2"
        },
        "os_profile": {
            "computer_name": BACKEND_NAME,
            "admin_username": USERNAME,
            "admin_password": PASSWORD
        },
        "network_profile": {
            "network_interfaces": [{
                "id": BACKEND_NETWORK_INTERFACE_REF,
            }]
        }
    })
    vm_result = poller.result()
    print(f"Provisioned virtual machine {vm_result.name}")
    network_client = NetworkManagementClient(credential,subscription_id)
    backend_net_interface_id = vm_result.network_profile.network_interfaces[0].id
    backend_net_interface_name = backend_net_interface_id.split("/")[-1]
    backend_net_interface_component = network_client.network_interfaces.get(RESOURCE_GROUP_NAME, backend_net_interface_name).ip_configurations[0]
    backend_pub_component = backend_net_interface_component.public_ip_address
    backend_pub_name =backend_pub_component.id.split('/')[-1]
    pub_ip_addresse = network_client.public_ip_addresses.get(RESOURCE_GROUP_NAME, backend_pub_name)
    return pub_ip_addresse.ip_address

def run_backend(db_ip, backend_public_ip):
    print(F"Connecting to Backend ({backend_public_ip})...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(backend_public_ip, username=USERNAME, password=PASSWORD)
    command = './startServer.sh '+db_ip
    print(f"Running \"{command}\" on {backend_public_ip}")
    ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(command)
    print(f"Leaving {backend_public_ip}.")

def create_frontend():
    poller = compute_client.virtual_machines.begin_create_or_update(RESOURCE_GROUP_NAME, FRONTEND_NAME,
    {
        "location": LOCATION,
        "storage_profile": {
            "image_reference": {
                "id": FRONTEND_IMAGE_REF
            }
        },
        "hardware_profile": {
            "vm_size": "Standard_DS1_v2"
        },
        "os_profile": {
            "computer_name": FRONTEND_NAME,
            "admin_username": USERNAME,
            "admin_password": PASSWORD
        },
        "network_profile": {
            "network_interfaces": [{
                "id": FRONTEND_NETWORK_INTERFACE_REF,
            }]
        }
    })
    vm_result = poller.result()
    print(f"Provisioned virtual machine {vm_result.name}")
    network_client = NetworkManagementClient(credential,subscription_id)
    frontend_net_interface_id = vm_result.network_profile.network_interfaces[0].id
    frontend_net_interface_name = frontend_net_interface_id.split("/")[-1]
    frontend_net_interface_component = network_client.network_interfaces.get(RESOURCE_GROUP_NAME, frontend_net_interface_name).ip_configurations[0]
    frontend_pub_component = frontend_net_interface_component.public_ip_address
    frontend_pub_name =frontend_pub_component.id.split('/')[-1]
    pub_ip_addresse = network_client.public_ip_addresses.get(RESOURCE_GROUP_NAME, frontend_pub_name)
    return pub_ip_addresse.ip_address

def run_frontend(backend_ip, frontend_public_ip):
    print(F"Connecting to Backend ({frontend_public_ip})...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(frontend_public_ip, username=USERNAME, password=PASSWORD)
    command = './startServer.sh '+backend_ip
    print(f"Running \"{command}\" on {frontend_public_ip}")
    ssh_stdin, ssh_stdout, ssh_stderr = ssh.exec_command(command)
    print(f"Leaving {frontend_public_ip}.")


print(f"Provisioning virtual machine {DATABASE_NAME}; this operation might take a few minutes.")
db_ip = create_database()

print(f"Provisioning virtual machine {BACKEND_NAME}; this operation might take a few minutes.")
backend_pub_ip = create_backend()
run_backend(db_ip, backend_pub_ip)

print(f"Provisioning virtual machine {FRONTEND_NAME}; this operation might take a few minutes.")
frontend_ip = create_frontend()
run_frontend(backend_pub_ip, frontend_ip)
