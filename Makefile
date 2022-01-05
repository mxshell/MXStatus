REMOVE = rm -rvf
RUN = bash

all:
	docker-compose build
client:
	$(RUN) ./create-runner-script
server:
	docker-compose up --build -d
server-down:
	docker-compose down
clean:
	$(REMOVE) logs
	$(REMOVE) ./**/logs
	$(REMOVE) tmp_*.txt
	$(REMOVE) ./**/tmp_*.txt
	$(REMOVE) __pycache__
	$(REMOVE) ./**/__pycache__