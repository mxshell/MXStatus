REMOVE = rm -rvf

all:
	docker compose build
client-up:
	bash ./client/installer install
client-down:
	bash ./client/installer uninstall
server-up:
	docker compose up --build -d
server-down:
	docker compose down --rmi all
clean:
	$(REMOVE) logs
	$(REMOVE) ./**/logs
	$(REMOVE) tmp_*.txt
	$(REMOVE) ./**/tmp_*.txt
	$(REMOVE) __pycache__
	$(REMOVE) ./**/__pycache__