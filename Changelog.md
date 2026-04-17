1.9.1
=====

Contributors:
- andrewjdarley

# Quality of Life
- Added an order suggestor to help players with mispelled orders

1.9.0
=====

Contributors
- Golden Kumquat
- thedarklizard

# New Features
- Added `.generate_layers` to populate the Army, Fleet, Retreat Army, Retreat Fleet, and Title layers with units/names
  - To use, have one sample object in each layer, and the command will place units and titles on the center of provinces if one does not exist already
- Added the Planiglobii variant
- Maps can now support per-nation unit designs
- `.edit_game set_capital` can now change a player's capital, which is reflected in the map if supported by the SVG

# Quality of Life
- Lots of map parser changes:
  - Added more layer names to search for in the layer dictionary
  - Added SVG support for units and SCs that are single objects and not groups
  - Sorting the scoreboard is now optional
  - More flexibility in what text of each scoreboard element is
  - More formatting options available for the Season Title
  - If a retreat layer is not found, will copy over the corrosponding unit layer as a backup
  - `.verify_svg()` now returns a list of issues instead of simply logging them
  - Removed warn_missing_coordinates() as the board is better at handling them

# Developer Chnages
- Refactored the game_management cog into smaller, more manageable modules based on function
- Moved fow, fish, and name parametres into board.data
- Split up some large methods into smaller chunks
- Moved a few ImpDip-specific values into the config file
- Moved some common operations into helper functions
- Combined FoW map generation logic with standard map generation
- Moved SQL calls out of parse_order and parse_edit_state modules
  - Added save_board_state() as a common call for all `.edit` commands
- Consolidated several common `.edit` and `.edit_game` commands that all did almost the same thing
- Added a format() function to Turn for more custom turn displaying
- Moved verify_adjacencies() into its own module
- TransGL3() properly handles scale transformations
- Moved import_game() to its own module
- Added more polymorphism to UnitOrders

# Bugfixes
- Island rings get colored in properly
- Civil disorder properly works when there are no units left
- Fixed order roles in renaming

1.8.1
=====

Contributors:
- aahoughton

# Quality of Life
- No longer considers "dead" players when running the `.ping_players` command
- Added aliases for the scheduling commands
  - ["s", "sched"] == `.schedule`
  - ["us", "unsched"] == `.unschedule`
  - ["vs", "vsched", "viewsched"] == `.view_schedule`
- Defaulted `.view_map` behaviour to use the "standard" colour mode, 

# GM Changes
- GMs can provide power roles to `.press_directory` to generate local copies in a GM channel

# Bugfixes
- Resolved error with requiring gm arguments when calling `.press_directory`

1.8.0
=====

Contributors
- Golden Kumquat

# New Features
- If a player did not order enough disbands, units will automatically be removed via civil disorder rules
- More DP updates:
  - Each power has a designated maximum number of DP that they can allocate per turn, set by default to 1/SC with a max of 3
  - If a player tries to allocate more DP than available, some DP allocations will be rendered invalid
  - `.ping_players` now alerts when someone has unspent or overspent DP
  - Added `.edit_game dp <disabled|enabled>`
- Added `.export_game` which outputs a JSON file of the current board state
- Added `.import_game` which creates a new game based on an exported JSON file
- Added `.rename_player` which changes a player's name and attempts to edit their role and channel names
- Variants can have custom scripts that can be loaded to give per-variant special rules

# Quality of Life
- More support for impassable provinces
  - Impassable provinces can now be included in the land/island/sea layers of the SVG and be parsed
  - Units can be ordered to impassable provinces, but they will automatically fail
  - `.edit set_province_owner <province> Impassable` now turns a province impassable
- `.adjudicate full` no longer converts the SVG to PNG twice for adjudication, saving up to 30 seconds per adjudication
- When parsing an SVG, the parser will now look for common layer names in addition to values supplied in the config.json's svg_config
- If there are multiple possible convoys for a unit, all will be displayed on the map
- Supports for a convoy will now point to the final fleet instead of all the way at the starting army

# Developer Changes
- Created some helper functions for common usage
- Combined logic with the nearly-identical `.view_map` and `.view_current`
- Moved parsing order strings from database to board
- Used a significantly faster function for adjacency searching

# Bugfixes
`.last_message` now properly works for renamed players

1.7.2
=====

Contributors
- Golden Kumuqat

# New Features
- Added rudimentary support for DP orders
  - Implementation follows the basic guidelines as laid out in https://nopunin10did.com/common-ruleset-for-dp-based-variants/
  - Powers can have "affiliates" that provide double strength DP allocations
  - DP allocations still need to be tracked manually for now
- Added Sortie option to Moves, which causes the unit to bounce/cut supports/etc., but does not actually move or dislodge the unit
- Added `.last_message` to track the last time each player has sent a message in the game's server
- Implemented non-active powers that are not controlled by a player but can have units that can be ordered (such as via DP)
  - Provinces in the initial SVG that do not have a power's color or a neutral color are considered part of a non-active power
  - Non-active powers can also be defined in the config by setting "active" to "false"

# Quality of Life
- Standarised some of the .help commands, particularly under Game Management
- Added support for each variant to have a config.json that each version can see and overwrite
- Added support for per-variant color palettes
- Upon loading a variant, the Parser now checks to see if there are any mismatching SVG labels before continuing

