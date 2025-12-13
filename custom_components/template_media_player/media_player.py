"""Template Media Player Component for Home Assistant."""

from collections.abc import Callable, Sequence
import logging
from typing import Any, cast

import voluptuous as vol

from homeassistant.components.media_player import (  # type: ignore[attr-defined]
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    PLATFORM_SCHEMA as MEDIA_PLAYER_PLATFORM_SCHEMA,
    BrowseMedia,
    MediaPlayerDeviceClass,
    MediaPlayerEntity,
    MediaPlayerEntityFeature,
    MediaPlayerState,
    MediaType,
    RepeatMode,
    SearchMedia,
    SearchMediaQuery,
    async_process_play_media_url,
)
from homeassistant.components.media_source import (
    async_resolve_media,
    is_media_source_id,
)
from homeassistant.components.template.template_entity import TemplateEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, TemplateError
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.script import (  # type: ignore[attr-defined]
    Script,
    ScriptRunResult,
    Template,
)
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import (
    CONF_ATTRIBUTES,
    CONF_BASE_MEDIA_PLAYER_ENTITY_ID,
    CONF_BROWSE_MEDIA_ENTITY_ID,
    CONF_BROWSE_MEDIA_SCRIPT,
    CONF_CLEAR_PLAYLIST_SCRIPT,
    CONF_DEVICE_CLASS,
    CONF_GLOBAL_TEMPLATE,
    CONF_ICON,
    CONF_JOIN_SCRIPT,
    CONF_MEDIA_NEXT_TRACK_SCRIPT,
    CONF_MEDIA_PAUSE_SCRIPT,
    CONF_MEDIA_PLAY_PAUSE_SCRIPT,
    CONF_MEDIA_PLAY_SCRIPT,
    CONF_MEDIA_PLAYERS,
    CONF_MEDIA_PREVIOUS_TRACK_SCRIPT,
    CONF_MEDIA_SEEK_SCRIPT,
    CONF_MEDIA_STOP_SCRIPT,
    CONF_NAME,
    CONF_PICTURE,
    CONF_PLAY_MEDIA_SCRIPT,
    CONF_REPEAT_SET_SCRIPT,
    CONF_SEARCH_MEDIA_ENTITY_ID,
    CONF_SEARCH_MEDIA_SCRIPT,
    CONF_SERVICE_SCRIPTS,
    CONF_SHUFFLE_SET_SCRIPT,
    CONF_SOUND_MODE_SCRIPTS,
    CONF_SOURCE_SCRIPTS,
    CONF_STATE,
    CONF_TOGGLE_SCRIPT,
    CONF_TURN_OFF_SCRIPT,
    CONF_TURN_ON_SCRIPT,
    CONF_UNIQUE_ID,
    CONF_UNJOIN_SCRIPT,
    CONF_VARIABLES,
    CONF_VOLUME_DOWN_SCRIPT,
    CONF_VOLUME_MUTE_SCRIPT,
    CONF_VOLUME_SET_SCRIPT,
    CONF_VOLUME_UP_SCRIPT,
)

_LOGGER = logging.getLogger(__name__)

MEDIA_PLAYER_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME): cv.template,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
        vol.Optional(CONF_ICON): cv.template,
        vol.Optional(CONF_PICTURE): cv.template,
        vol.Optional(CONF_VARIABLES): cv.SCRIPT_VARIABLES_SCHEMA,
        vol.Optional(CONF_DEVICE_CLASS): cv.string,
        vol.Optional(CONF_GLOBAL_TEMPLATE): cv.template,
        vol.Optional(CONF_STATE): cv.template,
        vol.Optional(CONF_BASE_MEDIA_PLAYER_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_BROWSE_MEDIA_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_SEARCH_MEDIA_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_ATTRIBUTES, default={}): {cv.string: cv.template},
        vol.Optional(CONF_SERVICE_SCRIPTS, default={}): {cv.string: cv.SCRIPT_SCHEMA},
        vol.Optional(CONF_SOUND_MODE_SCRIPTS, default={}): {
            cv.string: cv.SCRIPT_SCHEMA
        },
        vol.Optional(CONF_SOURCE_SCRIPTS, default={}): {cv.string: cv.SCRIPT_SCHEMA},
    }
)

