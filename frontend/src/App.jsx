import { useEffect, useMemo, useRef, useState } from 'react';
import {
  AlertTriangle,
  Check,
  Circle,
  Clock3,
  Edit3,
  History,
  Loader2,
  LocateFixed,
  MapPin,
  Mic,
  Play,
  RefreshCw,
  RotateCcw,
  Send,
  Sparkles,
  Square,
  Star,
  UserRound,
  UsersRound,
  Volume2,
  X,
} from 'lucide-react';
import AmapPanel from './AmapPanel.jsx';
import { fetchMeetingHistory, fetchMeetingHistoryDetail, submitMeetingAudio } from './api.js';
import {
  getCandidatePreview,
  getLocationSummary,
  getPrimaryReason,
  getProcessingSteps,
  getScreenMode,
} from './mobileViewModel.js';

const initialResult = {
  requestId: '',
  transcript: '',
  slots: {
    selfLocation: '',
    friendLocation: '',
  },
  answerText: '',
  audioSrc: '',
  mapData: null,
  recommendation: {
    title: '',
    address: '',
    summary: '',
    distanceText: '',
    durationText: '',
    reasons: [],
    candidates: [],
  },
};

export default function App() {
  const mediaRecorderRef = useRef(null);
  const audioChunksRef = useRef([]);
  const audioElementRef = useRef(null);
  const timerRef = useRef(null);
  const discardRecordingRef = useRef(false);
  const autoPlayAnswerRef = useRef(false);

  const [recordingState, setRecordingState] = useState('idle');
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [audioBlob, setAudioBlob] = useState(null);
  const [localAudioUrl, setLocalAudioUrl] = useState('');
  const [result, setResult] = useState(initialResult);
  const [errorMessage, setErrorMessage] = useState('');
  const [isPlayingAnswer, setIsPlayingAnswer] = useState(false);
  const [historyItems, setHistoryItems] = useState([]);
  const [historyState, setHistoryState] = useState('idle');
  const [historyError, setHistoryError] = useState('');
  const [selectedHistoryId, setSelectedHistoryId] = useState('');
  const [isHistoryOpen, setIsHistoryOpen] = useState(false);
  const [isCorrectionOpen, setIsCorrectionOpen] = useState(false);

  const isRecording = recordingState === 'recording';
  const isUploading = recordingState === 'uploading';
  const hasRecording = Boolean(audioBlob);
  const baseScreenMode = getScreenMode({ recordingState, errorMessage, result });
  const screenMode = isCorrectionOpen ? 'correction' : baseScreenMode;
  const locationSummary = getLocationSummary(result);
  const processingSteps = useMemo(() => getProcessingSteps(isUploading ? 1 : 0), [isUploading]);
  const candidatePreview = useMemo(() => getCandidatePreview(result), [result]);
  const primaryReason = useMemo(() => getPrimaryReason(result), [result]);

  useEffect(() => {
    return () => {
      if (timerRef.current) window.clearInterval(timerRef.current);
      if (localAudioUrl) URL.revokeObjectURL(localAudioUrl);
    };
  }, [localAudioUrl]);

  useEffect(() => {
    loadHistory();
  }, []);

  useEffect(() => {
    if (!result.audioSrc || !audioElementRef.current) return;
    if (!autoPlayAnswerRef.current) {
      setIsPlayingAnswer(false);
      return;
    }

    autoPlayAnswerRef.current = false;

    let isCancelled = false;
    audioElementRef.current.currentTime = 0;
    audioElementRef.current
      .play()
      .then(() => {
        if (!isCancelled) setIsPlayingAnswer(true);
      })
      .catch(() => {
        if (!isCancelled) setIsPlayingAnswer(false);
      });

    return () => {
      isCancelled = true;
    };
  }, [result.audioSrc]);

  async function startRecording() {
    setErrorMessage('');
    setResult(initialResult);
    setSelectedHistoryId('');
    setIsCorrectionOpen(false);
    setIsHistoryOpen(false);
    autoPlayAnswerRef.current = false;

    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);

      audioChunksRef.current = [];
      mediaRecorderRef.current = mediaRecorder;

      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = () => {
        if (discardRecordingRef.current) {
          discardRecordingRef.current = false;
          stream.getTracks().forEach((track) => track.stop());
          return;
        }

        const blob = new Blob(audioChunksRef.current, {
          type: mediaRecorder.mimeType || 'audio/webm',
        });

        stream.getTracks().forEach((track) => track.stop());
        setAudioBlob(blob);
        setLocalAudioUrl((previousUrl) => {
          if (previousUrl) URL.revokeObjectURL(previousUrl);
          return URL.createObjectURL(blob);
        });
        setRecordingState('ready');
      };

      setElapsedSeconds(0);
      timerRef.current = window.setInterval(() => {
        setElapsedSeconds((value) => value + 1);
      }, 1000);

      mediaRecorder.start();
      setRecordingState('recording');
    } catch (error) {
      setErrorMessage(error?.message || '无法使用麦克风');
      setIsCorrectionOpen(true);
      setRecordingState('idle');
    }
  }

  function stopRecording() {
    if (!mediaRecorderRef.current || mediaRecorderRef.current.state === 'inactive') return;
    mediaRecorderRef.current.stop();

    if (timerRef.current) {
      window.clearInterval(timerRef.current);
      timerRef.current = null;
    }
  }

  function resetRecording() {
    if (isRecording) {
      discardRecordingRef.current = true;
      stopRecording();
    }

    setAudioBlob(null);
    setResult(initialResult);
    setErrorMessage('');
    setSelectedHistoryId('');
    setIsCorrectionOpen(false);
    autoPlayAnswerRef.current = false;
    setElapsedSeconds(0);
    setRecordingState('idle');
    setLocalAudioUrl((previousUrl) => {
      if (previousUrl) URL.revokeObjectURL(previousUrl);
      return '';
    });
  }

  async function uploadRecording() {
    if (!audioBlob || isUploading) return;

    setErrorMessage('');
    setIsCorrectionOpen(false);
    setRecordingState('uploading');

    try {
      const nextResult = await submitMeetingAudio(audioBlob);
      autoPlayAnswerRef.current = true;
      setResult(nextResult);
      setSelectedHistoryId('');
      setRecordingState('done');
      loadHistory({ silent: true });
    } catch (error) {
      setErrorMessage(error?.message || '分析失败');
      setIsCorrectionOpen(true);
      setRecordingState('ready');
    }
  }

  function handlePrimaryVoiceAction() {
    if (isUploading) return;
    if (isRecording) {
      stopRecording();
      return;
    }
    if (hasRecording) {
      uploadRecording();
      return;
    }
    startRecording();
  }

  async function loadHistory({ silent = false } = {}) {
    if (!silent) setHistoryState('loading');
    setHistoryError('');

    try {
      const items = await fetchMeetingHistory();
      setHistoryItems(items);
      setHistoryState('ready');
    } catch (error) {
      setHistoryError(error?.message || '历史记录读取失败');
      setHistoryState('error');
    }
  }

  async function openHistoryItem(item) {
    if (!item?.request_id || historyState === 'loading-detail') return;

    setErrorMessage('');
    setHistoryError('');
    setIsCorrectionOpen(false);
    setHistoryState('loading-detail');
    autoPlayAnswerRef.current = false;

    try {
      const historyResult = await fetchMeetingHistoryDetail(item.request_id);
      setResult(historyResult);
      setRecordingState('done');
      setSelectedHistoryId(item.request_id);
      setIsHistoryOpen(false);
      setHistoryState('ready');
    } catch (error) {
      setHistoryError(error?.message || '历史详情读取失败');
      setHistoryState('error');
    }
  }

  async function playAnswerAudio() {
    if (!result.audioSrc || !audioElementRef.current) return;

    try {
      audioElementRef.current.currentTime = 0;
      await audioElementRef.current.play();
      setIsPlayingAnswer(true);
    } catch (error) {
      setErrorMessage(error?.message || '语音播放失败');
      setIsCorrectionOpen(true);
    }
  }

  return (
    <main className={`mobile-app mode-${screenMode}`}>
      <section className={screenMode === 'processing' ? 'map-layer is-softened' : 'map-layer'} aria-label="地图">
        <AmapPanel mapData={result.mapData} />
      </section>

      <header className="mobile-topbar" aria-label="应用信息">
        <button className="top-icon ghost" type="button" aria-label="定位">
          <LocateFixed size={22} aria-hidden="true" />
        </button>
        <h1>聚点助手</h1>
        <button
          className="top-icon"
          type="button"
          onClick={() => {
            setIsHistoryOpen(true);
            loadHistory({ silent: true });
          }}
          aria-label="打开历史记录"
        >
          <History size={22} aria-hidden="true" />
        </button>
      </header>

      {screenMode === 'result' ? (
        <LocationPill
          selfLocation={locationSummary.selfLocation}
          friendLocation={locationSummary.friendLocation}
          onEdit={() => setIsCorrectionOpen(true)}
        />
      ) : null}

      {screenMode === 'ready' ? (
        <ReadySheet
          recordingState={recordingState}
          elapsedSeconds={elapsedSeconds}
          hasRecording={hasRecording}
          localAudioUrl={localAudioUrl}
          errorMessage={errorMessage}
          onPrimaryAction={handlePrimaryVoiceAction}
          onReset={resetRecording}
          onCorrection={() => setIsCorrectionOpen(true)}
        />
      ) : null}

      {screenMode === 'processing' ? <ProcessingSheet steps={processingSteps} /> : null}

      {screenMode === 'result' ? (
        <ResultSheet
          result={result}
          locationSummary={locationSummary}
          candidates={candidatePreview}
          primaryReason={primaryReason}
          isPlayingAnswer={isPlayingAnswer}
          onPlay={playAnswerAudio}
          onReset={resetRecording}
          onTryAnother={() => setIsCorrectionOpen(true)}
        />
      ) : null}

      {screenMode === 'correction' ? (
        <CorrectionSheet
          errorMessage={errorMessage}
          locationSummary={locationSummary}
          onClose={() => setIsCorrectionOpen(false)}
          onRecord={startRecording}
          onReset={resetRecording}
        />
      ) : null}

      {isHistoryOpen ? (
        <HistoryOverlay
          items={historyItems}
          state={historyState}
          errorMessage={historyError}
          selectedId={selectedHistoryId}
          onClose={() => setIsHistoryOpen(false)}
          onRefresh={loadHistory}
          onOpen={openHistoryItem}
        />
      ) : null}

      {result.audioSrc ? (
        <audio
          ref={audioElementRef}
          src={result.audioSrc}
          onEnded={() => setIsPlayingAnswer(false)}
          onPause={() => setIsPlayingAnswer(false)}
        />
      ) : null}
    </main>
  );
}

