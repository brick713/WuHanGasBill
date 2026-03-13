"""Config flow for Wuhan Gas."""

from __future__ import annotations
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_TOKEN
from .const import DOMAIN, CONF_USERNO, CONF_MEMBER_ID

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
                # Create unique ID
                unique_id = f"wuhan_gas_{user_input[CONF_USERNO]}"
                
                # Check if already configured
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                
                return self.async_create_entry(
                    title=f"武汉天然气 {user_input[CONF_USERNO]}",
                    data=user_input
                )
        
        data_schema = vol.Schema({
            vol.Required(CONF_USERNO): str,
            vol.Required(CONF_MEMBER_ID): str,
            vol.Required(CONF_TOKEN): str,
        })
        
        return self.async_show_form(
            step_id="user",
            data_schema=data_schema,
            errors=errors,
            description_placeholders={
                "how_to_find": "在武汉天然气小程序中使用开发者工具或网络抓包获取token"
            }
        )
    
    async def async_step_import(self, import_data):
        """Handle import from configuration.yaml."""
        return await self.async_step_user(import_data)
