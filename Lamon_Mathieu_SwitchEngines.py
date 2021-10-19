# -*- coding: utf-8 -*-
""" Ce script permet de déployer automatiquement notre application 3-tiers sur 3 instances sur SWITCHEngines.
    
    Il faut faire attention aux clés privées et publiques. Il faut adapter la méthode create_client_ssh() pour qu'elle prenne
    la bonne clé (créé à la main, la seule partie non automatisée) ainsi que de mettre le bon nom de keypair lors de la création des instances.
"""

import openstack
import paramiko
import time

__author__ = "Mathieu Lamon"
__date__ = "18.10.2021"
__deprecated__ = False
__email__ = "mathieu.lamon@hes-so.ch"
__maintainer__ = "Mathieu Lamon"
__status__ = "Production"
__version__ = "1.0.0"

##################################################################################################
########################################## CREATE TOOLS ##########################################
################################################################################################## 

def get_or_create_keypairs(conn, keypairs_name):
    keypairs = conn.compute.find_keypair(keypairs_name)

    if not keypairs:
        print("Creating keypairs...")

        keypairs = conn.compute.create_keypair(name=keypairs_name)

        print("Keypairs created.")

    return keypairs

def create_floating_ips(conn):    
    network = conn.network.find_network('public')
    
    ip_database = conn.network.create_ip(floating_network_id=network.id)
    print("Floating ip created for database.")
    
    ip_backend = conn.network.create_ip(floating_network_id=network.id)
    print("Floating ip created for backend.")
    
    ip_frontend = conn.network.create_ip(floating_network_id=network.id)
    print("Floating ip created for frontend.")
    
    return (ip_database, ip_backend, ip_frontend)

def create_security_groups(conn):
    security_group_database = conn.network.create_security_group(name="security_database", description="Security group for database")
    conn.network.create_security_group_rule(direction="ingress", protocol="tcp", port_range_max=22, port_range_min=22, security_group_id=security_group_database.id)
    conn.network.create_security_group_rule(direction="ingress", protocol="tcp", port_range_max=3306, port_range_min=3306, security_group_id=security_group_database.id)
    print("Security group created for database.")
    
    security_group_backend = conn.network.create_security_group(name="security_backend", description="Security group for backend")
    conn.network.create_security_group_rule(direction="ingress", protocol="tcp", port_range_max=22, port_range_min=22, security_group_id=security_group_backend.id)
    conn.network.create_security_group_rule(direction="ingress", protocol="tcp", port_range_max=80, port_range_min=80, security_group_id=security_group_backend.id)
    print("Security group created for backend.")
    
    security_group_frontend = conn.network.create_security_group(name="security_frontend", description="Security group for frontend")
    conn.network.create_security_group_rule(direction="ingress", protocol="tcp", port_range_max=22, port_range_min=22, security_group_id=security_group_frontend.id)
    conn.network.create_security_group_rule(direction="ingress", protocol="tcp", port_range_max=80, port_range_min=80, security_group_id=security_group_frontend.id)
    print("Security group created for frontend.")
    
    return (security_group_database, security_group_backend, security_group_frontend)

##################################################################################################
######################################## CREATE INSTANCES ########################################
##################################################################################################

def create_client_ssh(ip, username):
    client = paramiko.SSHClient()
    key = paramiko.RSAKey.from_private_key_file('/mnt/c/Users/mathi/.ssh/id_rsa_cloudSys_labo1')
    client.load_system_host_keys()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    
    connected = False
    
    while(not connected):
        try:
            client.connect(hostname=ip, username=username, pkey=key)
            connected = True
            print("Connection established with ip : %s" % ip)
        except:
            # Wait 5 seconds until next try
            time.sleep(5)
    return client

