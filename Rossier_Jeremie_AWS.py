import boto3
import time
import urllib.request
import paramiko
from botocore.exceptions import ClientError

ec2 = boto3.resource('ec2')


def make_unique_name(name):
    return f'cloud-sys-{name}-{time.time_ns()}'


def create_key_pair(key_file_name):
    key_pair = ec2.create_key_pair(KeyName=make_unique_name('key'))
    # create a file to store the key locally
    outfile = open(f"{key_file_name}", 'w')
    key_pair_out = str(key_pair.key_material)
    outfile.write(key_pair_out)
    print(f"Created a key pair {key_pair.key_name} and saved the private key to "f"{key_file_name}")
    return key_pair


def create_security_group(current_ip_address):
    global ssh_sg, web_sg, db_sg
    try:
        ssh_sg = ec2.create_security_group(GroupName=make_unique_name('ssh-group'),
                                           Description="Security group that allows SSH from "f"{current_ip_address}")
        print(f"Created security group {ssh_sg.group_id}")

        ssh_sg.authorize_ingress(
            IpPermissions=[
                {'IpProtocol': 'tcp',
                 'FromPort': 22,
                 'ToPort': 22,
                 'IpRanges': [{'CidrIp': current_ip_address + "/32"}]},
                {'IpProtocol': 'icmp',
                 'FromPort': -1,
                 'ToPort': -1,
                 'IpRanges': [{'CidrIp': '0.0.0.0/0'}]}
            ])
        print('Rules Successfully Set for security group' + ssh_sg.group_name)

        web_sg = ec2.create_security_group(GroupName=make_unique_name('web-group'),
                                           Description="Security group that allows web connexions")
        print(f"Created security group {web_sg.group_id}")

        web_sg.authorize_ingress(
            IpPermissions=[
                {'IpProtocol': 'tcp',
                 'FromPort': 80,
                 'ToPort': 80,
                 'IpRanges': [{'CidrIp': "0.0.0.0/0"}]},
                {'IpProtocol': 'tcp',
                 'FromPort': 443,
                 'ToPort': 443,
                 'IpRanges': [{'CidrIp': "0.0.0.0/0"}]},
                {'IpProtocol': 'tcp',
                 'FromPort': 8080,
                 'ToPort': 8080,
                 'IpRanges': [{'CidrIp': "0.0.0.0/0"}]}
            ])
        print('Ingress Successfully Set for security group' + web_sg.group_name)

        db_sg = ec2.create_security_group(GroupName=make_unique_name('db-group'),
                                          Description="Security group that allows connexions for the database")
        print(f"Created security group {db_sg.group_id}")

        db_sg.authorize_ingress(
            IpPermissions=[
                {'IpProtocol': 'tcp',
                 'FromPort': 3306,
                 'ToPort': 3306,
                 'IpRanges': [{'CidrIp': "0.0.0.0/0"}]}
            ])
        print('Ingress Successfully Set for security group' + db_sg.group_name)

    except ClientError as e:
        print(e)

    return ssh_sg, web_sg, db_sg


def setup_instances(ami_image_id, key_pair, security_groups):
    instance_database = ec2.create_instances(
        ImageId=ami_image_id,
        MinCount=1,
        MaxCount=1,
        InstanceType='t2.micro',
        KeyName=key_pair.key_name,
        SecurityGroupIds=[security_groups[0].group_id, security_groups[2].group_id]
    )[0]
    print(f"Created instance {instance_database}")

    instance_backend = ec2.create_instances(
        ImageId=ami_image_id,
        MinCount=1,
        MaxCount=1,
        InstanceType='t2.micro',
        KeyName=key_pair.key_name,
        SecurityGroupIds=[security_groups[0].group_id, security_groups[1].group_id]
    )[0]
    print(f"Created instance {instance_backend}")

    instance_frontend = ec2.create_instances(
        ImageId=ami_image_id,
        MinCount=1,
        MaxCount=1,
        InstanceType='t2.micro',
        KeyName=key_pair.key_name,
        SecurityGroupIds=[security_groups[0].group_id, security_groups[1].group_id]
    )[0]
    print(f"Created instance {instance_frontend}")

    print(f"Waiting for database to start...")
    instance_database.wait_until_running()
    print(f"Instance {instance_database.instance_id} is running.")

    print(f"Waiting for backend to start...")
    instance_backend.wait_until_running()
    print(f"Instance {instance_backend.instance_id} is running.")

    print(f"Waiting for frontend to start...")
    instance_frontend.wait_until_running()
    print(f"Instance {instance_frontend.instance_id} is running.")

    return instance_database, instance_backend, instance_frontend


def run_ssh(instances, key_file_name):
    key = paramiko.RSAKey.from_private_key_file(key_file_name)
    run_db_ssh(instances[0], key)
    run_back_ssh(instances[1], key, instances[0].private_ip_address)
    run_front_ssh(instances[2], key, instances[1].private_ip_address)


