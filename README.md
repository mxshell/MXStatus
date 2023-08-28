# WorkstationStatus

Centralized Status Monitoring for Multiple Linux Workstations

## Deployment

### Deploy Server

-   Server is deployed on a public accessible server with fixed IP address.
-   Server is to receive status updates from multiple clients.
-   Server is deployed via [Docker](https://www.docker.com/)

```bash
make server-up
```

or, equivalently

```bash
docker compose up --build -d
```

To tear down the server and remove the docker image, run

```bash
make server-down
```

### Install Client

-   Client is installed on each workstation that you want to monitor.
-   Client will be installed on the system and will start running on system startup.
-   Client will in charge of reporting status updates to the server.

Note: Modify the [config file](client/config.json) to change the server address.

```bash
make client-up
```

or, dry-run the installation first by:

```bash
./client/installer
```

To remove the client from the system, run

```bash
make client-down
```

## Development

### Setup Environment

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run Development Server

```bash
# at project root directory
uvicorn server.main:app --reload
```

### Test Client

```bash
cd client
python3 main.py
```