def create_instance(conn, name):
    # Get some values
    image = conn.compute.find_image('Ubuntu Focal 20.04 (SWITCHengines)')
    flavor = conn.compute.find_flavor('m1.small')
    network = conn.network.find_network('private')
    
    # Get keypair
    keypair = get_or_create_keypairs(conn, 'labo1')
    
    # Create server
    server = conn.compute.create_server(
        name=name, image_id=image.id, flavor_id=flavor.id,
        networks=[{"uuid": network.id}], key_name=keypair.name)
    
    server = conn.compute.wait_for_server(server, status='ACTIVE')
    
    return server

def configure_tools(conn, server, ip, security_group):
    # Set floating ip (for ssh configurations)
    conn.compute.add_floating_ip_to_server(server, ip, fixed_address=None)
    
    # Set security_group
    conn.compute.add_security_group_to_server(server, security_group)
    
    # Remove default group
    default_group = conn.network.find_security_group('default')
    conn.compute.remove_security_group_from_server(server, default_group)

def create_database(conn, ip, security_group, floating_ip):
    # Create server
    print("Build database instance...")
    server = create_instance(conn, 'Database')
    print("Database instance created.")
    
    # Configure tools
    print("Configure database tools...")
    configure_tools(conn, server, ip, security_group)
    print("Database tools configured.")
    
    # Configurations with SSH
    print("Establishing SSH connection for database...")
    
    # Create ssh client
    client = create_client_ssh(ip, 'ubuntu')
    print("Start SSH configurations for database :")
    
    print("apt update...")
    stdin, stdout, stderr = client.exec_command('sudo -S apt update')
    exit_status = stdout.channel.recv_exit_status()
    
    print("Install mysql-server...")
    stdin, stdout, stderr = client.exec_command('sudo -S apt install --assume-yes mysql-server')
    exit_status = stdout.channel.recv_exit_status()
    
    print("Clone repository...")
    stdin, stdout, stderr = client.exec_command('git clone https://github.com/CloudSys-GJ/backend.git')
    exit_status = stdout.channel.recv_exit_status()
    
    print("Update rights on the script...")
    stdin, stdout, stderr = client.exec_command('chmod 777 backend/db-init.sh')
    exit_status = stdout.channel.recv_exit_status()
    
    print("Init databse...")
    stdin, stdout, stderr = client.exec_command('sudo -S ./backend/db-init.sh')
    exit_status = stdout.channel.recv_exit_status()
    
    print("Create mysql database...")
    stdin, stdout, stderr = client.exec_command('sudo -S mysql < backend/init.sql')
    exit_status = stdout.channel.recv_exit_status()
    
    print("Restart mysql service...")
    stdin, stdout, stderr = client.exec_command('sudo -S service mysql restart')
    exit_status = stdout.channel.recv_exit_status()
    
    client.close()
    print("Connection closed.")
    
    # Remove floating ip
    print("Remove floating ip")
    conn.compute.remove_floating_ip_from_server(server, ip)
    
    # Delete floating ip
    print("Delete floating ip")
    conn.network.delete_ip(floating_ip)
    
    # Get database ip
    db_ip = server.addresses.get('private')[0].get('addr')
    
    print("Configurations done for database.")
    
    return db_ip

def create_backend(conn, ip, security_group, db_ip):
    # Create server
    print("Build backend instance...")
    server = create_instance(conn, 'Backend')
    print("Backend instance created.")
    
    # Configure tools
    print("Configure backend tools...")
    configure_tools(conn, server, ip, security_group)
    print("Backend tools configured.")
    
    # Configurations with SSH
    print("Establishing SSH connection for backend...")
    
    # Create ssh client
    client = create_client_ssh(ip, 'ubuntu')
    print("Start SSH configurations for backend :")
    
    print("apt update...")
    stdin, stdout, stderr = client.exec_command('sudo -S apt update')
    exit_status = stdout.channel.recv_exit_status()
    
    print("Install default-jdk...")
    stdin, stdout, stderr = client.exec_command('sudo -S apt install --assume-yes default-jdk')
    exit_status = stdout.channel.recv_exit_status()
    
    print("Install maven...")
    stdin, stdout, stderr = client.exec_command('sudo -S apt install --assume-yes maven')
    exit_status = stdout.channel.recv_exit_status()
    
    print("Clone repository...")
    stdin, stdout, stderr = client.exec_command('git clone https://github.com/CloudSys-GJ/backend.git')
    exit_status = stdout.channel.recv_exit_status()
    
    print("Run backend application...")
    stdin, stdout, stderr = client.exec_command('cd backend && nohup sudo -S mvn spring-boot:run -Dspring-boot.run.arguments=--spring.datasource.url=jdbc:mysql://' + db_ip + ':3306/db_counter &')
    exit_status = stdout.channel.recv_exit_status()
    
    client.close()
    print("Connection closed.")
    
    print("Configurations done for backend.")
    print("Backend ip : %s" % ip)

