# Template Media Player

[![My Home Assistant](https://img.shields.io/badge/Home%20Assistant-%2341BDF5.svg?style=flat&logo=home-assistant&label=My)](https://my.home-assistant.io/redirect/hacs_repository/?owner=EuleMitKeule&repository=template-media-player&category=integration)

![GitHub License](https://img.shields.io/github/license/eulemitkeule/template-media-player)
![GitHub Sponsors](https://img.shields.io/github/sponsors/eulemitkeule?logo=GitHub-Sponsors)

> [!NOTE]
> This integration is strongly inspired by [media_player.template](https://github.com/Sennevds/media_player.template).<br>
> Unfortunately that integration is missing some features, so I decided to create a new and improved one.

With Template Media Player you can create media player entities in Home Assistant using templates and scripts.<br>
You can define any attribute you want and create custom behaviour for all services supported by the `media_player` domain.<br>
This allows you to combine your existing media players into a single entity for improved usability and control or to create completely new media players from scratch.

## Installation

You can install this integration using the custom repository option in [HACS](https://hacs.xyz/).<br>

1. Add the repository URL to the list of custom repositories in HACS
2. Select and install the integration in HACS
3. Restart Home Assistant
4. Configure your entities

## Configuration

To create the entities you need to define them in your `configuration.yaml` file.<br>
For a full example of all available options see [examples](examples/configuration.yaml).

```yaml
media_player:
  - platform: template_media_player
    media_players:
      my_media_player:
        unique_id: my_media_player
        name: My Media Player
        device_class: tv
        icon: mdi:television
        state: "on"
```

### Templates

All main options and all elements of the `attributes` object can be defined using Jinja2 templates:

```yaml
# ...
state: >
  {% if states('media_player.something") == "on" %}
    idle
  {% else %}
    off
  {% endif %}
```

#### Attributes

To define state attributes for your entity use the `attributes` option.<br>
You can use the variable `attribute` in your templates to get the current attributes name as a string.<br>
For a full list of attributes commonly used by media player entities see [examples](examples/configuration.yaml).

```yaml
media_player:
  - platform: template_media_player
    media_players:
      my_media_player:
        #...
        attributes:
            media_title: >
              # `attribute` contains the value "media_title"
              {{ state_attr("media_player.something", attribute) }}
```

#### Global Template

To define common template code that should be executed before every template, you can use the `global_template` option.
This template will be prepended to all other templates and recalculated each time the entity is updated.<br>

```yaml
media_player:
  - platform: template_media_player
    media_players:
      my_media_player:
        #...
        global_template: >
          {% set tv = "media_player.tv" %}
          {% set soundbar = "media_player.soundbar" %}
        state: >
          {{ states(tv) }}
        attributes:
          volume_level: >
            {{ state_attr(soundbar, "volume_level") }}
```

#### Variables

To reduce code duplication you can also define variables using the `variables` option.
This is a dictionary of variables that can be used in all templates of the media player entity **and** in `service_scripts`, `source_scripts`, and `sound_mode_scripts`.
Unlike `global_template` (which is prepended only to entity templates, not scripts), `variables` are passed into scripts when they run.

```yaml
media_player:
  - platform: template_media_player
    media_players:
      my_media_player:
        #...
        variables:
          tv: "media_player.tv"
        state: >
          {{ states(tv) }}
        service_scripts:
          media_play:
            - action: media_player.media_play
              target:
                entity_id: "{{ tv }}"
```

### Scripts

Elements of the `service_scripts`, `source_scripts` or `sound_mode_scripts` options are action sequences like in Home Assistant scripts.

```yaml
media_player:
  - platform: template_media_player
    media_players:
      my_media_player:
        #...
        source_scripts:
          Plex:
            - service: media_player.turn_on
              data_template:
                entity_id: media_player.tv
            - delay:
                seconds: 3
            - service: media_player.select_source
              data_template:
                entity_id: media_player.tv
                source: Plex
```

#### Service Scripts

Use the `service_scripts` option to define services that are supported by the `media_player` domain.<br>
For a full list of services and their respective variables supported by media player entities see [examples](examples/configuration.yaml).

```yaml
media_player:
  - platform: template_media_player
    media_players:
      my_media_player:
        #...
        service_scripts:
          turn_on:
            - service: media_player.turn_on
              data_template:
                entity_id: media_player.tv
```

#### Source Scripts

Use the `source_scripts` option to define sources for your media_player.

```yaml
media_player:
  - platform: template_media_player
    media_players:
      my_media_player:
        #...
        source_scripts:
          Plex:
            - service: media_player.select_source
              data_template:
                entity_id: media_player.tv
                source: Plex
```

#### Sound Mode Scripts

Use the `sound_mode_scripts` option to define sound modes for your media_player.

```yaml
media_player:
  - platform: template_media_player
    media_players:
      my_media_player:
        #...
        sound_mode_scripts:
          Bass Boost:
            - service: media_player.select_sound_mode
              data_template:
                entity_id: media_player.soundbar
                source: Bass Boost
```

### Base Media Player

You can specify an entity using the `base_media_player_entity_id` option to inherit all supported behaviour and attributes from, when the behaviour or attribute is not implemented by the template media player.

### Browse And Search Media

Existing configs keep working. You can combine these options; they are tried in this order:

1. `browse_media_sources` for the folder tree (and for playback of items picked there)
2. `service_scripts.browse_media` / `service_scripts.search_media` for a fully custom tree
3. `browse_media_entity_id` / `search_media_entity_id` (or `base_media_player_entity_id`)

`play_media` is still required unless a browse source already knows which entity should play.

#### Delegate to another media player

You can specify an entity to use for browse media and search media using `browse_media_entity_id` and `search_media_entity_id`.  
Make sure you also define the `play_media` service for this to work.

#### Multiple libraries as folders

To show several libraries (Plex, Spotify, …) as folders in the media browser, use `browse_media_sources`. Each entry can point at a media player entity and/or a `media_source` domain. Thumbnails default to the Home Assistant brand icon of that integration (`entity_id` platform, `media_source`, or an explicit `domain`). If an extra attribute `player` is set to a `media_player.*` entity, album art is taken from that child; otherwise `picture` / `entity_picture` templates behave as they did previously.

```yaml
media_player:
  - platform: template_media_player
    media_players:
      my_media_player:
        # ...
        browse_media_sources:
          Plex:
            entity_id: media_player.plex_living_room
            source: Plex  # optional: select this source before playing
          Spotify:
            entity_id: media_player.spotify
            source: Spotify
            media_source: spotify  # optional fallback when the player is unavailable
            # thumbnail: https://example.com/spotify.png  # optional override
            # domain: spotify  # optional brand-icon override
```

`source` is the template player's own source name (from `source_scripts`) and is selected before playback. Service names are not hardcoded — any integration that exposes browse/play on a media player or media source works.

#### Custom browse / search scripts

You can define `browse_media` and `search_media` under `service_scripts` when you need a custom tree. Scripts receive the entity `variables` plus the inputs below, and must return data via `response_variable` (the last responding action’s `service_response`).

*browse_media*  
Inputs: `media_content_type`, `media_content_id`  
Output: a dictionary matching Home Assistant `BrowseMedia`:

```yaml
media_class: directory
media_content_id: ""
media_content_type: apps
title: Media
can_play: false
can_expand: true
children: []          # optional
children_media_class: app
thumbnail:            # optional
not_shown: 0          # optional
can_search: false     # optional
```

*search_media*  
Inputs: `media_content_type`, `media_content_id`, `search_query`, `media_filter_classes`  
Output:

```yaml
media:
  - media_class: track
    media_content_id: ...
    media_content_type: music
    title: ...
    can_play: true
    can_expand: false
```
