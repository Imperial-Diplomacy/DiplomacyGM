# DiploGM architecture notes

## `main.py`

Imports some config values from `DiploGM.config` (which also loads `config.toml`)

Configures `logging` based on the config

Unused imports as legacy from when dotenv was used? Can probably be deleted

Import the bot from `DiploGM.bot`

Creates the bot with the intents required (moves over to `__init__` in `DiploGM.bot`)

## `DiploGM/bot.py`

`DiploGM` the class inherits from `discord.ext.commands.Bot`
passes the command prefix and intents to the parent class's init (idk proper terms, I don't reallyoop)
Logs `creation_time` and `last_command_time` (for doing the time taken for command stuff?)

`setup_hook`, called on the bot logging in, sets up a number of functions to run on specific things happening, and loads all cogs (extensions) specified
- `before_any_command` logs the command and thumbs-up reacts
- `after_any_command` logs the time taken to execute the command
- `on_message_listener` keeps track of when players are last active
- creates a `Manager`, which manages boardstates and db interfacing etc (very important)

the "cogs" (extensions) loaded in the default config are:
- administration
- command
- development
- fog_of_war
- extension_management
- game_management
- moderation
- party
- player
- schedule
- slash_substitute
- spectator

all `app_commands` (slash commands) get synced


extensions can be loaded, unloaded and reloaded by superusers with `.extension_load`, `.extension_unload` and `.extension_reload` as part of the `extension_management` cog






