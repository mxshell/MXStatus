# WorkstationStatus

Centralized Status Monitoring for Multiple Linux Workstations

## Understand the system structure

About the **Client**

-   Client is installed on each workstation that you want to monitor.
-   Client will actively post its host machine's status to the server.

About the **Server**

-   Server is deployed on a public-accessible cloud server with a fixed IP address.
-   Server runs API endpoints to receive status updates from all clients.

About the **Web Client**

-   Web Client is the front-end to interact with the server.

## Deployment

### Deploy Server

We use [Docker](https://www.docker.com/) to deploy the server.

With the help of [make](https://www.gnu.org/software/make/manual/make.html), simply run the following command at the project root directory:

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

Client will be registered as a systemd service managed by the [systemd](https://wiki.archlinux.org/title/systemd) and will be started automatically after booting.

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
