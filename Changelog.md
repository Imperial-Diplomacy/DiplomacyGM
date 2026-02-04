1.5.0
=====

Contributors
- aahoughton

# New Features
- Grace/Extension tracking system
  - Can be filitered by GMs for instances per user or per server
- Simple up/down Reputation Delta system
  - Requires more work to include the complexities of how subbing affects gains/losses
- Community system
  - Allows the definition of meta groups that users can join or leave
  - Allows registering of servers to communities
  - Automatic tracking of user membership to servers
  - On joining a server, DiploGM will automatically populate the relationships table with SERVER_MEMBER tags

- .me
  - Returns some information about yourself (ID, username, mention for server)
  - Returns community memberships
  - Returns server memberships

# Quality of Life
- Added .adju / .adjudication as aliases to .adjudicate
- Added .pp as alias to .ping_players

# Developer Changes
- Added `Repository` class for handling save/load of individual data types, supporting abstraction for different storage methods

- Relationships table
  - Valid relationships defined in the RelationshipType `StrEnum`
  - Network of relationships between a subject ID and an object ID
  - Currently only used for the Community system (SERVER_MEMBER, COMMUNITY_MEMBER, COMMUNITY_OWNER)
  - TODO: Can be extended to hold other things, such as permissions based tags e.g. Moderator / Community Creator

## Documentation
- Added documentation for many prefix command methods
- TODO: Write docstrings and comments for the more *core* systems e.g. Adjudicators and Mapping

1.4.5
=====
Contributors
- hdwhite

Fixed some bugs related to Chaos maps

# Known Issues
- Points do not properly update on the scoreboard in Chaos games

1.4.4
=====
Contributors
- hdwhite

# New Features
- Added in an .edit_game command which can modify parameters of a game:
  - build_options: Allows for building in home SCs only, building anywhere, or enables coring mechanic
  - victory_conditions: Classic-style (all powers must reach X SCs), or VSCC with different SC goals for each country
  - victory_count: For classic-style victory conditions, the number of SCs required to win
  - iscc: For VSCC victory conditions, the number of SCs required to win for a given power
  - vscc: For VSCC victory conditions, the initial SC count for a given power
  - player_name: Edits the name of a power
  - hide_player: Causes a power to not show up in scoreboards
  - add_player: Adds a new power to the game. This cannot be undone

1.4.3
=====
Contributors
- hdwhite

# Features
- Doing .scoreboard now shows SC and unit changes
- .sb added as an alias for .scoreboard

# Bugfixes
- Fixed an issue with the bot crashing when someone tried building a fleet on a multi-coastal province without specifying a coast
- Fixed an issue in .view_gui where moving a fleet to a sea tile would send it to the Arctic instead
- Fixed a year 0 issue that was causing startup to take longer than expected

# Backend Changes
- Added a PhaseName Enum to make Turns slightly better
- Added a lot more type checks to hopefully catch bugs earlier
- Refactored a few functions to be slightly less complicated

# Test Changes
- Added DATC tests that had been previously commented out due to bot limitations
- All DATC tests pass!

1.4.2
=====
Fixed GUI file location

1.4.1
=====
Contributors
- hdwhite

Fixed some bugs with adjacencies of multiple coasts


1.4.0
=====
Contributors
- hdwhite

# Infrastructure Changes
- Removed Coasts as a separate Loction from Provinces
  - All Provinces will now store adjacency and coordinate data for each coast
  - Units will now keep track of whether they are in a coast
  - Retreats to coasts will function properly
  - Specifying a coast in the destination is now optional if there's only one valid coast to move to
  - References to Locations and Coasts have been properly moved to Provinces
  - Added back-compatability for existing games in the database

# Backend changes
- Added a significant number of type checks
- Fixed parse_season and made it use Turns

# Test Changes
- Updated unit tests to make use of the Classic map
- Added several tests for parse_edit_state, parse_order, and parse_season

