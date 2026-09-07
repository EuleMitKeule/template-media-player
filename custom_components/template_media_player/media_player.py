"""Template Media Player Component for Home Assistant."""

import importlib
import inspect
import json
import logging
from collections.abc import Callable, Sequence
from functools import partial
from typing import Any, cast

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.media_player import (
    DOMAIN as MEDIA_PLAYER_DOMAIN,
    PLATFORM_SCHEMA as MEDIA_PLAYER_PLATFORM_SCHEMA,
    BrowseMedia,
    MediaClass,
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
    async_browse_media as ms_async_browse_media,
    async_resolve_media,
    is_media_source_id,
)
from homeassistant.components.template.template_entity import TemplateEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError, TemplateError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.entity_component import EntityComponent
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.network import is_internal_request
from homeassistant.helpers.script import Script, ScriptRunResult, Template
from homeassistant.helpers.typing import ConfigType, DiscoveryInfoType

from .const import (
    BROWSE_PAYLOAD_PREFIX,
    CONF_ATTRIBUTES,
    CONF_AVAILABILITY,
    CONF_BASE_MEDIA_PLAYER_ENTITY_ID,
    CONF_BROWSE_MEDIA_ENTITY_ID,
    CONF_BROWSE_MEDIA_SCRIPT,
    CONF_BROWSE_MEDIA_SOURCES,
    CONF_CLEAR_PLAYLIST_SCRIPT,
    CONF_DEVICE_CLASS,
    CONF_DOMAIN,
    CONF_ENTITY_ID,
    CONF_GLOBAL_TEMPLATE,
    CONF_ICON,
    CONF_JOIN_SCRIPT,
    CONF_MEDIA_CONTENT_ID,
    CONF_MEDIA_CONTENT_TYPE,
    CONF_MEDIA_NEXT_TRACK_SCRIPT,
    CONF_MEDIA_PAUSE_SCRIPT,
    CONF_MEDIA_PLAY_PAUSE_SCRIPT,
    CONF_MEDIA_PLAY_SCRIPT,
    CONF_MEDIA_PLAYERS,
    CONF_MEDIA_PREVIOUS_TRACK_SCRIPT,
    CONF_MEDIA_SEEK_SCRIPT,
    CONF_MEDIA_SOURCE,
    CONF_MEDIA_STOP_SCRIPT,
    CONF_NAME,
    CONF_PICTURE,
    CONF_PLAY_ENTITY_ID,
    CONF_PLAY_MEDIA_SCRIPT,
    CONF_REPEAT_SET_SCRIPT,
    CONF_SEARCH_MEDIA_ENTITY_ID,
    CONF_SEARCH_MEDIA_SCRIPT,
    CONF_SERVICE_SCRIPTS,
    CONF_SHUFFLE_SET_SCRIPT,
    CONF_SOUND_MODE_SCRIPTS,
    CONF_SOURCE,
    CONF_SOURCE_SCRIPTS,
    CONF_STATE,
    CONF_THUMBNAIL,
    CONF_TITLE,
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

BRAND_ICON_URL = "/api/brands/integration/{domain}/icon.png"


def _validate_browse_media_source(value: dict[str, Any]) -> dict[str, Any]:
    if not value.get(CONF_ENTITY_ID) and not value.get(CONF_MEDIA_SOURCE):
        raise vol.Invalid("browse_media_sources entry needs entity_id or media_source")
    return value


BROWSE_MEDIA_SOURCE_SCHEMA = vol.All(
    vol.Schema(
        {
            vol.Optional(CONF_ENTITY_ID): cv.entity_id,
            vol.Optional(CONF_PLAY_ENTITY_ID): cv.template,
            vol.Optional(CONF_MEDIA_SOURCE): cv.string,
            vol.Optional(CONF_MEDIA_CONTENT_ID): cv.string,
            vol.Optional(CONF_MEDIA_CONTENT_TYPE): cv.string,
            vol.Optional(CONF_SOURCE): cv.string,
            vol.Optional(CONF_THUMBNAIL): cv.string,
            vol.Optional(CONF_TITLE): cv.string,
            vol.Optional(CONF_DOMAIN): cv.string,
        }
    ),
    _validate_browse_media_source,
)

MEDIA_PLAYER_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_NAME): cv.template,
        vol.Optional(CONF_UNIQUE_ID): cv.string,
        vol.Optional(CONF_ICON): cv.template,
        vol.Optional(CONF_PICTURE): cv.template,
        vol.Optional(CONF_VARIABLES): cv.SCRIPT_VARIABLES_SCHEMA,
        vol.Optional(CONF_ATTRIBUTES): vol.Schema({cv.string: cv.template}),
        vol.Optional(CONF_DEVICE_CLASS): cv.string,
        vol.Optional(CONF_GLOBAL_TEMPLATE): cv.template,
        vol.Optional(CONF_STATE): cv.template,
        vol.Optional(CONF_AVAILABILITY): cv.template,
        vol.Optional(CONF_BASE_MEDIA_PLAYER_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_BROWSE_MEDIA_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_SEARCH_MEDIA_ENTITY_ID): cv.entity_id,
        vol.Optional(CONF_BROWSE_MEDIA_SOURCES): {
            cv.string: BROWSE_MEDIA_SOURCE_SCHEMA
        },
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
        global_template = config.get(CONF_GLOBAL_TEMPLATE)
        prefix = (
            global_template.template
            if isinstance(global_template, Template)
            else ""
        )
        name_template = config.get(CONF_NAME)
        static_name = name.replace("_", " ").title()
        name_has_template = False
        if isinstance(name_template, Template):
            name_src = name_template.template.strip()
            name_has_template = "{{" in name_src or "{%" in name_src
            if not name_has_template and name_src:
                static_name = name_src
        elif isinstance(name_template, str) and name_template:
            static_name = name_template
        if prefix:
            for key in (
                CONF_STATE,
                CONF_AVAILABILITY,
                CONF_ICON,
                CONF_PICTURE,
            ):
                tmpl = config.get(key)
                if isinstance(tmpl, Template):
                    tmpl.template = prefix + tmpl.template
            # Keep static names unprefixed so HA does not show the global
            # template source as the entity title. Templated names still get
            # the prefix, matching the original global_template behaviour.
            if name_has_template and isinstance(name_template, Template):
                name_template.template = prefix + name_template.template
            for tmpl in (config.get(CONF_ATTRIBUTES) or {}).values():
                if isinstance(tmpl, Template):
                    tmpl.template = prefix + tmpl.template

        TemplateEntity.__init__(self, hass, config, unique_id)
        if not name_has_template:
            self._attr_name = static_name

        self._availability_template: Template | None = config.get(CONF_AVAILABILITY)
        self._icon_template: Template | None = config.get(CONF_ICON)
        self._friendly_name_template: Template | None = config.get(CONF_NAME)
        self._entity_picture_template: Template | None = config.get(CONF_PICTURE)

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
        self._browse_media_sources: dict[str, dict[str, Any]] = (
            config.get(CONF_BROWSE_MEDIA_SOURCES) or {}
        )
        self._global_template: Template | None = global_template
        self._state_template: Template | None = config.get(CONF_STATE)
        self._attribute_templates: dict[str, Template] = config.get(CONF_ATTRIBUTES)

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

    def _script_run_variables(
        self, extra: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Merge configured template variables with per-service script variables."""
        rendered: dict[str, Any] = {}
        render = getattr(self, "_render_script_variables", None)
        if callable(render):
            value = render() or {}
            if isinstance(value, dict):
                rendered = dict(value)
        if extra:
            rendered.update(extra)
        return rendered

    async def _async_run_script(
        self, script: Script, extra: dict[str, Any] | None = None
    ) -> ScriptRunResult | None:
        """Run a service/source/sound-mode script with entity variables available."""
        return await script.async_run(
            self._script_run_variables(extra), context=self._context
        )

    async def async_added_to_hass(self) -> None:
        """Register callbacks."""
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

    def _media_player_entity(self, entity_id: str | None) -> MediaPlayerEntity | None:
        if not entity_id:
            return None
        component: EntityComponent[MediaPlayerEntity] = self.hass.data[
            MEDIA_PLAYER_DOMAIN
        ]
        return component.get_entity(entity_id)

    def _template_extra_attr(self, key: str) -> Any:
        extra = getattr(self, "_attr_extra_state_attributes", None) or {}
        value = extra.get(key)
        if value in (None, "", "None", "none"):
            return None
        return value

    def _usable_picture_url(self, value: Any) -> str | None:
        if not isinstance(value, str):
            return None
        value = value.strip()
        if not value or value.lower() in {"none", "null", "unknown"}:
            return None
        if value.startswith(("/", "http://", "https://")):
            return value
        return None

    def _declared_player_id(self) -> str | None:
        """Return extra attribute `player` when it is a media_player entity id."""
        player_id = self._template_extra_attr("player")
        if isinstance(player_id, str):
            player_id = player_id.strip()
            if player_id.startswith("media_player."):
                return player_id
        return None

    def _active_media_player(self) -> MediaPlayerEntity | None:
        if entity := self._media_player_entity(self._declared_player_id()):
            return entity
        return None

    def _child_picture_url(self) -> str | None:
        entity_id = self._declared_player_id()
        if not entity_id:
            return None
        if state := self.hass.states.get(entity_id):
            for key in ("entity_picture_local", "entity_picture"):
                if url := self._usable_picture_url(state.attributes.get(key)):
                    return url
        if player := self._active_media_player():
            if url := self._usable_picture_url(player.entity_picture):
                return url
            if url := self._usable_picture_url(player.media_image_url):
                return url
        return self._usable_picture_url(self._template_extra_attr("entity_picture"))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        extra = dict(super().extra_state_attributes or {})
        if not self._declared_player_id():
            return extra
        for key in ("entity_picture", "entity_picture_local", "media_image_url"):
            if not self._usable_picture_url(extra.get(key)):
                extra.pop(key, None)
        # The more-info dialog prefers entity_picture_local. A blank/invalid
        # value hides a working entity_picture, so only keep real URLs.
        if picture := self._child_picture_url():
            extra["entity_picture"] = picture
        extra.pop("entity_picture_local", None)
        return extra

    @property
    def media_image_url(self) -> str | None:
        if self._declared_player_id():
            if player := self._active_media_player():
                if url := player.media_image_url:
                    return url
            return self._child_picture_url()
        return super().media_image_url

    @property
    def media_image_remotely_accessible(self) -> bool:
        if self._declared_player_id():
            # Avoid injecting this entity's own proxy URL as
            # entity_picture_local; the more-info dialog prefers that field.
            return False
        return super().media_image_remotely_accessible

    @property
    def media_image_hash(self) -> str | None:
        if self._declared_player_id():
            if player := self._active_media_player():
                if image_hash := player.media_image_hash:
                    return image_hash
            if self.media_image_url:
                return super().media_image_hash
            return None
        return super().media_image_hash

    @property
    def entity_picture(self) -> str | None:
        """Return album art, preferring the declared child player when set."""
        if self._declared_player_id():
            if picture := self._child_picture_url():
                return picture
        return super().entity_picture

    async def async_get_media_image(self) -> tuple[bytes | None, str | None]:
        if self._declared_player_id():
            if player := self._active_media_player():
                return await player.async_get_media_image()
            if url := self._child_picture_url():
                return await self._async_fetch_image_from_cache(url)
            return None, None
        return await super().async_get_media_image()

    def _browse_source_domain(self, source_config: dict[str, Any]) -> str | None:
        if domain := source_config.get(CONF_DOMAIN):
            return domain
        if media_source := source_config.get(CONF_MEDIA_SOURCE):
            return media_source
        entity_id = source_config.get(CONF_ENTITY_ID)
        if not entity_id:
            return None
        entry = er.async_get(self.hass).async_get(entity_id)
        if entry and entry.platform:
            return entry.platform
        entity = self._media_player_entity(entity_id)
        if entity and entity.platform:
            return entity.platform.platform_name
        return None

    def _browse_source_thumbnail(self, source_config: dict[str, Any]) -> str | None:
        if thumbnail := source_config.get(CONF_THUMBNAIL):
            return thumbnail
        if domain := self._browse_source_domain(source_config):
            return BRAND_ICON_URL.format(domain=domain)
        return None

    def _encode_browse_id(
        self,
        source_key: str,
        media_content_type: str | None = None,
        media_content_id: str | None = None,
    ) -> str:
        payload: dict[str, Any] = {"s": source_key}
        if media_content_id:
            payload["t"] = media_content_type
            payload["i"] = media_content_id
        return BROWSE_PAYLOAD_PREFIX + json.dumps(payload, separators=(",", ":"))

    def _decode_browse_id(
        self, media_content_id: str | None
    ) -> tuple[str, str | None, str | None] | None:
        if not media_content_id or not media_content_id.startswith(BROWSE_PAYLOAD_PREFIX):
            return None
        try:
            payload = json.loads(media_content_id[len(BROWSE_PAYLOAD_PREFIX) :])
        except json.JSONDecodeError:
            return None
        source_key = payload.get("s")
        if not source_key:
            return None
        return source_key, payload.get("t"), payload.get("i")

    def _wrap_browse_item(self, source_key: str, item: BrowseMedia) -> BrowseMedia:
        item.media_content_id = self._encode_browse_id(
            source_key, item.media_content_type, item.media_content_id
        )
        if item.children:
            for child in item.children:
                self._wrap_browse_item(source_key, child)
        return item

    def _media_source_domain(self, media_id: str) -> str | None:
        if not is_media_source_id(media_id):
            return None
        remainder = media_id.split("://", 1)[1]
        return remainder.split("/", 1)[0] or None

    def _source_for_media_source_domain(
        self, domain: str
    ) -> tuple[str, dict[str, Any]] | None:
        for key, source_config in self._browse_media_sources.items():
            source_domain = self._browse_source_domain(source_config)
            media_source = source_config.get(CONF_MEDIA_SOURCE)
            if domain in {source_domain, media_source}:
                return key, source_config
        return None

    def _rendered_play_entity_id(self, source_config: dict[str, Any]) -> str | None:
        play = source_config.get(CONF_PLAY_ENTITY_ID)
        if play is not None:
            if isinstance(play, Template):
                play.hass = self.hass
                try:
                    rendered = play.async_render(
                        self._script_run_variables(), parse_result=False
                    )
                except TemplateError:
                    rendered = None
                if rendered not in (None, "None", ""):
                    return str(rendered).strip()
            elif play:
                return str(play)
        return source_config.get(CONF_ENTITY_ID)

    def _normalize_play_media_id(self, entity: MediaPlayerEntity, media_id: str) -> str:
        platform = ""
        if entity.platform:
            platform = entity.platform.platform_name
        if platform == "spotify" and media_id.startswith("spotify://"):
            rest = media_id[len("spotify://") :]
            kind, _, ident = rest.partition("/")
            if kind and ident:
                return f"spotify:{kind}:{ident}"
        return media_id

    def _browse_source_for_item(self, item: BrowseMedia) -> str | None:
        media_id = item.media_content_id or ""
        media_type = str(item.media_content_type or "").lower()
        if domain := self._media_source_domain(media_id):
            if matched := self._source_for_media_source_domain(domain):
                return matched[0]

        radio_key = None
        spotify_key = None
        plex_key = None
        for key, source_config in self._browse_media_sources.items():
            domain = self._browse_source_domain(source_config) or ""
            media_source = source_config.get(CONF_MEDIA_SOURCE) or ""
            start_id = source_config.get(CONF_MEDIA_CONTENT_ID) or ""
            if domain == "plex":
                plex_key = key
            if domain in {"spotify"} or media_source == "spotify":
                spotify_key = key
            if (
                start_id == "radio"
                or media_source == "radio_browser"
                or domain in {"radio_browser", "radio"}
            ):
                radio_key = key

        lowered = media_id.lower()
        if (
            media_type == "radio"
            or "radio" in lowered
            or lowered.startswith("radio://")
        ):
            return radio_key or spotify_key
        if lowered.startswith(("spotify:", "spotify://")):
            return spotify_key
        if lowered.startswith(("plex:", "plex://")):
            return plex_key
        if lowered.startswith("library://"):
            return spotify_key or radio_key
        return spotify_key or radio_key

    async def _async_play_on_source(
        self,
        source_config: dict[str, Any],
        media_type: MediaType | str,
        media_id: str,
        **kwargs: Any,
    ) -> None:
        if (source := source_config.get(CONF_SOURCE)) and source in self.source_list:
            await self.async_select_source(source)
        entity = self._media_player_entity(self._rendered_play_entity_id(source_config))
        if entity is None:
            raise HomeAssistantError(
                "No playable entity configured for this browse media source."
            )
        if is_media_source_id(media_id):
            play_item = await async_resolve_media(
                self.hass, media_id, entity.entity_id
            )
            media_id = async_process_play_media_url(self.hass, play_item.url)
            media_type = MediaType.MUSIC
        media_id = self._normalize_play_media_id(entity, media_id)
        await entity.async_play_media(media_type, media_id, **kwargs)

    async def _async_browse_via_integration(
        self,
        domain: str,
        media_content_type: MediaType | str | None,
        media_content_id: str | None,
    ) -> BrowseMedia | None:
        """Browse via the integration media_browser module when no live entity exists."""
        try:
            module = importlib.import_module(
                f"homeassistant.components.{domain}.media_browser"
            )
        except ImportError:
            return None

        browse_fn = getattr(module, "async_browse_media", None) or getattr(
            module, "browse_media", None
        )
        if browse_fn is None:
            return None

        kwargs: dict[str, Any] = {}
        for name in inspect.signature(browse_fn).parameters:
            if name in ("self", "cls"):
                continue
            if name == "hass":
                kwargs[name] = self.hass
            elif name in ("is_internal", "internal"):
                kwargs[name] = is_internal_request(self.hass)
            elif name == "media_content_type":
                kwargs[name] = media_content_type
            elif name == "media_content_id":
                kwargs[name] = media_content_id

        try:
            if inspect.iscoroutinefunction(browse_fn):
                return await browse_fn(**kwargs)
            return await self.hass.async_add_executor_job(
                partial(browse_fn, **kwargs)
            )
        except HomeAssistantError:
            raise
        except Exception as err:
            raise HomeAssistantError(str(err)) from err

    async def _async_browse_source(
        self,
        source_key: str,
        media_content_type: MediaType | str | None,
        media_content_id: str | None,
    ) -> BrowseMedia:
        source_config = self._browse_media_sources[source_key]
        entity = self._media_player_entity(source_config.get(CONF_ENTITY_ID))
        media_source = source_config.get(CONF_MEDIA_SOURCE)
        errors: list[str] = []
        start_id = source_config.get(CONF_MEDIA_CONTENT_ID)
        start_type = source_config.get(CONF_MEDIA_CONTENT_TYPE)
        if not media_content_id:
            if start_id:
                media_content_id = start_id
                if start_type:
                    media_content_type = start_type
            else:
                media_content_type = None

        browse_entity = entity is not None
        if (
            browse_entity
            and entity is not None
            and media_source
            and not start_id
            and not media_content_id
            and entity.platform
            and entity.platform.platform_name != media_source
        ):
            # entity_id is only the play target (e.g. Music Assistant for Radio).
            browse_entity = False
        if browse_entity and entity is not None:
            try:
                result = await entity.async_browse_media(
                    media_content_type, media_content_id
                )
                return self._wrap_browse_item(source_key, result)
            except HomeAssistantError as err:
                errors.append(str(err))

        if domain := self._browse_source_domain(source_config):
            try:
                result = await self._async_browse_via_integration(
                    domain, media_content_type, media_content_id
                )
            except HomeAssistantError as err:
                errors.append(str(err))
                result = None
            if result is not None:
                return self._wrap_browse_item(source_key, result)

        if media_source:
            source_id = media_content_id
            if not source_id:
                source_id = f"media-source://{media_source}"
            elif not is_media_source_id(source_id):
                source_id = f"media-source://{media_source}/{source_id}"
            try:
                result = await ms_async_browse_media(self.hass, source_id)
                return self._wrap_browse_item(source_key, result)
            except HomeAssistantError as err:
                errors.append(str(err))

        raise HomeAssistantError(
            f"Could not browse media source '{source_key}': {'; '.join(errors) or 'no target available'}"
        )

    def _browse_sources_root(self) -> BrowseMedia:
        children: list[BrowseMedia] = []
        for source_key, source_config in self._browse_media_sources.items():
            children.append(
                BrowseMedia(
                    title=source_config.get(CONF_TITLE) or source_key,
                    media_class=MediaClass.APP,
                    media_content_type="app",
                    media_content_id=self._encode_browse_id(source_key),
                    can_play=False,
                    can_expand=True,
                    thumbnail=self._browse_source_thumbnail(source_config),
                    children_media_class=MediaClass.DIRECTORY,
                )
            )
        return BrowseMedia(
            title=self.name or "Media",
            media_class=MediaClass.DIRECTORY,
            media_content_type="apps",
            media_content_id="",
            can_play=False,
            can_expand=True,
            children=children,
            children_media_class=MediaClass.APP,
        )

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
        if (
            CONF_PLAY_MEDIA_SCRIPT in self._service_scripts
            or CONF_BROWSE_MEDIA_SCRIPT in self._service_scripts
            or self._browse_media_entity
            or self._browse_media_sources
        ):
            support |= MediaPlayerEntityFeature.PLAY_MEDIA
        if (
            CONF_VOLUME_UP_SCRIPT in self._service_scripts
            and CONF_VOLUME_DOWN_SCRIPT in self._service_scripts
        ):
            support |= MediaPlayerEntityFeature.VOLUME_STEP
        if len(self.source_list) > 0:
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
        if (
            self._browse_media_entity_id
            or self._browse_media_sources
            or CONF_BROWSE_MEDIA_SCRIPT in self._service_scripts
        ):
            support |= MediaPlayerEntityFeature.BROWSE_MEDIA
        if (
            self._search_media_entity_id
            or CONF_SEARCH_MEDIA_SCRIPT in self._service_scripts
        ):
            support |= MediaPlayerEntityFeature.SEARCH_MEDIA
        if CONF_REPEAT_SET_SCRIPT in self._service_scripts:
            support |= MediaPlayerEntityFeature.REPEAT_SET
        if (
            CONF_JOIN_SCRIPT in self._service_scripts
            and CONF_UNJOIN_SCRIPT in self._service_scripts
        ):
            support |= MediaPlayerEntityFeature.GROUPING

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
            return self._base_media_player_entity.source_list

        return []

    @property
    def sound_mode_list(self) -> list | list[str] | None:
        """List of available sound modes."""
        if self._sound_mode_scripts:
            return list(self._sound_mode_scripts.keys())

        if self._base_media_player_entity:
            return self._base_media_player_entity.sound_mode_list

        return []

    async def async_media_next_track(self) -> None:
        """Send next track command."""
        if script := self._service_scripts.get(CONF_MEDIA_NEXT_TRACK_SCRIPT):
            await self._async_run_script(script)
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_media_next_track()

    async def async_media_pause(self) -> None:
        """Send pause command."""
        if script := self._service_scripts.get(CONF_MEDIA_PAUSE_SCRIPT):
            await self._async_run_script(script)
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_media_pause()

    async def async_media_play(self) -> None:
        """Send play command."""
        if script := self._service_scripts.get(CONF_MEDIA_PLAY_SCRIPT):
            await self._async_run_script(script)
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_media_play()

    async def async_media_play_pause(self) -> None:
        """Play or pause the media player."""
        if script := self._service_scripts.get(CONF_MEDIA_PLAY_PAUSE_SCRIPT):
            await self._async_run_script(script)
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_media_play_pause()

    async def async_media_previous_track(self) -> None:
        """Send previous track command."""
        if script := self._service_scripts.get(CONF_MEDIA_PREVIOUS_TRACK_SCRIPT):
            await self._async_run_script(script)
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_media_previous_track()

    async def async_media_seek(self, position: float) -> None:
        """Send seek command."""
        if script := self._service_scripts.get(CONF_MEDIA_SEEK_SCRIPT):
            await self._async_run_script(script, {"position": position})
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_media_seek(position)

    async def async_media_stop(self) -> None:
        """Send stop command."""
        if script := self._service_scripts.get(CONF_MEDIA_STOP_SCRIPT):
            await self._async_run_script(script)
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_media_stop()

    async def async_set_repeat(self, repeat: RepeatMode) -> None:
        """Set repeat mode."""
        if script := self._service_scripts.get(CONF_REPEAT_SET_SCRIPT):
            await self._async_run_script(script, {"repeat": repeat})
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_set_repeat(repeat)

    async def async_set_shuffle(self, shuffle: bool) -> None:
        """Enable/disable shuffle mode."""
        if script := self._service_scripts.get(CONF_SHUFFLE_SET_SCRIPT):
            await self._async_run_script(script, {"shuffle": shuffle})
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_set_shuffle(shuffle)

    async def async_toggle(self) -> None:
        """Toggle the power on the media player."""
        if script := self._service_scripts.get(CONF_TOGGLE_SCRIPT):
            await self._async_run_script(script)
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_toggle()

    async def async_turn_off(self) -> None:
        """Turn the media player off."""
        if script := self._service_scripts.get(CONF_TURN_OFF_SCRIPT):
            await self._async_run_script(script)
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_turn_off()

    async def async_turn_on(self) -> None:
        """Turn the media player on."""
        if script := self._service_scripts.get(CONF_TURN_ON_SCRIPT):
            await self._async_run_script(script)
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_turn_on()

    async def async_volume_down(self) -> None:
        """Turn volume down for media player."""
        if script := self._service_scripts.get(CONF_VOLUME_DOWN_SCRIPT):
            await self._async_run_script(script)
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_volume_down()

    async def async_mute_volume(self, mute: bool) -> None:
        """Mute the volume."""
        if script := self._service_scripts.get(CONF_VOLUME_MUTE_SCRIPT):
            await self._async_run_script(script, {"mute": mute})
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_mute_volume(mute)

    async def async_set_volume_level(self, volume: float) -> None:
        """Set volume level, range 0..1."""
        if script := self._service_scripts.get(CONF_VOLUME_SET_SCRIPT):
            await self._async_run_script(script, {"volume": volume})
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_set_volume_level(volume)

    async def async_volume_up(self) -> None:
        """Turn volume up for media player."""
        if script := self._service_scripts.get(CONF_VOLUME_UP_SCRIPT):
            await self._async_run_script(script)
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_volume_up()

    async def async_clear_playlist(self) -> None:
        """Clear players playlist."""
        if script := self._service_scripts.get(CONF_CLEAR_PLAYLIST_SCRIPT):
            await self._async_run_script(script)
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_clear_playlist()

    async def async_join_players(self, group_members: list[str]) -> None:
        """Join `group_members` as a player group with the current player."""
        if script := self._service_scripts.get(CONF_JOIN_SCRIPT):
            await self._async_run_script(script, {"group_members": group_members})
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_join_players(group_members)

    async def async_play_media(
        self, media_type: MediaType | str, media_id: str, **kwargs
    ) -> None:
        """Play a piece of media."""
        if decoded := self._decode_browse_id(media_id):
            source_key, inner_type, inner_id = decoded
            source_config = self._browse_media_sources.get(source_key)
            if not source_config:
                raise HomeAssistantError(f"Unknown browse media source '{source_key}'")
            await self._async_play_on_source(
                source_config,
                inner_type or media_type,
                inner_id or "",
                **kwargs,
            )
            return

        if is_media_source_id(media_id):
            domain = self._media_source_domain(media_id)
            if domain and (matched := self._source_for_media_source_domain(domain)):
                _, source_config = matched
                await self._async_play_on_source(
                    source_config, media_type, media_id, **kwargs
                )
                return

        if script := self._service_scripts.get(CONF_PLAY_MEDIA_SCRIPT):
            if is_media_source_id(media_id):
                media_type = MediaType.MUSIC
                play_item = await async_resolve_media(
                    self.hass, media_id, self.entity_id
                )
                media_id = async_process_play_media_url(self.hass, play_item.url)

            await self._async_run_script(
                script, {"media_type": media_type, "media_id": media_id}
            )
            return

        if self._browse_media_entity:
            await self._browse_media_entity.async_play_media(
                media_type, media_id, **kwargs
            )
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_play_media(
                media_type, media_id, **kwargs
            )

    async def async_select_sound_mode(self, sound_mode) -> None:
        """Select sound mode."""
        if sound_mode not in (self.sound_mode_list or []):
            return

        if script := self._sound_mode_scripts.get(sound_mode):
            await self._async_run_script(script)
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_select_sound_mode(sound_mode)

    async def async_select_source(self, source) -> None:
        """Select input source."""
        if source not in self.source_list:
            return

        if script := self._source_scripts.get(source):
            await self._async_run_script(script)
            return

        if self._base_media_player_entity:
            await self._base_media_player_entity.async_select_source(source)

    async def async_unjoin_player(self) -> None:
        """Remove this player from any group."""
        if script := self._service_scripts.get(CONF_UNJOIN_SCRIPT):
            await self._async_run_script(script)
            return

        if self._base_media_player_entity:
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
        if decoded := self._decode_browse_id(media_content_id):
            source_key, inner_type, inner_id = decoded
            if source_key not in self._browse_media_sources:
                raise HomeAssistantError(
                    f"Unknown browse media source '{source_key}'"
                )
            return await self._async_browse_source(source_key, inner_type, inner_id)

        if self._browse_media_sources and not media_content_id:
            return self._browse_sources_root()

        if script := self._service_scripts.get(CONF_BROWSE_MEDIA_SCRIPT):
            result = await self._async_run_script(
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
                    "Browse media script did not return a dictionary."
                )
            return self._build_browse_media(result_data)

        content_id = media_content_id or ""
        if content_id.startswith("media-source://"):
            return await ms_async_browse_media(self.hass, media_content_id)

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
            result = await self._async_run_script(
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
                browse_media_entries.append(self._build_browse_media(result_media_entry))
            return SearchMedia(result=browse_media_entries)

        if self._search_media_entity:
            result = await self._search_media_entity.async_search_media(query)
            if self._browse_media_sources:
                wrapped: list[BrowseMedia] = []
                for item in result.result:
                    source_key = self._browse_source_for_item(item)
                    if source_key:
                        wrapped.append(self._wrap_browse_item(source_key, item))
                    else:
                        wrapped.append(item)
                return SearchMedia(result=wrapped)
            return result

        if self._base_media_player_entity:
            return await self._base_media_player_entity.async_search_media(query)

        raise HomeAssistantError(
            "No search media entity configured for this template media player."
        )

    def _build_browse_media(self, item: dict[str, Any]) -> BrowseMedia:
        """Build a BrowseMedia tree from a script response dictionary."""
        required_attributes = {
            "media_class",
            "media_content_id",
            "media_content_type",
            "title",
            "can_play",
            "can_expand",
        }
        if any(attribute not in item for attribute in required_attributes):
            raise HomeAssistantError(
                f"Could not build BrowseMedia, missing required attributes in: {item}"
            )

        children: list[BrowseMedia] | None = None
        if "children" in item:
            child_items = item["children"]
            if child_items is None:
                children = None
            elif not isinstance(child_items, list):
                raise HomeAssistantError(
                    "Could not build BrowseMedia, child items must be a list."
                )
            else:
                children = []
                for child_item in child_items:
                    if not isinstance(child_item, dict):
                        raise HomeAssistantError(
                            "Could not build BrowseMedia, child items must be dictionaries."
                        )
                    children.append(self._build_browse_media(child_item))

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
