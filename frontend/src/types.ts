/** The part of Home Assistant's `hass` object that the panel reads. */
export interface HomeAssistant {
  language: string;
  locale?: { language: string };
}