# Developer Changes
- Added a `.get_distance` method for Provinces, which is to be used for future development
- Renamed some ImpDip-specific terminology in the code

# Bugfixes
- `.adjudicate test` now displays red arrows for failed moves again
- Fixed a couple more issues regarding score panel generation

# Known Issues
- Score panel generation does not quite work with matrix transformations yet

1.7.1
=====
Contributors
- notnot

# New Features
- Added 'forced-disband' and 'free-retreat' arguments to view_orders; view which orders are forced retreats, or hide all forced retreats.

1.7.0
=====

Contributors
- aahoughton
- Golden Kumuqat

# New Features
- Added `.spec_ban` command group to apply country spectating bans as Code of Conduct violation penalties.
  - `.spec_ban add` can create a ban
  - `.spec_ban remove` can remove a ban
  - `.spec_ban view` can list outstanding bans
- Reorganized variants folder to split each variant its own subfolder and subrepo to allow for easier map development
- Added a welcome message to order channels when a game is created

# Quality of Life
- Reclassified `.remove_all` as a player command, GMs can still use in a GM channel to wipe all orders 
- Added a fix to strip unit designations when removing orders- `.remove f london` will become `.remove london` within the code
- Added a detection loop for newlines when using `.schedule` allowing multiple commands to be scheduled at once
  - Changed the task_id to use an 8 long hex string (obtained by slicing a uuid4)

# Developer Changes
- Lots of documentation and code clarity changes
- Split mapper into several smaller files for readability
- Changed how location data is stored in Province.py
- Added type checking to parser

# Bugfixes
- Movement to a specific coast displays properly
- .announce works again
- Minor fixes to neutral units
- Order warnings now work with retreats

1.6.0
=====

Contributors
- Golden Kumquat

# New Features
- Added an optional "transform" order during moves and/or builds that can change armies into fleets and vice versaq
- Added an option to allow convoys through islands
- Added the ability for start of game neutral armies, which can be supported but otherwise hold put
- Added difficult borders, which cause units to move with strength one less and prevents supports
- Added a .reload_variant command which forces a refresh of the map, adjacencies, and all boards
- Implemented .create_press_channel, which will automate channel creation for players

# Quality of Life
- Added warnings when players order moves or supports to non-adjacent provinces
- Added warnings when players do not specify a coast when ordering a fleet to a multi-coastal province
- Added a safeguard to prevent .adjudicate when orders are missing

# Bugfixes
- Fixed an issue when trying to change the coast of a build
- Fixed invalid orders causing a province to not properly appear as a retreat option

1.5.3
=====

Contributors
- aahoughton

# New Features
- Added a .press_directory command to output a list of all active press channels for a user's power in their orders channel

1.5.2
=====

Contributors
- hdwhite

# New Features
- Added a supportable_cores config value for variants
- Added a "control" version in build options where one can build in non-home SCs if they own all the non-sea provinces around it
- Added a .verify_adjacencies command to look for potential missing or extra connections in a variant

# Quality of Life
- Added failbacks and warnings of a unit coordinate could not be found
- Power banners no longer have to be created in an exactly specific way
- Players are given a warning if they build/disband more than they are supposed to
- GMs can set a non-integer number of hours for graces

# Bugfixes
- Fixed an issue when adding and hiding powers
- Retreating into a multi-coastal province works properly
- Fixed /advertise and /substitute
- Fixed /spec explicitly trying to find #admin-chat

1.5.1
=====

Contributors
- Golden Kumquat

# Bugfixes
- Fixed everyone's ages being negative
- Minor fixes for Southern ImpDip
- Fixes for multi-word players

1.5.0
=====

Contributors
- aahoughton
- Golden Kumquat

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

- Added .list_variants to show what maps have been loaded into the bot

# Quality of Life
- Added .adju / .adjudication as aliases to .adjudicate
- Added .pp as alias to .ping_players
- SVG parser now works if a path uses absolute coordinates
- Messages sent to orders channel after adjudication now show appropriate messages depending on phase
- .ping_players will no longer ping if there is a forced disband during retreat phases

# Bugfixes
- Fixed issue with the bot not finding a player's channel if they were using a nickname
- Retreat arrows now properly work for units in provinces that wrap around the board
- `.scoreboard` csv now sorts by original power name, not by nickname

# Developer Changes
- Added `Repository` class for handling save/load of individual data types, supporting abstraction for different storage methods

- Relationships table
  - Valid relationships defined in the RelationshipType `StrEnum`
  - Network of relationships between a subject ID and an object ID
  - Currently only used for the Community system (SERVER_MEMBER, COMMUNITY_MEMBER, COMMUNITY_OWNER)
  - TODO: Can be extended to hold other things, such as permissions based tags e.g. Moderator / Community Creator

- Split off Adjudicator into separate files for readability
- Removed the deprecated ConvoyMove
- Updated order_is_valid to return an Enum with level of validity

## Documentation
- Added documentation for many prefix command methods
- TODO: Write docstrings and comments for the more *core* systems e.g. Adjudicators and Mapping

1.4.5
=====
Contributors
- Golden Kumquat

Fixed some bugs related to Chaos maps

# Known Issues
- Points do not properly update on the scoreboard in Chaos games

1.4.4
=====
Contributors
- Golden Kumquat

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
- Golden Kumquat

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
- Golden Kumquat

Fixed some bugs with adjacencies of multiple coasts


1.4.0
=====
Contributors
- Golden Kumquat

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