1.3.4
=====

Contributors
- aahoughton

# Player Changes
- Changed styling of orders displayed by `.view_gui` to distinguish it from the outputs of `.view_map`

# Variant Changes
- Added support for a new subvariant of Imperial Diplomacy for an event being arranged by CaptainMeme of DiploStrats

# Moderator Changes
- Added a new method that reports on players when joining servers managed/observed by DiploGM under the following conditions:
  - Account is less than 2 weeks old
  - Account is not a member of the Imperial Diplomacy Hub Server
  - Account is not verified on the Imperial Diplomacy Hub Server

# Developer Changes
- Replaced fetches of past and/or future board statess to use `get_board()` or the stored `board_id` attached to the handled object, not the current `server_id`

1.3.3
=====

Contributors
- Chloe

# Player Changes
- Fixed `.view_gui`


# Develper Changes
- Fixed `.announce` for servers with no gm_channels
- Fixed incorrect path for `mapper.js`
- when eolhc runs `.eolhc` in the Hub server it no longer edits DiploGM's nickname

1.3.2
=====
*further panicking*

Contributors
- Chloe


# Developer Changes
- fixed 11-RenamedVariants.py based on changes to `get_parser()` in `1.3.1`

1.3.1
=====
*panic*

Contributors
- Chloe


# Developer Changes
- Fixed `11-RenamedVariants.py`
- in `.gitmodules` made `variants` submodule use ssh instead of https for cloning 
- fixed `get_parser()` for `impdip.1.4.chaos`

1.3.0
=====
Please never make me do a merge again.


Contributors
- Chloe
- Golden Kumquat

# Fun Commands
- .eolhc: no further questions

# Player Bugfixes
- fixed `/substitute` 
- fixed year display for negative years (now shows BCE)
- readded Adjudication Information messages


# GM Changes
- Depreciated `.vm true` and `.vc true`.
- Added `#gm-bot-commands` as a valid GM command channel.
- Removed `#bot-spam` as a valid GM command channel.


# Developer Changes
so a lot changed....

## Added DiploGM.service to repo

- Moved Map Archive environment variables to `config.toml`


## Variants Submodule
Variants have been moved to their own private submodule at https://github.com/Imperial-Diplomacy/DiplomacyGM-Variants/. 
Variant names have also been standardised.
This uses a git submodule that can be updated separately. This means that the previous `config/` and `assets/` have been removed.
#### There is an update to the database be sure to apply `sqlite3 bot_db.db < DiploGM/db/SQL/11-RenamedVariants.sql`

