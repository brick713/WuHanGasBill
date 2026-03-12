"""Config flow for Wuhan Gas."""

from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from .const import DOMAIN, CONF_USERNO, CONF_MEMBER_ID, CONF_TOKEN

class WuhanGasConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Wuhan Gas."""
    
    VERSION = 1
    
    async def async_step_user(self, user_input=None):
        """Handle the initial step."""
        errors = {}
        
        if user_input is not None:
            # Validate input
            if len(user_input[CONF_USERNO]) < 8:
                errors[CONF_USERNO] = "invalid_account"
            elif len(user_input[CONF_MEMBER_ID]) < 5:
                errors[CONF_MEMBER_ID] = "invalid_member_id"
            elif len(user_input[CONF_TOKEN]) < 10:
                errors[CONF_TOKEN] = "invalid_token"
            else:
                # Check if already configured
                await self.async_set_unique_id(f"wuhan_gas_{user_input[CONF_USERNO]}")
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=f"武汉天燃气 {user_input[CONF_USERNO]}",
                    data=user_input
                )
        
        data_schema = vol.Schema({
            vol.Required(CONF_USERNO, default=user_input.get(CONF_USERNO, "") if user_input else ""): str,
            vol.Required(CONF_MEMBER_ID, default=user_input.get(CONF_MEMBER_ID, "") if user_input else ""): str,
            vol.Required(CONF_TOKEN, default=user_input.get(CONF_TOKEN, "") if user_input else ""): str,
        })
        
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "how_to_find": "在武汉天燃气小程序中使用开发者工具或网络抓包获取token"
            }
        )
    
    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return WuhanGasOptionsFlow(config_entry)

class WuhanGasOptionsFlow(config_entries.OptionsFlow):
    """Handle options flow for Wuhan Gas."""
    
    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry
    
    async def async_step_init(self, user_input=None):
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema({
                vol.Optional(
                    "scan_interval",
                    default=self.config_entry.options.get("scan_interval", 60)
                ): vol.All(vol.Coerce(int), vol.Range(min=30, max=1440))
            })
        )
