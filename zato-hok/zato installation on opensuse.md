https://zato.io/docs/admin/guide/install/docker.html
Zato 2.0.8 documentation   Installation under Docker
https://en.opensuse.org/SDB:Docker#Use_Docker


ZATO  Installation steps
Quickstart cluster
Get Zato Dockerfile
host$ mkdir -p ~/zato-docker && cd ~/zato-docker && \
        wget https://zato.io/download/docker/quickstart/Dockerfile
Build Zato Docker image
host$ sudo docker build --no-cache -t zato-2.0.8 .
Retrieve your web admin password. The password will be printed out on terminal:
host$ sudo docker run zato-2.0.8 /bin/bash -c 'cat /opt/zato/web_admin_password \
        /opt/zato/zato_user_password'
Create a container in which Zato components will be launched:
host$ sudo docker run -it -p 22 -p 6379:6379 -p 8183:8183 -p 17010:17010 -p 17011:17011 \
        -p 11223:11223 zato-2.0.8
That concludes the process - a web-admin instance is running on http://localhost:8183 and you can log into it with the username 'admin' using the password printed on the terminal above.

You can also connect via SSH to the container under which Zato is running. User: zato. Password: second one of the two printed on terminal above.



https://en.opensuse.org/SDB:Docker#Use_Docker
SDB:Docker
openSUSE Support Database
Portal - SDB Categories - How to write an article

Tested on openSUSE	Recommended articles	Related articles
Icon-checked.png	
Tumbleweed
42.3
42.2
Icon-manual.png	
Docker Overview
Get Started with Docker
Docker Engine user guide
Icon-help.png	
SDB:LXC
Virtualization Guide
Contents [hide] 
1 Situation
2 Procedure
2.1 with YaST2
2.2 on the command line
2.3 Use Docker
2.4 docker and btrfs bug workaround
Situation
You want to use Docker on openSUSE.

Procedure
This article describes several solutions:

with YaST2
To install the docker and docker-compose packages start YaST2, select "Software" and start the module "Software Management". Search for docker and choose to install the Packages "docker" and "docker-compose". Then click "Accept", and if the installation was successful, "Finish".

To start the docker daemon during boot start YaST2, select "System" and start the module "Services Manager". Select the "docker" service and click "Enable/Disable" and "Start/Stop". To apply your changes click "OK".

To join the docker group that is allowed to use the docker daemon start YaST2, select "Security and Users" and start the module "User and Group Management". Select your user and click "Edit". On the "Details" tab select "docker" in the list of "Additional Groups". Then click "OK" twice.

Now you have to "Log out" of your session and "Log in" again for the changes to take effect.

on the command line
To install the docker and docker-compose packages:

zypper install docker docker-compose
To start the docker daemon during boot:

sudo systemctl enable docker
To join the docker group that is allowed to use the docker daemon:

sudo usermod -G docker -a YOURUSERNAME
where YOURUSERNAME is your user name.

Now you have to "Log out" of your session and "Log in" again for the changes to take effect.

Use Docker
If you followed the instructions your openSUSE is ready to make use of docker containers. Dive into the great docker documentation and have a lot of fun...

Warning Currently there is a bug that affects docker used in btrfs partitions. As a workaround you can create a different partition for /var/lib/docker.
docker and btrfs bug workaround
When you install docker in a machine that has /var/lib in a btrfs partition you can be hit by this bug. One way to workaround it is to create an ext4 partition and mount /var/lib/docker in that new partition. You can follow the steps below:

Uninstall docker:
zypper rm docker docker-compose
Create /var/lib/docker:
mkdir /var/lib/docker
Create a new partition, and attach it to /var/lib/docker. You can use yast2. Follow the steps described in here.
Install docker:
zypper in docker docker-compose 
