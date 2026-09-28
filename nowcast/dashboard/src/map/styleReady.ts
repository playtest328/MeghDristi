import type { Map as MaplibreMap } from "maplibre-gl";

/** MapLibre's style can transiently report `isStyleLoaded() === false` even
 * after the map's own 'load' event has fired — e.g. while other layer
 * components are adding their own sources around the same time. Calling
 * addSource/addLayer during that window can silently no-op or throw
 * ("Style is not done loading."). A one-shot 'styledata' listener isn't
 * reliable here: if nothing else changes the style after the transient
 * false, no further 'styledata' event ever fires and the listener waits
 * forever — so this polls the (cheap, synchronous) isStyleLoaded() check
 * instead of waiting on a specific event. */
export function whenStyleReady(map: MaplibreMap, fn: () => void) {
  if (map.isStyleLoaded()) {
    fn();
    return;
  }
  const check = () => {
    if (map.isStyleLoaded()) fn();
    else setTimeout(check, 50);
  };
  setTimeout(check, 50);
}
