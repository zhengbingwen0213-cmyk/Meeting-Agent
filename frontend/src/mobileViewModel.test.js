import test from 'node:test';
import assert from 'node:assert/strict';

import {
  getCandidatePreview,
  getPrimaryReason,
  getProcessingSteps,
  getScreenMode,
  hasRecommendation,
} from './mobileViewModel.js';

test('getScreenMode returns processing while uploading', () => {
  assert.equal(getScreenMode({ recordingState: 'uploading', errorMessage: '', result: {} }), 'processing');
});

test('getScreenMode returns result when a recommendation title exists', () => {
  const result = { recommendation: { title: '星巴克' } };
  assert.equal(getScreenMode({ recordingState: 'done', errorMessage: '', result }), 'result');
});

test('getScreenMode returns correction when an error exists without result', () => {
  assert.equal(getScreenMode({ recordingState: 'ready', errorMessage: '没有听清两个地点', result: {} }), 'correction');
});

test('getProcessingSteps highlights the requested step index', () => {
  const steps = getProcessingSteps(2);
  assert.equal(steps.length, 4);
  assert.deepEqual(
    steps.map((step) => step.status),
    ['done', 'done', 'active', 'pending'],
  );
});

test('hasRecommendation detects title or answer text', () => {
  assert.equal(hasRecommendation({ answerText: '', recommendation: { title: '' } }), false);
  assert.equal(hasRecommendation({ answerText: '推荐你们见面', recommendation: { title: '' } }), true);
});

test('getPrimaryReason prefers recommendation reasons before summary', () => {
  const result = {
    answerText: '语音回答',
    recommendation: {
      summary: '摘要',
      reasons: ['位于中间区域，交通便利。'],
    },
  };
  assert.equal(getPrimaryReason(result), '位于中间区域，交通便利。');
});

test('getCandidatePreview normalizes candidate labels', () => {
  const result = {
    recommendation: {
      candidates: [
        { name: '瑞幸咖啡', address: '古墩印象城', distance: '87' },
        { title: 'Manner Coffee', formatted_address: '余杭塘路785号', distance_text: '1.5 km' },
      ],
    },
  };
  assert.deepEqual(getCandidatePreview(result), [
    {
      title: '瑞幸咖啡',
      address: '古墩印象城',
      distance: '87 m',
    },
    {
      title: 'Manner Coffee',
      address: '余杭塘路785号',
      distance: '1.5 km',
    },
  ]);
});
