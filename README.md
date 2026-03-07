# Clothing Portal

Web UI for batch uploading Roblox clothing to groups.

## Setup

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/)

2. Install dependencies:
   ```
   uv sync
   ```

3. Copy `.env.example` to `.env` and fill in your values:
   ```
   ROBLOSECURITY_TOKEN=     # Your Roblox account's .ROBLOSECURITY cookie
   PUBLISHER_USER_ID=       # User ID of the account that owns the cookie
   SECRET_KEY=              # Random string for signing session cookies
   ROBLOX_PROXY=            # Optional proxy (e.g. roproxy.com)
   PORT=                    # Port to run on; defaults to 8000
   ```

4. Create an admin account:
   ```
   uv run python -m src.create_admin
   ```

5. Start the server:
   ```
   uv run python -m src
   ```

   The app runs at `http://localhost:PORT`.

## Usage

1. Log in with your admin account
2. Create additional users from the **Admin** panel if needed
3. Go to **Upload**, select a group, asset type, and price
4. Add one or more items with a name, description, and PNG image
5. Click **Upload All** and watch live progress
6. View past uploads on the **History** page

## Security Notice

Automating interactions with Roblox (including uploading assets via the API) may violate the Roblox Terms of Use. Use of this tool is at your own risk. The authors are not responsible for any consequences, including account termination, resulting from its use.
