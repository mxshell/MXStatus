# WorkstationStatus

Centralized Status Monitoring for Multiple Linux Workstations

## Deploy Server

-   Server is deployed on a public accessible server with fixed IP address.
-   Server is to receive status updates from multiple clients.
-   Server is deployed via [Docker](https://www.docker.com/) and [Docker Compose](https://docs.docker.com/compose/overview/).

```bash
make server
```

## Install Client

-   Client is installed on each workstation that you want to monitor.
-   Client will be installed on the system and will start running on system startup.
-   Client will in charge of sending status updates to the server.

Step 0: Modify the [create-runner-script](create-runner-script) file to include the IP address of the server.

```bash
nano create-runner-script
```

Step 1: Create a runner script

```bash
make client
```

Step 2: Setup a Cron job to run the runner script on system startup

-   Edit Cron job file

    ```bash
    sudo crontab -e
    ```

-   Add the following line to the end of the file:

    ```bash
    @reboot /bin/run_system_status_client &
    ```

Step 3: Reboot the system

```bash
sudo reboot
```

## Development

### Backend TODOs

-   [ ] User Authentication (JWT + Google OAuth + GitHub OAuth)
-   [ ] Admin User Web APIs
    -   [ ] create new public/private view group
    -   [ ] add/remove workstations to/from view group
    -   [ ] add/remove users to/from view group (TBC)
-   [ ] Generate public view group URL

### Client TODOs

-   [ ] Register client as a service on system startup
    -   Ref: https://medium.com/codex/setup-a-python-script-as-a-service-through-systemctl-systemd-f0cc55a42267
    -   Ref: https://www.digitalocean.com/community/tutorials/how-to-use-systemctl-to-manage-systemd-services-and-units
-   [ ] Remove name-based identification of workstations, use Admin User's username as target for status updates
