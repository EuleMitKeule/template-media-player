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
This is a dictionary of variables that are calculated once on startup and can be used in all templates of the media player entity.
Unlike `global_template`, variables are only calculated once when the entity is initialized.<br>

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

#### Script

You can define a script under `source_scripts` for the `browse_media` and `search_media` services.

Ensure that your script takes the following variables and returns the following schema:

*search_media*  
Inputs:  
* media_content_type: string
* media_content_id: string
* search_query: string
* media_filter_classes: list[string]

Output:  
```yaml
- media_class: MediaClass | str,
  media_content_id: str,
  media_content_type: MediaType | str,
  title: str,
  can_play: bool,
  can_expand: bool,
  children: Sequence[BrowseMedia] | None = None,
  children_media_class: MediaClass | str | None = None,
  thumbnail: str | None = None,
  not_shown: int = 0,
  can_search: bool = False,
```

*browse_media*  
Inputs:  
* media_content_type: string
* media_content_id: string

Output:  
```yaml
media_class: MediaClass | str,
media_content_id: str,
media_content_type: MediaType | str,
title: str,
can_play: bool,
can_expand: bool,
children: Sequence[BrowseMedia] | None = None,
children_media_class: MediaClass | str | None = None,
thumbnail: str | None = None,
not_shown: int = 0,
can_search: bool = False,
```

#### Entities

To use a media_player entity
You can specify an entity to use for the browse media and search media functionalities using the `browse_media_entity_id` and `search_media_entity_id` options.<br>
Make sure you also define the `play_media` service for this to work.