PLATFORM_SCHEMA = MEDIA_PLAYER_PLATFORM_SCHEMA.extend(
    {vol.Required(CONF_MEDIA_PLAYERS): cv.schema_with_slug_keys(MEDIA_PLAYER_SCHEMA)}
)


async def async_setup_platform(
    hass: HomeAssistant,
    config: ConfigType,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the template media players."""
    media_player_configs: dict[str, ConfigType] = config[CONF_MEDIA_PLAYERS]
    media_players: list[TemplateMediaPlayer] = []

    for media_player_name, media_player_config in media_player_configs.items():
        media_players.append(
            TemplateMediaPlayer(hass, media_player_config, media_player_name)
        )

    async_add_entities(media_players)


class TemplateMediaPlayer(TemplateEntity, MediaPlayerEntity):
    """Representation of a Template Media player."""

    def __init__(
        self,
        hass: HomeAssistant,
        config: ConfigType,
        name: str,
    ) -> None:
        """Initialize the Template Media player."""
        unique_id: str | None = config.get(CONF_UNIQUE_ID, name)
        TemplateEntity.__init__(self, hass, config, unique_id)

        self._attr_device_class = config.get(CONF_DEVICE_CLASS)
        self._attr_should_poll = False

        self._base_media_player_entity_id: str | None = config.get(
            CONF_BASE_MEDIA_PLAYER_ENTITY_ID
        )
        self._search_media_entity_id: str | None = config.get(
            CONF_SEARCH_MEDIA_ENTITY_ID
        )
        self._browse_media_entity_id: str | None = config.get(
            CONF_BROWSE_MEDIA_ENTITY_ID
        )
        self._global_template: Template | None = config.get(CONF_GLOBAL_TEMPLATE)
        self._state_template: Template | None = config.get(CONF_STATE)
        self._attribute_templates: dict[str, Template] = cast(
            dict[str, Template], config.get(CONF_ATTRIBUTES)
        )

        self._service_scripts = {
            service: Script(hass, service_script, name, MEDIA_PLAYER_DOMAIN)
            for service, service_script in cast(
                dict[str, Sequence[dict[str, Any]]], config.get(CONF_SERVICE_SCRIPTS)
            ).items()
        }
        self._source_scripts = {
            source: Script(hass, source_script, name, MEDIA_PLAYER_DOMAIN)
            for source, source_script in cast(
                dict[str, Sequence[dict[str, Any]]], config.get(CONF_SOURCE_SCRIPTS)
            ).items()
        }
        self._sound_mode_scripts = {
            sound_mode: Script(hass, sound_mode_script, name, MEDIA_PLAYER_DOMAIN)
            for sound_mode, sound_mode_script in cast(
                dict[str, Sequence[dict[str, Any]]], config.get(CONF_SOUND_MODE_SCRIPTS)
            ).items()
        }

        self._state: MediaPlayerState | None = None

        for template in [
            self._state_template,
            self._availability_template,
            self._icon_template,
            self._friendly_name_template,
            self._entity_picture_template,
        ] + (
            list(self._attribute_templates.values())
            if self._attribute_templates
            else []
        ):
            if template is None or not isinstance(template, Template):
                continue

            if self._global_template is not None:
                template.template = self._global_template.template + template.template

    async def _async_run_script_with_result(
        self, script: Script, variables: dict[str, Any] | None = None
    ) -> ScriptRunResult | None:
        """Run a script with variables."""
        script_vars = {
            **self._render_script_variables(),
            **(variables or {}),
        }
        return await script.async_run(script_vars, context=self._context)

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
        if self._state_template is not None:
            self.add_template_attribute(
                "_state", self._state_template, None, self._update_state
            )
        await super().async_added_to_hass()

    @property
    def _base_media_player_entity(self) -> MediaPlayerEntity | None:
        if self._base_media_player_entity_id:
            component: EntityComponent[MediaPlayerEntity] = self.hass.data[
                MEDIA_PLAYER_DOMAIN
            ]
            if entity := component.get_entity(self._base_media_player_entity_id):
                return entity
        return None

    @property
    def _browse_media_entity(self) -> MediaPlayerEntity | None:
        if self._browse_media_entity_id:
            component: EntityComponent[MediaPlayerEntity] = self.hass.data[
                MEDIA_PLAYER_DOMAIN
            ]
            if entity := component.get_entity(self._browse_media_entity_id):
                return entity
        return None

    @property
    def _search_media_entity(self) -> MediaPlayerEntity | None:
        if self._search_media_entity_id:
            component: EntityComponent[MediaPlayerEntity] = self.hass.data[
                MEDIA_PLAYER_DOMAIN
            ]
            if entity := component.get_entity(self._search_media_entity_id):
                return entity
        return None

    @callback
    def _update_state(self, result: str | TemplateError) -> None:
        super()._update_state(result)

        if isinstance(result, TemplateError):
            _LOGGER.error("Could not render state template: %s", result)
            self._state = None
            return

        try:
            state = MediaPlayerState(result)
            self._state = state
        except ValueError:
            _LOGGER.error("Received invalid state: %s", result)
            self._state = None

    def add_template_attribute(
        self,
        attribute: str,
        template: Template,
        validator: Callable[[Any], Any] | None = None,
        on_update: Callable[[Any], None] | None = None,
        none_on_template_error: bool = False,
    ) -> None:
        """Create a template tracker for the attribute."""
        if not template:
            return

        template = Template(
            "{% set attribute = '" + attribute + "' %}" + template.template, self.hass
        )

        super().add_template_attribute(
            attribute,
            template,
            validator,
            on_update,
            none_on_template_error,
        )

    @property
    def device_class(self) -> MediaPlayerDeviceClass | None:
        """Return the class of this device."""
        device_class = super().device_class

        if not device_class and self._base_media_player_entity:
            return self._base_media_player_entity.device_class

        return device_class

    @property
    def supported_features(self) -> MediaPlayerEntityFeature:
        """Flag media player features that are supported."""
        support = MediaPlayerEntityFeature(0)

        if self._base_media_player_entity:
            support |= self._base_media_player_entity.supported_features

        if CONF_MEDIA_PAUSE_SCRIPT in self._service_scripts:
            support |= MediaPlayerEntityFeature.PAUSE
        if CONF_MEDIA_SEEK_SCRIPT in self._service_scripts:
            support |= MediaPlayerEntityFeature.SEEK
        if CONF_VOLUME_SET_SCRIPT in self._service_scripts:
            support |= MediaPlayerEntityFeature.VOLUME_SET
        if CONF_VOLUME_MUTE_SCRIPT in self._service_scripts:
            support |= MediaPlayerEntityFeature.VOLUME_MUTE
        if CONF_MEDIA_PREVIOUS_TRACK_SCRIPT in self._service_scripts:
            support |= MediaPlayerEntityFeature.PREVIOUS_TRACK
        if CONF_MEDIA_NEXT_TRACK_SCRIPT in self._service_scripts:
            support |= MediaPlayerEntityFeature.NEXT_TRACK
        if CONF_TURN_ON_SCRIPT in self._service_scripts:
            support |= MediaPlayerEntityFeature.TURN_ON
        if CONF_TURN_OFF_SCRIPT in self._service_scripts:
            support |= MediaPlayerEntityFeature.TURN_OFF
        if CONF_PLAY_MEDIA_SCRIPT in self._service_scripts or self._browse_media_entity:
            support |= MediaPlayerEntityFeature.PLAY_MEDIA
        if (
            CONF_VOLUME_UP_SCRIPT in self._service_scripts
            and CONF_VOLUME_DOWN_SCRIPT in self._service_scripts
        ):
            support |= MediaPlayerEntityFeature.VOLUME_STEP
        if len(self.source_list or []) > 0:
            support |= MediaPlayerEntityFeature.SELECT_SOURCE
        if CONF_MEDIA_STOP_SCRIPT in self._service_scripts:
            support |= MediaPlayerEntityFeature.STOP
        if CONF_CLEAR_PLAYLIST_SCRIPT in self._service_scripts:
            support |= MediaPlayerEntityFeature.CLEAR_PLAYLIST
        if CONF_MEDIA_PLAY_SCRIPT in self._service_scripts:
            support |= MediaPlayerEntityFeature.PLAY
        if CONF_SHUFFLE_SET_SCRIPT in self._service_scripts:
            support |= MediaPlayerEntityFeature.SHUFFLE_SET
        if self.sound_mode_list:
            support |= MediaPlayerEntityFeature.SELECT_SOUND_MODE
        if self._browse_media_entity_id:
            support |= MediaPlayerEntityFeature.BROWSE_MEDIA
        if CONF_REPEAT_SET_SCRIPT in self._service_scripts:
            support |= MediaPlayerEntityFeature.REPEAT_SET
        if (
            CONF_JOIN_SCRIPT in self._service_scripts
            and CONF_UNJOIN_SCRIPT in self._service_scripts
        ):
            support |= MediaPlayerEntityFeature.GROUPING
        if (
            self._search_media_entity_id is not None
            or CONF_SEARCH_MEDIA_SCRIPT in self._service_scripts
        ):
            support |= MediaPlayerEntityFeature.SEARCH_MEDIA
        if (
            self._browse_media_entity_id is not None
            or CONF_BROWSE_MEDIA_SCRIPT in self._service_scripts
        ):
            support |= MediaPlayerEntityFeature.BROWSE_MEDIA

        return support

    @property
    def state(self) -> MediaPlayerState | None:
        """State of the player."""
        if self._state_template:
            return self._state

        if self._base_media_player_entity:
            return self._base_media_player_entity.state

        return None

    @property
    def source_list(self) -> list[str]:
        """List of available input sources."""
        if self._source_scripts:
            return list(self._source_scripts.keys())

        if self._base_media_player_entity:
            return self._base_media_player_entity.source_list or []

        return []

    @property
    def sound_mode_list(self) -> list[str]:
        """List of available sound modes."""
        if self._sound_mode_scripts:
            return list(self._sound_mode_scripts.keys())

        if self._base_media_player_entity:
            return self._base_media_player_entity.sound_mode_list or []

        return []

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        if CONF_MEDIA_NEXT_TRACK_SCRIPT in self._service_scripts and (
            script := self._service_scripts.get(CONF_MEDIA_NEXT_TRACK_SCRIPT)
        ):
            await self._async_run_script_with_result(script)

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_media_next_track()

    async def async_media_pause(self) -> None:
        """Send pause command."""
        if CONF_MEDIA_PAUSE_SCRIPT in self._service_scripts and (
            script := self._service_scripts.get(CONF_MEDIA_PAUSE_SCRIPT)
        ):
            await self._async_run_script_with_result(script)

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_media_pause()

    async def async_media_play(self) -> None:
        """Send play command."""
        if CONF_MEDIA_PLAY_SCRIPT in self._service_scripts and (
            script := self._service_scripts.get(CONF_MEDIA_PLAY_SCRIPT)
        ):
            await self._async_run_script_with_result(script)

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_media_play()

    async def async_media_play_pause(self) -> None:
        """Play or pause the media player."""
        if CONF_MEDIA_PLAY_PAUSE_SCRIPT in self._service_scripts and (
            script := self._service_scripts.get(CONF_MEDIA_PLAY_PAUSE_SCRIPT)
        ):
            await self._async_run_script_with_result(script)

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_media_play_pause()

    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        if CONF_MEDIA_PREVIOUS_TRACK_SCRIPT in self._service_scripts and (
            script := self._service_scripts.get(CONF_MEDIA_PREVIOUS_TRACK_SCRIPT)
        ):
            await self._async_run_script_with_result(script)

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_media_previous_track()

    async def async_media_seek(self, position: float) -> None:
        """Send seek command."""
        if CONF_MEDIA_SEEK_SCRIPT in self._service_scripts and (
            script := self._service_scripts.get(CONF_MEDIA_SEEK_SCRIPT)
        ):
            await self._async_run_script_with_result(
                script,
                {"position": position},
            )

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_media_seek(position)

    async def async_media_stop(self) -> None:
        """Send stop command."""
        if CONF_MEDIA_STOP_SCRIPT in self._service_scripts and (
            script := self._service_scripts.get(CONF_MEDIA_STOP_SCRIPT)
        ):
            await self._async_run_script_with_result(script)

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_media_stop()

    async def async_set_repeat(self, repeat: RepeatMode) -> None:
        """Set repeat mode."""
        if CONF_REPEAT_SET_SCRIPT in self._service_scripts and (
            script := self._service_scripts.get(CONF_REPEAT_SET_SCRIPT)
        ):
            await self._async_run_script_with_result(
                script,
                {"repeat": repeat},
            )

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_set_repeat(repeat)

    async def async_set_shuffle(self, shuffle: bool) -> None:
        """Enable/disable shuffle mode."""
        if CONF_SHUFFLE_SET_SCRIPT in self._service_scripts and (
            script := self._service_scripts.get(CONF_SHUFFLE_SET_SCRIPT)
        ):
            await self._async_run_script_with_result(
                script,
                {"shuffle": shuffle},
            )

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_set_shuffle(shuffle)

    async def async_toggle(self) -> None:
        """Toggle the power on the media player."""
        if CONF_TOGGLE_SCRIPT in self._service_scripts and (
            script := self._service_scripts.get(CONF_TOGGLE_SCRIPT)
        ):
            await self._async_run_script_with_result(script)

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_toggle()

    async def async_turn_off(self) -> None:
        """Turn the media player off."""
        if CONF_TURN_OFF_SCRIPT in self._service_scripts and (
            script := self._service_scripts.get(CONF_TURN_OFF_SCRIPT)
        ):
            await self._async_run_script_with_result(script)

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_turn_off()

    async def async_turn_on(self) -> None:
        """Turn the media player on."""
        if CONF_TURN_ON_SCRIPT in self._service_scripts and (
            script := self._service_scripts.get(CONF_TURN_ON_SCRIPT)
        ):
            await self._async_run_script_with_result(script)

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_turn_on()

    async def async_volume_down(self) -> None:
        """Turn volume down for media player."""
        if CONF_VOLUME_DOWN_SCRIPT in self._service_scripts and (
            script := self._service_scripts.get(CONF_VOLUME_DOWN_SCRIPT)
        ):
            await self._async_run_script_with_result(script)

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_volume_down()

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        if CONF_VOLUME_MUTE_SCRIPT in self._service_scripts and (
            script := self._service_scripts.get(CONF_VOLUME_MUTE_SCRIPT)
        ):
            await self._async_run_script_with_result(
                script,
                {"mute": mute},
            )

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_mute_volume(mute)

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        if CONF_VOLUME_SET_SCRIPT in self._service_scripts and (
            script := self._service_scripts.get(CONF_VOLUME_SET_SCRIPT)
        ):
            await self._async_run_script_with_result(
                script,
                {"volume": volume},
            )

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_set_volume_level(volume)

    async def async_volume_up(self) -> None:
        """Turn volume up for media player."""
        if CONF_VOLUME_UP_SCRIPT in self._service_scripts and (
            script := self._service_scripts.get(CONF_VOLUME_UP_SCRIPT)
        ):
            await self._async_run_script_with_result(script)

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_volume_up()

    async def async_clear_playlist(self) -> None:
        """Clear players playlist."""
        if CONF_CLEAR_PLAYLIST_SCRIPT in self._service_scripts and (
            script := self._service_scripts.get(CONF_CLEAR_PLAYLIST_SCRIPT)
        ):
            await self._async_run_script_with_result(script)

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_clear_playlist()

    async def async_join_players(self, group_members: list[str]) -> None:
        """Join `group_members` as a player group with the current player."""
        if CONF_JOIN_SCRIPT in self._service_scripts and (
            script := self._service_scripts.get(CONF_JOIN_SCRIPT)
        ):
            await self._async_run_script_with_result(
                script,
                {"group_members": group_members},
            )

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_join_players(group_members)

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs: dict[str, Any]
    ) -> None:
        """Play a piece of media."""
        if CONF_PLAY_MEDIA_SCRIPT in self._service_scripts and (
            script := self._service_scripts.get(CONF_PLAY_MEDIA_SCRIPT)
        ):
            if is_media_source_id(media_id):
                media_type = MediaType.MUSIC
                play_item = await async_resolve_media(
                    self.hass, media_id, self.entity_id
                )
                media_id = async_process_play_media_url(self.hass, play_item.url)

            await self._async_run_script_with_result(
                script,
                {"media_type": media_type, "media_id": media_id},
            )

        elif self._browse_media_entity:
            await self._browse_media_entity.async_play_media(
                media_type, media_id, **kwargs
            )

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_play_media(
                media_type, media_id, **kwargs
            )

    async def async_select_sound_mode(self, sound_mode: str) -> None:
        """Select sound mode."""
        if sound_mode not in self.sound_mode_list:
            return

        if script := self._sound_mode_scripts.get(sound_mode):
            await self._async_run_script_with_result(script)

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_select_sound_mode(sound_mode)

    async def async_select_source(self, source: str) -> None:
        """Select input source."""
        if source not in self.source_list:
            return

        if script := self._source_scripts.get(source):
            await self._async_run_script_with_result(script)

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_select_source(source)

    async def async_unjoin_player(self) -> None:
        """Remove this player from any group."""
        if script := self._service_scripts.get(CONF_UNJOIN_SCRIPT):
            await self._async_run_script_with_result(script)

        elif self._base_media_player_entity:
            await self._base_media_player_entity.async_unjoin_player()

    async def async_browse_media(
        self,
        media_content_type: MediaType | str | None = None,
        media_content_id: str | None = None,
    ) -> BrowseMedia:
        """Return a BrowseMedia instance.

        The BrowseMedia instance will be used by the
        "media_player/browse_media" websocket command.
        """
        if script := self._service_scripts.get(CONF_BROWSE_MEDIA_SCRIPT):
            result = await self._async_run_script_with_result(
                script,
                {
                    "media_content_type": media_content_type,
                    "media_content_id": media_content_id,
                },
            )

            if not result:
                raise HomeAssistantError("Browse media script did not return any data.")

            result_data = result.service_response
            if not isinstance(result_data, dict):
                raise HomeAssistantError(
                    "Search media script did not return a dictionary."
                )

            return self._build_browse_media(result_data)

        if self._browse_media_entity:
            return await self._browse_media_entity.async_browse_media(
                media_content_type, media_content_id
            )

        if self._base_media_player_entity:
            return await self._base_media_player_entity.async_browse_media(
                media_content_type, media_content_id
            )

        raise HomeAssistantError(
            "No browse media entity configured for this template media player."
        )

    async def async_search_media(
        self,
        query: SearchMediaQuery,
    ) -> SearchMedia:
        """Search the media player."""
        if script := self._service_scripts.get(CONF_SEARCH_MEDIA_SCRIPT):
            result = await self._async_run_script_with_result(
                script,
                {
                    "media_content_type": query.media_content_type,
                    "media_content_id": query.media_content_id,
                    "search_query": query.search_query,
                    "media_filter_classes": query.media_filter_classes,
                },
            )

            if not result:
                return SearchMedia(result=[])

            result_data = result.service_response
            if not isinstance(result_data, dict):
                raise HomeAssistantError(
                    "Search media script did not return a dictionary."
                )

            result_media = result_data.get("media", [])
            if not isinstance(result_media, list):
                raise HomeAssistantError(
                    "Search media script did not return a list of media items."
                )

            browse_media_entries: list[BrowseMedia] = []
            for result_media_entry in result_media:
                if not isinstance(result_media_entry, dict):
                    raise HomeAssistantError(
                        "Search media script returned media items with invalid structure."
                    )

                browse_media_entry = self._build_browse_media(result_media_entry)
                browse_media_entries.append(browse_media_entry)

            return SearchMedia(
                result=browse_media_entries,
            )

        if self._search_media_entity:
            return await self._search_media_entity.async_search_media(query)

        if self._base_media_player_entity:
            return await self._base_media_player_entity.async_search_media(query)

        raise HomeAssistantError(
            "No search media entity configured for this template media player."
        )

    def _build_browse_media(
        self,
        item: dict[str, Any],
    ) -> BrowseMedia:
        required_attributes = {
            "media_class",
            "media_content_id",
            "media_content_type",
            "title",
            "can_play",
            "can_expand",
        }

        if any(
            required_attribute not in item for required_attribute in required_attributes
        ):
            raise HomeAssistantError(
                f"Could not build BrowseMedia, missing required attributes in: {item}"
            )

        children: list[BrowseMedia] = []
        if child_items := item.get("children"):
            for child_item in child_items:
                if not isinstance(child_item, dict):
                    raise HomeAssistantError(
                        "Could not build BrowseMedia, child items must be dictionaries."
                    )
                child = self._build_browse_media(child_item)
                children.append(child)

        return BrowseMedia(
            media_class=item["media_class"],
            media_content_id=item["media_content_id"],
            media_content_type=item["media_content_type"],
            title=item["title"],
            can_play=item["can_play"],
            can_expand=item["can_expand"],
            children=children,
            children_media_class=item.get("children_media_class"),
            thumbnail=item.get("thumbnail"),
            not_shown=item.get("not_shown", 0),
            can_search=item.get("can_search", False),
        )
