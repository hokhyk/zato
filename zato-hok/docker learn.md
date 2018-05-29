 
docker version
docker search zato
docker pull  learn/tutorial

docker images
docker ps -l

docker run learn/tutorial apt-get install -y ping

docker commit learn/ping

docker run learn/ping ping baidu

docker run zato-2.0.8 -i -l -d ......

docker push


docker compose up
