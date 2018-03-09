# Zulip Botfarm

A flask based interface for securely deploying Zulip bots online
without worrying about uptime issues of local deployment and the
security risks of running untested code on the main server.

## Usage

1. Clone this repository and `cd` into it.
2. `tools/activate` to install dependencies and activate virtualenv.
3. Ensure that Docker is running and your current user can access it.
4. `mkdir bots` for storing the bot data.
5. `tools/run` to run the Flask server.

Now, you can either read the code and manually interface with it, or
use the helper script with usage instructions: zulip/python-zulip-api#337

## Contributing

Please follow [Zulip's](https://github.com/zulip/zulip) commit message
guidelines.

The code is split into two files:

1. `deployer.py` - This file interfaces with the docker daemon.
2. `app.py` - This is the Flask server that provides GitHub login,
   token generation, and bindings to the `deployer.py` functions.
