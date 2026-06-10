<div align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset=".github/readme_for_dark_theme.svg">
    <source media="(prefers-color-scheme: light)" srcset=".github/readme_for_light_theme.svg">
    <img alt="SteamFlow" src=".github/readme_for_light_theme.svg">
  </picture>
</div>

<p align="center">
<img src="https://hatscripts.github.io/circle-flags/flags/uk.svg" width="24"/>
<img src="https://hatscripts.github.io/circle-flags/flags/de.svg" width="24"/>
<img src="https://hatscripts.github.io/circle-flags/flags/es.svg" width="24"/>
<img src="https://hatscripts.github.io/circle-flags/flags/fr.svg" width="24"/>
<img src="https://hatscripts.github.io/circle-flags/flags/jp.svg" width="24"/>
<img src="https://hatscripts.github.io/circle-flags/flags/kr.svg" width="24"/>
<img src="https://hatscripts.github.io/circle-flags/flags/pl.svg" width="24"/>
<img src="https://hatscripts.github.io/circle-flags/flags/br.svg" width="24"/>
<img src="https://hatscripts.github.io/circle-flags/flags/ru.svg" width="24"/>
<img src="https://hatscripts.github.io/circle-flags/flags/cn.svg" width="24"/>
<img src="https://hatscripts.github.io/circle-flags/flags/tw.svg" width="24"/>
</p>

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
`steam top`
`steam deals`
`steam status`
`steam switch`
`steam wishlist`

## Features

### Local library
<img src=".github/localgames.png" width="500">

- Launch installed games directly from Flow Launcher
- Shows playtime, last played date, and achievement progress
- Display game update status and control downloads (pause/resume updates)
- Sorted by most recently played


### Steam Store search
<img src=".github/store.png" width="500">

- Search the Steam store by game name
- Shows review score, concurrent player count, price, and release date
- Browse Steam top sellers (`steam top`) and specials (`steam deals`)
- Owned games opens directly in your library


### Wishlist
<img src=".github/wishlist.png" width="500">

- Browse and search your Steam wishlist
- Shows current price, review score, and date added to wishlist
- Requires a Steam Web API key (`steam api` to configure)


### Adaptive context menu
<img src=".github/contextmenu.png" width="500">

- Open store page in Steam/[SteamDB](https://steamdb.info/)/[CS.RIN](https://cs.rin.ru/forum/viewforum.php?f=10)
- Open Community Guides and Discussions
- Open Recordings & Screenshots folder
- Open game Properties
- Browse local game files
- Check refund eligibility
- Add games to Steam shopping cart
- Add/remove games from Steam wishlist
- Install/Uninstall game


### Steam status
<img src=".github/status.png" width="500">

- Switch to Online, Invisible, or Offline in one click


### Account switcher
<img src=".github/switch.png" width="500">

- Switch between Steam accounts signed in on this PC and restart Steam instantly


### Steam Web API

> API key is encrypted and bound to active Steam account

- Detects owned games from store search
- Enables wishlist browsing
- Shows your active profile status


## Installation

type `pm install SteamFlow by keekys`in FlowLauncher