## The refactor
This is an attempt to document all the changes that are part of this.
- Moved all functions relating to permissions out of `utils.py` into `perms.py`.
- split up `utils.py`.
- moved `fish_pop_model()` to the `PartyCog`.
- moved `santise.py` into the `utils` package.
- renamed `bot` package to `DiploGM`.
- merged `DiploGM` and `diplomacy` packages.
- removed both `core` packages. Events have been moved to their own `events` package and singleton into `utils`.
- `bot/assets/` has been moved to `assets/`.
- `diplomacy/persistance/db/` has been moved to `DiploGM/db/`.
- `persistance` package has been renamed `models`.
- removed `utils.whitespace_dict` as it was only used once and contained one item.
- moved `utils.simple_player_name()` to `utils.sanitise.simple_player_name()`.
- moved functionality of `get_player_by_role()` into the Manager.
- removed unused `discord_id` property from `Player`.
- moved `get_keywords()`, `_manage_coast_signature()`, `get_unit_type()`, `parse_season()` & `get_value_from_timestamp()` to `sanitise.py`
- moved `get_role_by_player()` into `Player`.
- `Player` now has a reference to its `Board`.
- moved `is_player_channel()` into `perms.py`.
- removed `get_channel_by_player.
- moved `get_player_by_name()` into `Board`.
- moved `get_maps_channel()` and `get_orders_log()` into `game_management.py`

## Other Changes
- renamed ordered scoreboard functions.
- Added `assets/*_adjacencies.txt`, `*.pclprof` & `logs/*` and removed `assets/`.
- depreciated `get_latest_board()`.
- `Phase` has been replaced with `Turn`.
- `IMPDIP_SERVER_SUBSTITUTE_LOG_CHANNEL_ID` is no longer a list ( this was breaking `/substitute`).
- `.su_dashboard` now sorts extension list.
- logs generated by `config.py` are now outputted by `main.py` using `output_config_logs()` 
- Fix `.announce` giving the wrong type to `is_gm_channel()`
- Removed `adjacent.py`, `colinear.py,` `graphical_adjacencies.py`, `server.txt` & `test_miwok.py`

1.2.1
=====
*Otter jumps off a diving board, throws a fish at aahoughton, performs a perfect front flip into the pool*

Released: 2025/09/20

Contributors to this release:
- Golden Kumquat


# Developer Changes
- Added missing `CommandPermissionError` import to `perms.py`

1.2.0
=====
The wheels on the bus go round and round... round and round... round and round...

Also the formatter got hungry again :(

Released: 2025/09/20

Contributors to this release:
- aahoughton

# GM Changes
- Reverted previous attempt to remove inland fleets by auto appending "coast" when using command `.edit create_unit` for fleets that resulted in failure to create units on Sea Provinces

# Developer Changes
- Optimised `Manager` initialisation by only loading games for which DiploGM is currently managing (managing a game defined as being a member of the server)
  - Required definition of Manager to occur within `DiploGM.setup_hook`, which must be the first location that `Manager` is called for this functionality
  - This functionality can be reversed at any time by setting the `board_ids` argument in `Manager(board_ids=current_servers)` to `None`
- Created `./bot/core/` directory
  - Created `eventbus.py` to facilitate Event-Driven communication within the codebase
- Created `./diplomacy/core/` directory
  - Created `events.py` to hold Diplomacy Event type definitions (contents minimal)
  - Created `base_listener.py` to define an abstract class for listening and processing of raised Diplomacy Events over the EventBus
- Renamed `ManagerMeta` to `SingletonMeta` and moved to `./bot/core` so that the structure can be reused for other classes
  - Introduced `force_new` boolean argument to create fresh instances (for example when writing tests) 
- Added `get_latest_board()` to `database.py`
  - Added a catch if `Manager.get_board()` fails (no board is currently loaded for that game), `get_latest_board()` attempts to find one on the database. 
- Moved `CommandPermissionError` into new file `errors.py`

## Event Bus
Event Bus is initialised in `setup_hook` as a publish-subscribe observer pattern connector of BaseListener types
It can be accessed within the code base using `bot.eventbus.publish(event)` only Listeners should use the subscribe model

## Event Listeners
An abstract listener is located in `diplomacy/core/base_listener.py`

Custom listeners are currently setup to be created in `diplomacy/listeners` and should feature a type that subclasses the abstract listener, listeners are primarily setup to handle one event, though can be setup to handle multiple if truly desired
An example listener is located in `diplomacy/listeners/event_counter.py`, 

1.1.0
=====
I broke `.adjudicate`... just not that bad.

Released: 2025/11/17

Contributors to this release:
- Chloe
- aahoughton
- oliu


# Fun commands
- added `.shutdown`, posts a message.

# GM Changes
These most likely won't be relevant to you unless you're a GM/Angel
- Fixed posting the `.scoreboard csv` to the automatic winter scoreboard output thread. This will stop the errors generated by `.adjudicate`
- Postponed adjudication announcements on `.publish_orders` until an easier method to identify player voids
  - Seems a matter of controversy amongst 'some' of the GMs, but have thus far only heard approval from players.
- Added `bulk` to `.edit`, it allows you to execute `set_core`, `set_province_owner`, `set_province_half_core`, `set_total_owner` to and `delete_unit` a lot of times reducing the amount of copy pasting to edit a big map.
- Added `bulk_create_units` to `.edit`, it allows you to create a lot of units from the same country and type.

# Hellenic Diplomacy
Authored by Con-Pope
- Uploaded modifed config json
  - Added new adjacency and updated starting supply centre counts

# Developer Changes
These most likely won't be relevant to you unless you're a Developer and/or a Superuser.

## Extension Management Cog
Extension management was moved to its own cog to prevent accidental unloading
- New ExtensionManagement Extension and Cog
- `DiploGM.load_extension()`, `DiploGM.reload_extension()` and `DiploGM.unload_extension()` nolonger prepend `bot.cogs.` to extension names when called. This was causing issues, as the base implementation of `reload_extensions` was calling.
- Added wrapper functions `load_diplogm_extension`, `reload_diplogm_extension` & `unload_diplogm_extension` that preprend the extension directory `bot/cogs/` to extension names passed to them.
- Added logging to `DiploGM.reload_extension()` and `DiploGM.unload_extension()`
- `.extension_reload` doesn't list the extension name twice in error messages
- `DiploGM.unload_diplogm_extension` and `DiploGM.reload_diplogm_extension` don't no longer call `load_extionsion` instead of their correct respective functions.
## Other Changes
- Moved superuser list to `config_defaults.toml` and moved `is_superuser` to `perms.py`
- `ScheduleCog.close()` doesn't generate an error message due to calling `.cancel` on a function which isn't a loop anymore

1.0.0
=====
First versioned release - though there has been many prior releases.

Released: 2025/11/16

Contributors to this release:
- Chloe
- a(dev)ahoughton

# Changelog and repository updates
- Repository moved to https://github.com/Imperial-Diplomacy/DiplomacyGM
- updated README.md with changelog, versioning and release information.
- added `Changelog.md`
- `dev` now acts as a staging branch where PRs should be opened to.


# Hellenic Diplomacy
HellaDip should be fully supported by the bot.
- Support for years before 1 A.D.
- New way of detecting units for Helladip, you now get some fleets.

# GM changes
These most likely won't be relevant to you unless you're a GM/Angel
- `.schedule` will now correctly ping you if an error occurs.

# New Superuser
Golden Kumquat is now a superuser, [per](https://discord.com/channels/1262215477237645314/1262215478072447019/1439753744072970460). Another one to stand up to the tyranny of DiploGM!

# Developer changes
These most likely won't be relevant to you unless you're a Developer and/or a Superuser.

**DEVELOPERS: you will need to create a `config.toml` and put your discord token in it. `.env` has been depreciated.**


## Development Cog
New Cog for developer commands
- `.su_dashboard command` dashboard for the bot - currently only shows loaded extensions and cogs.
- `extension_load`, `extension_unload` & `extension_reload` Can be used to reload extensions and their Cogs.
- `shutdown_the_bot_yes_i_want_to_do_this` command to shutdown the bot.

## Other changes
- Switch to `config.toml` instead of `.env`.
- A lot of hardcoded values have also been moved to `config.toml`.
- Supports logging levels of `CRITICAL` and `INFO` in config.
- Only Extensions in `config.toml` - extensions.load_on_startup are loaded on startup.
- terminology for admin's for the bot have been changed from "bot" to "superuser" to avoid confusion with community admins.
- scheduled commands are saved and deleted from disk instantly.
- commands scheduled in deleted channels are now automatically deleted.
- commands scheduled by users that can't be found are now not run and are deleted.
- scheduled commands now create an artificial Message to invoke a command instead of sending a message to create a new on. This lets superusers schedule superuser commands.
- scheduled commands have better error reporting.
- helladip didn't use the new or old system of unit detection. I didn't want to mess around with the svg so now it checks for what the unit is called in the svg.
- adding logging for SVG -> PNG conversion.
- deleted `_command.py`. Cogs are now stable.