def create_frontend(conn, ip, security_group, backend_ip):
    # Create server
    print("Build frontend instance...")
    server = create_instance(conn, 'Frontend')
    print("Frontend instance created.")
    
    # Configure tools
    print("Configure frontend tools...")
    configure_tools(conn, server, ip, security_group)
    print("Backend tools configured.")
    
    # Configurations with SSH
    print("Establishing SSH connection for frontend...")
    
    # Create ssh client
    client = create_client_ssh(ip, 'ubuntu')
    print("Start SSH configurations for frontend :")
    
    print("apt update...")
    stdin, stdout, stderr = client.exec_command('sudo -S apt update')
    exit_status = stdout.channel.recv_exit_status()
    
    print("Install npm...")
    stdin, stdout, stderr = client.exec_command('sudo -S apt install --assume-yes npm')
    exit_status = stdout.channel.recv_exit_status()
    
    print("Install nodejs...")
    stdin, stdout, stderr = client.exec_command('sudo -S apt install --assume-yes nodejs')
    exit_status = stdout.channel.recv_exit_status()
    
    print("Clone repository...")
    stdin, stdout, stderr = client.exec_command('git clone https://github.com/CloudSys-GJ/frontend.git')
    exit_status = stdout.channel.recv_exit_status()
    
    print("Install npm dependencies...")
    stdin, stdout, stderr = client.exec_command('cd frontend && sudo -S npm install')
    exit_status = stdout.channel.recv_exit_status()
    
    print("Run frontend application...")
    stdin, stdout, stderr = client.exec_command('cd frontend && sudo -S node app.js ' + backend_ip + ' &')
    exit_status = stdout.channel.recv_exit_status()
    
    client.close()
    print("Connection closed.")
    
    print("Configurations done for frontend.")
    print("Frontend ip : %s" % ip)

##################################################################################################
########################################## MAIN PROGRAM ##########################################
##################################################################################################

if __name__ == '__main__':
    print("===== Start of the deployment of the application =====")
    print("======================================================")
    
    # Initialize connection with openstack
    print("Initialize connection with openstack...")
    conn = openstack.connection.from_config(cloud='openstack')
    print("Connection initialized.")
    
    # Create three floating ips (database ip will be deleted after ssh configurations)
    print("=========== STEP 1 : Creating floating ips ===========")
    ip_database, ip_backend, ip_frontend = create_floating_ips(conn)
    print("=================== End of STEP 1 ====================")
    
    # Create security group
    print("========== STEP 2 : Creating security groups =========")
    security_group_database, security_group_backend, security_group_frontend = create_security_groups(conn)
    print("=================== End of STEP 2 ====================")
    
    # Create database
    print("========= STEP 3 : Creating databse instance =========")
    db_ip = create_database(conn, ip_database.floating_ip_address, security_group_database, ip_database)
    print("=================== End of STEP 3 ====================")
    
    # Create backend
    print("========= STEP 4 : Creating backend instance =========")
    create_backend(conn, ip_backend.floating_ip_address, security_group_backend, db_ip)
    print("=================== End of STEP 4 ====================")
    
    # Create frontend
    print("========= STEP 5 : Creating frontend instance ========")
    create_frontend(conn, ip_frontend.floating_ip_address, security_group_frontend, ip_backend.floating_ip_address)
    print("=================== End of STEP 5 ====================")