function ReadySheet({
  recordingState,
  elapsedSeconds,
  hasRecording,
  localAudioUrl,
  errorMessage,
  onPrimaryAction,
  onReset,
  onCorrection,
}) {
  const isRecording = recordingState === 'recording';
  const label = isRecording ? '停止录音' : hasRecording ? '上传分析' : '按住说话';

  return (
    <section className="bottom-sheet ready-sheet" aria-label="录音入口">
      <div className="sheet-handle" />
      <h2>告诉我你们分别在哪里？</h2>
      <p className="sheet-subtitle">例如：我在杭州东站，朋友在杭州西站。</p>

      <button className={isRecording ? 'voice-button is-recording' : 'voice-button'} type="button" onClick={onPrimaryAction}>
        {isRecording ? <Square size={28} aria-hidden="true" /> : hasRecording ? <Send size={28} aria-hidden="true" /> : <Mic size={30} aria-hidden="true" />}
        <span>{label}</span>
        <strong>{formatDuration(elapsedSeconds)}</strong>
      </button>

      {localAudioUrl ? (
        <div className="recording-preview">
          <audio src={localAudioUrl} controls />
          <button type="button" onClick={onReset}>
            <RotateCcw size={17} aria-hidden="true" />
            重新录音
          </button>
        </div>
      ) : null}

      {errorMessage ? <p className="inline-error">{errorMessage}</p> : null}

      <button className="text-action" type="button" onClick={onCorrection}>
        手动输入地点
      </button>
    </section>
  );
}

