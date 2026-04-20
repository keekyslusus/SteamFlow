<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/readme_for_dark_theme.svg">
    <source media="(prefers-color-scheme: light)" srcset=".github/readme_for_light_theme.svg">
    <img alt="SteamFlow" src=".github/readme_for_light_theme.svg">
  </picture>
</div>

<p align="center">
  <img src="https://img.shields.io/github/downloads/keekyslusus/SteamFlow/total?style=flat-square&color=black&labelColor=blue">
  <img src="https://img.shields.io/github/stars/keekyslusus/SteamFlow?style=flat-square&color=black&labelColor=blue">
  <img src="https://img.shields.io/github/last-commit/keekyslusus/SteamFlow?style=flat-square&color=black&labelColor=blue">
  <img src="https://img.shields.io/github/v/release/keekyslusus/SteamFlow?style=flat-square&color=black&labelColor=blue">
</p>

## SteamFlow: steam plugin for [Flow Launcher](https://www.flowlauncher.com/)

### Search Steam store and launch games and more

<img src=".github/peenar.gif" width="500">

### Commands

`steam ?`
`steam api`
`steam status`
`steam switch`
`steam wishlist`

## Features

### Local library
<img src=".github/localgames.png" width="500">

- Launch installed games directly from Flow Launcher
- Shows playtime, last played date, and achievement progress
- Live install/update status badges
- Sorted by most recently played


### Steam Store search
<img src=".github/store.png" width="500">

- Search the Steam store by game name
- Shows review score, concurrent player count, price, and release date
- Owned games opens directly in your library


### Wishlist
<img src=".github/wishlist.png" width="500">

- Browse and search your Steam wishlist
- Shows current price, review score, and date added to wishlist
- Requires a Steam Web API key (`steam api` to configure)


### Adaptive context menu
<img src=".github/contextmenu.png" width="500">

- Open store page in Steam or [SteamDB](https://steamdb.info/)
- Open Community Guides and Discussions
- Open Recordings & Screenshots folder
- Open game Properties
- Browse local game files
- Check refund eligibility
- Install or Uninstall game


### Steam status
<img src=".github/status.png" width="500">

- Switch to Online, Invisible, or Offline in one click


### Account switcher
<img src=".github/switch.png" width="500">

- Switch between Steam accounts signed in on this PC and restart Steam instantly


### Steam Web API

> API key is encrypted with Windows DPAPI and bound to your Steam account.

- Detects owned games from store search
- Enables wishlist browsing
- Shows your active profile status (Online, playing a game, etc.)

## TODO:

- Pause/resume download/update for installing/updating games using Remote access [(`IClientCommService`)](docs/clientcomm.md)
- `Add to Google Calendar` context menu option in `steam wishlist` for upcoming games with a known release date
- `steam recent` with `IPlayerService/GetRecentlyPlayedGames` under discussion
- Commands to display the `New & trending`, `Top sellers` and `Specials` lists

## Installation
type `pm install SteamFlow by keekys`in FlowLauncher

or

Unzip [archive](https://github.com/keekyslusus/SteamFlow/releases/latest) to `%appdata%\FlowLauncher\Plugins`
