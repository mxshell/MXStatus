# MXShell Client Installation

## Install

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
    ./client/installer install
    ```

    The installation script will create a systemd service to run the Client in the background. The service will be started automatically when the workstation boots up.

## Maintenance

Check the status of the Client service:

```bash
sudo systemctl status MXShellClient
```

To restart the Client service, run:

```bash
sudo systemctl restart MXShellClient
```

To check the system logs of the Client, run:

```bash
sudo journalctl -u MXShellClient
```

## Uninstall

To remove the Client from a workstation, run:

```bash
./client/installer uninstall
```