function ProcessingSheet({ steps }) {
  return (
    <section className="bottom-sheet processing-sheet" aria-label="处理进度">
      <div className="sheet-handle" />
      <div className="processing-title">
        <span className="ai-badge">
          <Sparkles size={23} aria-hidden="true" />
        </span>
        <h2>正在为你们寻找合适的见面地点...</h2>
      </div>

      <div className="step-card">
        {steps.map((step) => (
          <div className={`process-step ${step.status}`} key={step.label}>
            <span className="step-dot">
              {step.status === 'done' ? <Check size={16} aria-hidden="true" /> : step.status === 'active' ? <Loader2 className="spin" size={16} aria-hidden="true" /> : <Circle size={10} aria-hidden="true" />}
            </span>
            <span>{step.label}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

function ResultSheet({
  result,
  locationSummary,
  candidates,
  primaryReason,
  isPlayingAnswer,
  onPlay,
  onReset,
  onTryAnother,
}) {
  const title = result.recommendation.title || '推荐地点';
  const address = result.recommendation.address || '地址待确认';
  const distance = result.recommendation.distanceText || '距离待计算';
  const duration = result.recommendation.durationText || '路线待补充';

  return (
    <section className="bottom-sheet result-sheet" aria-label="推荐结果">
      <div className="sheet-handle" />
      <div className="result-heading">
        <span className="result-star">
          <Star size={24} aria-hidden="true" />
        </span>
        <div>
          <p className="overline">推荐聚点</p>
          <h2>{title}</h2>
        </div>
      </div>

      <p className="address-line">
        <MapPin size={17} aria-hidden="true" />
        <span>{address}</span>
        <strong>{distance}</strong>
      </p>

      <div className="eta-grid">
        <EtaCard icon={<UserRound size={18} aria-hidden="true" />} label="你" value={duration} />
        <EtaCard icon={<UsersRound size={18} aria-hidden="true" />} label="朋友" value={duration} />
      </div>

      <div className="reason-card">
        <Sparkles size={20} aria-hidden="true" />
        <p>{primaryReason}</p>
      </div>

      <div className="location-inline">
        <span>我：{locationSummary.selfLocation}</span>
        <span>朋友：{locationSummary.friendLocation}</span>
      </div>

      <div className="result-actions">
        <button className="primary-cta" type="button" onClick={onPlay} disabled={!result.audioSrc}>
          {isPlayingAnswer ? <Volume2 size={20} aria-hidden="true" /> : <Play size={20} aria-hidden="true" />}
          播放语音回复
        </button>
        <div className="dual-actions">
          <button type="button" onClick={onTryAnother}>换一个地点</button>
          <button type="button" onClick={onReset}>重新录音</button>
        </div>
      </div>

      {candidates.length ? (
        <div className="candidate-strip" aria-label="备选地点">
          {candidates.map((candidate) => (
            <button className="candidate-chip" type="button" key={`${candidate.title}-${candidate.address}`} onClick={onTryAnother}>
              <strong>{candidate.title}</strong>
              <span>{candidate.distance || candidate.address}</span>
            </button>
          ))}
        </div>
      ) : null}
    </section>
  );
}

function EtaCard({ icon, label, value }) {
  return (
    <div className="eta-card">
      <span>{icon}</span>
      <p>{label}约</p>
      <strong>{value}</strong>
    </div>
  );
}

function CorrectionSheet({ errorMessage, locationSummary, onClose, onRecord, onReset }) {
  return (
    <section className="bottom-sheet correction-sheet" aria-label="地点修正">
      <button className="sheet-close" type="button" onClick={onClose} aria-label="关闭修正面板">
        <X size={20} aria-hidden="true" />
      </button>
      <div className="sheet-handle" />
      <span className="error-badge">
        <AlertTriangle size={28} aria-hidden="true" />
      </span>
      <h2>{errorMessage ? '需要确认地点信息' : '手动确认地点'}</h2>
      <p className="sheet-subtitle">{errorMessage || '当前版本会先保留录音链路，手动地点提交稍后接入。'}</p>

      <div className="field-stack">
        <label>
          <span>我的位置</span>
          <input value={locationSummary.selfLocation} readOnly />
        </label>
        <label>
          <span>朋友的位置</span>
          <input value={locationSummary.friendLocation === '朋友的位置' ? '' : locationSummary.friendLocation} placeholder="请输入朋友的位置..." readOnly />
        </label>
      </div>

      <button className="primary-cta" type="button" onClick={onRecord}>
        <Mic size={20} aria-hidden="true" />
        重新录音
      </button>
      <button className="secondary-cta" type="button" onClick={onReset}>
        返回首页
      </button>
    </section>
  );
}

function LocationPill({ selfLocation, friendLocation, onEdit }) {
  return (
    <button className="location-pill" type="button" onClick={onEdit}>
      <span>我：{selfLocation}</span>
      <span>朋友：{friendLocation}</span>
      <Edit3 size={17} aria-hidden="true" />
    </button>
  );
}

function HistoryOverlay({ items, state, errorMessage, selectedId, onClose, onRefresh, onOpen }) {
  const isBusy = state === 'loading' || state === 'loading-detail';

  return (
    <section className="history-overlay" aria-label="历史记录">
      <div className="history-backdrop" onClick={onClose} />
      <div className="history-sheet">
        <div className="history-top">
          <button type="button" onClick={onClose} aria-label="关闭历史记录">
            <X size={20} aria-hidden="true" />
          </button>
          <h2>历史记录</h2>
          <button type="button" onClick={() => onRefresh()} disabled={isBusy} aria-label="刷新历史记录">
            <RefreshCw className={state === 'loading' ? 'spin' : ''} size={19} aria-hidden="true" />
          </button>
        </div>

        {errorMessage ? <p className="inline-error">{errorMessage}</p> : null}

        {items.length > 0 ? (
          <div className="history-list-mobile">
            {items.map((item) => {
              const route = [item.self_location, item.friend_location].filter(Boolean).join(' -> ');
              const meta = [item.distance_text, item.address].filter(Boolean).join(' · ');
              const isSelected = item.request_id === selectedId;

              return (
                <button
                  className={isSelected ? 'history-card active' : 'history-card'}
                  type="button"
                  key={item.request_id}
                  onClick={() => onOpen(item)}
                  disabled={state === 'loading-detail'}
                >
                  <span className="history-icon">
                    <Clock3 size={18} aria-hidden="true" />
                  </span>
                  <span className="history-copy">
                    <strong>{item.title || '历史推荐'}</strong>
                    <span>{route || item.transcript_preview || '未识别到地址'}</span>
                    <small>{meta || formatHistoryDate(item.created_at)}</small>
                  </span>
                </button>
              );
            })}
          </div>
        ) : (
          <p className="history-empty-mobile">{state === 'loading' ? '读取历史中' : '暂无历史记录'}</p>
        )}
      </div>
    </section>
  );
}

function formatDuration(totalSeconds) {
  const minutes = Math.floor(totalSeconds / 60).toString().padStart(2, '0');
  const seconds = (totalSeconds % 60).toString().padStart(2, '0');
  return `${minutes}:${seconds}`;
}

function formatHistoryDate(value) {
  if (!value) return '未知时间';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '未知时间';

  return new Intl.DateTimeFormat('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
  }).format(date);
}
