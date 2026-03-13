"""Sensor platform for Wuhan Gas."""

from homeassistant.components.sensor import (
    SensorEntity,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from .const import DOMAIN
from .coordinator import WuhanGasDataUpdateCoordinator

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Wuhan Gas sensors from a config entry."""
    coordinator: WuhanGasDataUpdateCoordinator = hass.data[DOMAIN][config_entry.entry_id]
    
    sensors = [
        WuhanGasBalanceSensor(coordinator, config_entry),
        WuhanGasAnnualBillSensor(coordinator, config_entry),
        WuhanGasLastMonthBillSensor(coordinator, config_entry),
    ]
    
    async_add_entities(sensors)

class WuhanGasSensor(CoordinatorEntity, SensorEntity):
    """Base class for Wuhan Gas sensors."""
    
    _attr_has_entity_name = True
    
    def __init__(self, coordinator: WuhanGasDataUpdateCoordinator, config_entry: ConfigEntry) -> None:
        """Initialize the sensor."""
        super().__init__(coordinator)
        self._config_entry = config_entry
        self._coordinator = coordinator
        self._attr_device_info = {
            "identifiers": {(DOMAIN, config_entry.entry_id)},
            "name": f"武汉天然气 {coordinator.userno}",
            "manufacturer": "武汉天然气",
            "model": "燃气账户",
        }
    
    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        if not self.coordinator.data:
            return {}
        
        attrs = {
            "account_number": self._coordinator.userno,
        }
        
        if "user_name" in self.coordinator.data:
            attrs["user_name"] = self.coordinator.data["user_name"]
        if "user_addr" in self.coordinator.data:
            attrs["address"] = self.coordinator.data["user_addr"]
        
        return attrs

class WuhanGasBalanceSensor(WuhanGasSensor):
    """Sensor for account balance."""
    
    _attr_name = "账户余额"
    _attr_unique_id = "balance"
    _attr_native_unit_of_measurement = "元"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 2
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        if not self.coordinator.data or "balance" not in self.coordinator.data:
            return None
        return self.coordinator.data["balance"]
    
    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        balance = self.native_value
        if balance is not None and balance < 0:
            return "mdi:cash-remove"
        return "mdi:cash"

class WuhanGasAnnualBillSensor(WuhanGasSensor):
    """Sensor for annual bill total."""
    
    _attr_name = "年度账单"
    _attr_unique_id = "annual_bill"
    _attr_native_unit_of_measurement = "元"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = SensorStateClass.TOTAL
    _attr_suggested_display_precision = 2
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        if not self.coordinator.data or "annual_total" not in self.coordinator.data:
            return None
        return self.coordinator.data["annual_total"]
    
    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        attrs = super().extra_state_attributes
        
        if self.coordinator.data and "monthly_bills" in self.coordinator.data:
            attrs["monthly_details"] = self.coordinator.data["monthly_bills"]
        
        return attrs
    
    @property
    def icon(self):
        """Return the icon to use in the frontend."""
        return "mdi:calendar-text"

class WuhanGasLastMonthBillSensor(WuhanGasSensor):
    """Sensor for last month's bill."""
    
    _attr_name = "上月账单"
    _attr_unique_id = "last_month_bill"
    _attr_native_unit_of_measurement = "元"
    _attr_device_class = SensorDeviceClass.MONETARY
    _attr_state_class = None
    _attr_suggested_display_precision = 2
    
    @property
    def native_value(self):
        """Return the state of the sensor."""
        if not self.coordinator.data or "last_month_bill" not in self.coordinator.data:
            return None
        return self.coordinator.data["last_month_bill"]
    
    @property
    def extra_state_attributes(self):
        """Return additional attributes."""
        attrs = super().extra_state_attributes
        
        if self.coordinator.data and "last_month" in self.coordinator.data:
            attrs["bill_month"] = self.coordinator.data["last_month"]
        
        return attrs
    
    @property
    def icon(self):
        """Return the icon
