const processingLabels = [
  '语音识别中',
  '提取地点',
  '搜索中间点',
  '生成语音回复',
];

export function hasRecommendation(result = {}) {
  return Boolean(result.answerText || result.recommendation?.title);
}

export function getScreenMode({ recordingState, errorMessage, result }) {
  if (recordingState === 'uploading') return 'processing';
  if (hasRecommendation(result)) return 'result';
  if (errorMessage) return 'correction';
  return 'ready';
}

export function getProcessingSteps(activeIndex = 1) {
  return processingLabels.map((label, index) => {
    let status = 'pending';
    if (index < activeIndex) status = 'done';
    if (index === activeIndex) status = 'active';
    return { label, status };
  });
}

export function getPrimaryReason(result = {}) {
  const reasons = Array.isArray(result.recommendation?.reasons)
    ? result.recommendation.reasons
    : [];
  const firstReason = reasons.map(normalizeReason).find(Boolean);
  return firstReason || result.recommendation?.summary || result.answerText || '位于中间区域，适合作为会面地点。';
}

export function getCandidatePreview(result = {}, limit = 3) {
  const candidates = Array.isArray(result.recommendation?.candidates)
    ? result.recommendation.candidates
    : [];

  return candidates.slice(0, limit).map((candidate, index) => {
    if (typeof candidate === 'string') {
      return {
        title: candidate,
        address: '点击查看详情',
        distance: '',
      };
    }

    const title = candidate?.name || candidate?.title || candidate?.poi_name || `备选地点 ${index + 1}`;
    const address = candidate?.address || candidate?.formatted_address || '地址待确认';
    return {
      title,
      address,
      distance: normalizeDistance(candidate?.distance_text || candidate?.distance || ''),
    };
  });
}

export function getLocationSummary(result = {}) {
  return {
    selfLocation: result.slots?.selfLocation || '我的位置',
    friendLocation: result.slots?.friendLocation || '朋友的位置',
  };
}

function normalizeReason(reason) {
  if (typeof reason === 'string') return reason;
  if (!reason || typeof reason !== 'object') return '';
  return reason.text || reason.reason || reason.summary || '';
}

function normalizeDistance(distance) {
  if (typeof distance === 'number') return `${distance} m`;
  if (typeof distance !== 'string' || !distance.trim()) return '';
  const trimmed = distance.trim();
  if (/^\d+(\.\d+)?$/.test(trimmed)) return `${trimmed} m`;
  return trimmed;
}
