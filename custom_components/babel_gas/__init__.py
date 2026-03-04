'''
Author: brick713 hibrick713@gmail.com
Date: 2025-06-11 17:00:32
LastEditors: brick713 hibrick713@gmail.com
LastEditTime: 2026-01-28 17:39:45
FilePath: /WuHanGasBill/custom_components/babel_gas/__init__.py
Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
'''
"""初始化Babel燃气集成."""
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """设置配置条目."""
    hass.async_create_task(
        hass.config_entries.async_forward_entry_setup(entry, "sensor")
    )
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """卸载配置条目."""
    return await hass.config_entries.async_forward_entry_unload(entry, "sensor")
