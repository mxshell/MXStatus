# Documentation for the server

## Functions

### Client-Server Communication

-   [ ] `report`

### Web-Server Communication

-   [ ] `view`

### Admin Web-Server Communication

-   [ ] Access
    -   [ ] Sign up (High priority)
        -   [ ] Sign up using Google
        -   [ ] Sign up using GitHub
        -   [ ] Sign up using email (JWT)
    -   [ ] Sign in (High priority)
    -   [ ] Delete account
-   [ ] `report_key`
    -   [ ] Get all current `report_key`
    -   [ ] Add a new `report_key`
        -   [ ] Use a custom or random `report_key`
    -   [ ] Edit the description of a `report_key`
    -   [ ] Delete single/multiple `report_key`
-   [ ] `view_group`
    -   [ ] Get all current `view_group`
    -   [ ] Create a new `view_group`
        -   [ ] Use a custom or random `view_key`
    -   [ ] Edit the name of a `view_group`
    -   [ ] Edit the description of a `view_group`
    -   [ ] Edit the password of a `view_group` (optional) (low priority)
    -   [ ] Delete single/multiple `view_group`
    -   [ ] Enable `view_group`
    -   [ ] Disable `view_group`
    -   [ ] Auto-Disable Timer (disable after a certain timestamp)
        -   [ ] Set timer
        -   [ ] Remove timer
    -   [ ] Add single/multiple `machine_id` to the `view_group`
    -   [ ] Remove single/multiple `machine_id` from the `view_group`
-   [ ] `admin_view`: Get the latest machine updates grouped by `report_key`
    -   [ ] Blacklist `machine_id` (for the current user)
