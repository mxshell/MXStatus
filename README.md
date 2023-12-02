# WorkstationStatus

_WorkstationStatus is a comprehensive system for monitoring the status of multiple Linux workstations from a centralized server._

## System Structure

#### Client

The Client component is installed on each workstation that you want to monitor. It actively and periodically posts the host machine's status to the central server.

#### Server

The Server is deployed on a publicly accessible cloud server with a fixed IP address. It runs API endpoints to receive status updates from all clients. It also handles requests from the Web Client.

#### Web Client

The Web Client serves as the user interface to interact with the server and view the status of the monitored workstations.

## Deployment

### Deploy Server

We use Docker for easy server deployment. Follow these steps to get your server up and running:

1. Make sure you have [Docker](https://docs.docker.com/get-docker/) installed.

2. Clone this repository; Navigate to the project root directory.

3. Run the following command to deploy the server:

    ```bash
    make server-up
    ```

    Alternatively, you can use the following Docker command:

    ```bash
    docker compose up --build -d
    ```

4. To tear down the server and remove the Docker image, run:

    ```bash
    make server-down
    ```

### Install Client

To install the Client on your workstations:

1. Clone this repository to a permanent location on your workstation; Navigate to the project root directory.

2. Prepare a Python virtual environment for the Client:

    ```bash
    python3 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3. Ensure that you have modified the [config file](client/config.json) to specify the server address.
4. Dry-run the installation:

    ```bash
    ./client/installer
    ```

    Check the output of the dry-run to verify that the installation script is able to detect the correct Python virtual environment.

5. Run the actual installation:

    ```bash
    make client-up
    ```

    The installation script will create a systemd service to run the Client in the background. The service will be started automatically when the workstation boots up.

### Uninstall Client

To remove the Client from a workstation, run:

```bash
make client-down
```

## Development

This section is for developers who want to contribute to the development of WorkstationStatus.

### Setup Environment

To set up the development environment:

1. Create a virtual environment:

    ```bash
    python3 -m venv venv
    source venv/bin/activate
    ```

2. Install the required dependencies:

    ```bash
    pip install -r requirements.txt
    ```

### Run Development Server

To run the development server, use the following command from the project root directory:

```bash
uvicorn server.main:app --reload --port 5000
```

### Run Client

For testing the Client component:

1. Navigate to the 'client' directory:

    ```bash
    cd client
    ```

2. Run the Client using:

    ```bash
    python3 main.py
    ```

Feel free to explore and contribute to the development of WorkstationStatus!
