import { useEffect, useRef, useState } from 'react';
import { getClientConfig } from './clientConfig.js';
import { loadAmap } from './amapLoader.js';

const DEFAULT_CENTER = [116.397428, 39.90923];

export default function AmapPanel({ mapData }) {
  const containerRef = useRef(null);
  const mapRef = useRef(null);
  const overlaysRef = useRef([]);
  const [mapUnavailable, setMapUnavailable] = useState(false);

  useEffect(() => {
    let isCancelled = false;

    async function initializeMap() {
      try {
        const config = await getClientConfig();
        const amapConfig = config?.amap || {};
        if (!amapConfig.enabled || !amapConfig.js_api_key) {
          setMapUnavailable(true);
          return;
        }
        if (!amapConfig.security_js_code && !amapConfig.allow_without_security_js_code) {
          setMapUnavailable(true);
          return;
        }

        const AMap = await loadAmap({
          key: amapConfig.js_api_key,
          securityJsCode: amapConfig.security_js_code,
        });

        if (isCancelled || !containerRef.current || mapRef.current) return;

        mapRef.current = new AMap.Map(containerRef.current, {
          center: getInitialCenter(mapData),
          zoom: mapData?.meetingPoint ? 13 : 4,
          mapStyle: 'amap://styles/normal',
          layers: [new AMap.TileLayer()],
          features: ['bg', 'road', 'building', 'point'],
          showLabel: true,
          resizeEnable: true,
          viewMode: '2D',
        });
      } catch {
        if (!isCancelled) setMapUnavailable(true);
      }
    }

    initializeMap();

    return () => {
      isCancelled = true;
    };
  }, [mapData]);

  useEffect(() => {
    if (!mapRef.current || !window.AMap) return;
    renderOverlays(window.AMap, mapRef.current, mapData, overlaysRef);
  }, [mapData]);

  useEffect(() => () => {
    if (mapRef.current) {
      mapRef.current.destroy();
      mapRef.current = null;
    }
  }, []);

  if (mapUnavailable) {
    return <MapFallback />;
  }

  return (
    <div className="amap-stage">
      <div className="amap-canvas" ref={containerRef} aria-label="高德实时地图" />
      <MapFallback isBehindMap />
    </div>
  );
}

function renderOverlays(AMap, map, mapData, overlaysRef) {
  overlaysRef.current.forEach((overlay) => map.remove(overlay));
  overlaysRef.current = [];

  const points = [
    mapData?.originA ? { ...mapData.originA, kind: 'origin' } : null,
    mapData?.originB ? { ...mapData.originB, kind: 'origin' } : null,
    mapData?.meetingPoint ? { ...mapData.meetingPoint, kind: 'meeting' } : null,
  ].filter(isValidPoint);

  if (!points.length) {
    map.setCenter(DEFAULT_CENTER);
    map.setZoom(4);
    return;
  }

  const markers = points.map((point) => new AMap.Marker({
    position: [point.lng, point.lat],
    title: point.title || point.address || '',
    anchor: 'center',
    content: `<span class="amap-marker-square ${point.kind === 'meeting' ? 'is-meeting' : ''}"></span>`,
  }));

  markers.forEach((marker) => map.add(marker));
  overlaysRef.current.push(...markers);

  const routePoints = [mapData.originA, mapData.meetingPoint, mapData.originB].filter(isValidPoint);
  if (routePoints.length >= 2) {
    const polyline = new AMap.Polyline({
      path: routePoints.map((point) => [point.lng, point.lat]),
      strokeColor: '#000000',
      strokeWeight: 4,
      strokeOpacity: 1,
      lineJoin: 'round',
    });
    map.add(polyline);
    overlaysRef.current.push(polyline);
  }

  map.setFitView(overlaysRef.current, false, [44, 44, 44, 44]);
}

function getInitialCenter(mapData) {
  if (isValidPoint(mapData?.meetingPoint)) return [mapData.meetingPoint.lng, mapData.meetingPoint.lat];
  if (isValidPoint(mapData?.originA)) return [mapData.originA.lng, mapData.originA.lat];
  return DEFAULT_CENTER;
}

function isValidPoint(point) {
  return Number.isFinite(point?.lng) && Number.isFinite(point?.lat);
}

function MapFallback({ isBehindMap = false }) {
  return (
    <div className={isBehindMap ? 'map-fallback is-behind-map' : 'map-fallback'} aria-hidden={isBehindMap}>
      <span className="pin pin-a" />
      <span className="pin pin-b" />
      <span className="pin pin-meet" />
      <span className="route route-one" />
      <span className="route route-two" />
    </div>
  );
}