def run_db_ssh(instance, key):
    print("==== DATABASE SSH ====")
    db_commands = [
        "sudo yum -y update",
        "sudo yum -y install mariadb-server",
        "sudo systemctl start mariadb",
        "sudo systemctl enable mariadb",
        "sudo yum -y install git",
        "sudo mkdir /home/ec2-user/workspace",
        "sudo git clone https://github.com/CloudSys-GJ/backend.git /home/ec2-user/workspace",
        "sudo chmod 777 /etc/my.cnf",
        "sudo echo 'bind-address = 0.0.0.0' >> /etc/my.cnf",
        "sudo chmod 644 /etc/my.cnf",
        "cat /home/ec2-user/workspace/init.sql | sudo mysql -u root",
        "sudo systemctl restart mariadb"
    ]
    instance.load()
    print("Database public dns name : " + instance.public_dns_name)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    time.sleep(5)
    client.connect(hostname=instance.public_dns_name, username="ec2-user", pkey=key, allow_agent=False,
                   look_for_keys=False)
    for command in db_commands:
        print("running command: {}".format(command))
        stdin, stdout, stderr = client.exec_command(command)
        print(stdout.read())
        print(stderr.read())

    client.close()


def run_back_ssh(instance, key, db_ip):
    print("==== BACKEND SSH ====")
    back_commands = [
        "sudo yum -y update",
        "sudo wget https://repos.fedorapeople.org/repos/dchen/apache-maven/epel-apache-maven.repo -O /etc/yum.repos.d/epel-apache-maven.repo",
        "sudo sed -i s/\$releasever/6/g /etc/yum.repos.d/epel-apache-maven.repo",
        "sudo yum install -y apache-maven",
        "sudo yum -y install git",
        "mkdir /home/ec2-user/workspace",
        "sudo git clone https://github.com/CloudSys-GJ/backend.git /home/ec2-user/workspace",
        "sudo chmod 777 /etc/my.cnf",
        "sudo echo 'bind-address = 0.0.0.0' >> /etc/my.cnf",
        "sudo chmod 644 /etc/my.cnf",
        "sudo alternatives --set javac /usr/lib/jvm/java-11-amazon-corretto.x86_64/bin/javac",
        "sudo alternatives --set java /usr/lib/jvm/java-11-amazon-corretto.x86_64/bin/java",
    ]
    instance.load()
    print("Backend public dns name : " + instance.public_dns_name)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    time.sleep(5)
    client.connect(hostname=instance.public_dns_name, username="ec2-user", pkey=key, allow_agent=False,
                   look_for_keys=False)
    for command in back_commands:
        print("running command: {}".format(command))
        stdin, stdout, stderr = client.exec_command(command, timeout=40)
        print(stdout.read())
        print(stderr.read())
    stdin, stdout, stderr = client.exec_command(
        "cd /home/ec2-user/workspace; nohup sudo mvn spring-boot:run -Dspring-boot.run.arguments=--spring.datasource.url=jdbc:mysql://" + db_ip + ":3306/db_counter &")
    exit_status = stdout.channel.recv_exit_status()
    client.close()


def run_front_ssh(instance, key, backend_ip):
    print("==== FRONTEND SSH ====")
    front_commands = [
        "sudo yum -y update",
        "sudo wget -qO- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash",
        ". ~/.nvm/nvm.sh",
        "nvm install node",
        "sudo yum -y install git",
        "mkdir /home/ec2-user/workspace",
        "sudo git clone https://github.com/CloudSys-GJ/frontend.git /home/ec2-user/workspace",
        "cd /home/ec2-user/workspace;"
        "npm install -g",
        "cd /home/ec2-user/workspace;"
        "npm install express"
    ]
    instance.load()
    print("Frontend public dns name : " + instance.public_dns_name)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    time.sleep(5)
    client.connect(hostname=instance.public_dns_name, username="ec2-user", pkey=key, allow_agent=False,
                   look_for_keys=False)
    for command in front_commands:
        print("running command: {}".format(command))
        stdin, stdout, stderr = client.exec_command(command)
        print(stdout.read())
        print(stderr.read())
    stdin, stdout, stderr = client.exec_command("cd /home/ec2-user/workspace && sudo /home/ec2-user/.nvm/versions/node/v16.11.1/bin/node app.js " + backend_ip)
    exit_status = stdout.channel.recv_exit_status()
    client.close()

    print("Frontend available at " + instance.public_dns_name + ":80")


def run():
    # Get the current public IP address of this computer to allow SSH connections to created instances
    current_ip_address = urllib.request.urlopen('http://checkip.amazonaws.com').read().decode('utf-8').strip()
    print(f"Your public IP address is {current_ip_address}. This will be "
          f"used to grant SSH access to the Amazon EC2 instance created by this script.")

    ami_image_id = 'ami-02e136e904f3da870'
    key_file_name = 'cloudsys-key-file.pem'
    key_pair = create_key_pair(key_file_name)
    security_groups = create_security_group(current_ip_address)
    time.sleep(5)
    instances = setup_instances(ami_image_id, key_pair, security_groups)
    run_ssh(instances, key_file_name)
    print("END")


run()
