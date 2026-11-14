# MXShell Client Installation

## Install

To install the Client on your workstations:

1. Clone this repository to a permanent location on your workstation; Navigate to the project root directory.

2. Prepare a Python virtual environment for the Client:

    ```bash
    python3.12 -m venv venv
    source venv/bin/activate
    pip install -r requirements.txt
    ```

3. Download `config.json` from the server’s `/admin/` panel using **Connect a client**,
   or edit [config.json](config.json): set `server_address` to your HTTPS server URL,
   and `report_key` to a key configured or created on the server. The example key is
   deliberately empty; the client exits with an error until configured. Keys must
   contain 16–64 ASCII letters or digits. `report_interval` must be an integer from
   1 to 86400 seconds. Use Python 3.12 or newer. Restrict the config file's
   permissions with `chmod 600 client/config.json` and do not commit real keys.

   Requests use 5-second connect and 15-second read timeouts; commands have a
   10-second timeout. Failed reports are retried with at most 300 seconds of extra
   delay. The client contacts the configured server directly, so private networks
   do not need access to Google. GPU process telemetry includes executable names,
   without command-line arguments that might contain passwords or tokens. Per-process
   CPU usage is measured between reports and is unavailable on the first sample.
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

Reporting intervals can also be set per client in the admin panel. Updated clients
apply the change after their next successful report; clearing the override restores
the local interval. Blocking reports does not stop the client service.
