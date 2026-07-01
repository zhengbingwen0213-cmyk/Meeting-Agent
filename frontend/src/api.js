const DEFAULT_ENDPOINT = '/api/meeting-point/recommend';
const HISTORY_ENDPOINT = '/api/meeting-point/history';

export async function submitMeetingAudio(audioBlob) {
  const endpoint = import.meta.env.VITE_RECOMMEND_ENDPOINT || DEFAULT_ENDPOINT;
  const formData = new FormData();
  const fileExtension = getAudioExtension(audioBlob.type);

  formData.append('audio', audioBlob, `meeting-description.${fileExtension}`);
  formData.append('client_timezone', Intl.DateTimeFormat().resolvedOptions().timeZone);
  formData.append('client_recorded_at', new Date().toISOString());

  const response = await fetch(endpoint, {
    method: 'POST',
    body: formData,
  });

  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json')
    ? await response.json()
    : { answer_text: await response.text() };

  if (!response.ok) {
    const message = payload?.detail || payload?.message || payload?.error || `接口请求失败：${response.status}`;
    throw new Error(message);
  }

  return normalizeMeetingResponse(payload);
}

export async function fetchMeetingHistory() {
  const response = await fetch(HISTORY_ENDPOINT);
  const payload = await readJsonResponse(response);

  if (!response.ok) {
    throw new Error(errorMessageFromPayload(payload, response.status));
  }

  return Array.isArray(payload.items) ? payload.items : [];
}

export async function fetchMeetingHistoryDetail(requestId) {
  const response = await fetch(`${HISTORY_ENDPOINT}/${encodeURIComponent(requestId)}`);
  const payload = await readJsonResponse(response);

  if (!response.ok) {
    throw new Error(errorMessageFromPayload(payload, response.status));
  }

  return normalizeMeetingResponse(payload);
}

async function readJsonResponse(response) {
  const contentType = response.headers.get('content-type') || '';
  return contentType.includes('application/json')
    ? response.json()
    : { answer_text: await response.text() };
}

function errorMessageFromPayload(payload, status) {
  return payload?.detail || payload?.message || payload?.error || `接口请求失败：${status}`;
}

function getAudioExtension(mimeType) {
  if (mimeType.includes('mp4')) return 'm4a';
  if (mimeType.includes('mpeg')) return 'mp3';
  if (mimeType.includes('ogg')) return 'ogg';
  if (mimeType.includes('wav')) return 'wav';
  return 'webm';
}

function normalizeMeetingResponse(payload) {
  const recommendation = payload.recommendation || payload.meeting_point || {};
  const slots = payload.slots || payload.extracted_slots || {};
  const answerText = payload.answer_text || payload.answer || payload.message || '';
  const audioUrl = payload.audio_url || payload.tts_audio_url || payload.tts_url || '';
  const audioBase64 = payload.audio_base64 || payload.tts_audio_base64 || '';
  const audioMime = payload.audio_mime || payload.tts_audio_mime || 'audio/mpeg';
  const mapData = normalizeMapData(payload);

  return {
    requestId: payload.request_id || payload.requestId || '',
    transcript: payload.transcript || payload.asr_text || '',
    slots: {
      selfLocation: slots.self_location || slots.user_location || slots.origin_a || '',
      friendLocation: slots.friend_location || slots.target_location || slots.origin_b || '',
    },
    answerText,
    audioSrc: audioUrl || createAudioDataUrl(audioBase64, audioMime),
    mapData,
    recommendation: {
      title: recommendation.title || recommendation.name || recommendation.meeting_place || '',
      address: recommendation.address || recommendation.formatted_address || '',
      summary: recommendation.summary || answerText,
      distanceText: recommendation.distance_text || recommendation.distance || '',
      durationText: recommendation.duration_text || recommendation.duration || '',
      reasons: recommendation.reasons || [],
      candidates: recommendation.candidates || recommendation.pois || [],
    },
    raw: payload,
  };
}

function createAudioDataUrl(base64, mimeType) {
  if (!base64) return '';
  if (base64.startsWith('data:')) return base64;
  return `data:${mimeType};base64,${base64}`;
}

function normalizeMapData(payload) {
  const geocoding = payload.geocoding || {};
  const map = payload.map || {};
  const recommendation = payload.recommendation || {};
  const candidates = Array.isArray(recommendation.candidates) ? recommendation.candidates : [];
  const firstCandidate = candidates[0] || {};

  const originA = normalizePoint(map.origin_a || geocoding.origin_a, '你的位置');
  const originB = normalizePoint(map.origin_b || geocoding.origin_b, '朋友的位置');
  const meetingPoint = normalizePoint(
    map.meeting_point || {
      ...recommendation.midpoint,
      title: recommendation.title,
      address: recommendation.address,
      location: recommendation.location || firstCandidate.location,
    },
    recommendation.title || '推荐地点',
  );

  return {
    originA,
    originB,
    meetingPoint,
  };
}

function normalizePoint(point, fallbackTitle) {
  if (!point || typeof point !== 'object') return null;
  const parsedLocation = parseLocation(point.location);
  const lng = toNumber(point.lng ?? point.longitude ?? parsedLocation?.lng);
  const lat = toNumber(point.lat ?? point.latitude ?? parsedLocation?.lat);

  if (!Number.isFinite(lng) || !Number.isFinite(lat)) return null;

  return {
    lng,
    lat,
    title: point.title || point.name || fallbackTitle,
    address: point.address || point.formatted_address || '',
  };
}

function parseLocation(location) {
  if (typeof location !== 'string' || !location.includes(',')) return null;
  const [lng, lat] = location.split(',');
  return {
    lng: toNumber(lng),
    lat: toNumber(lat),
  };
}

function toNumber(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : NaN;
}
