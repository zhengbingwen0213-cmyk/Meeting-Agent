# MeetPoint AI V1 PRD

## 1. Product Positioning

MeetPoint AI V1 is a mobile-first meeting-point decision assistant for lightweight friend and coworker meetups.

It helps users move from "Where should we meet?" to a confirmed meeting place through a short multi-turn conversation, map-based recommendation, and explainable comparison.

Current version is treated as Demo v0: it proves that ASR, DeepSeek extraction, Amap lookup, map display, and TTS can be connected. V1 should turn that pipeline into a reliable decision loop.

## 2. Target User And Scenario

Primary scenario:

- Two people want to meet in the same city.
- They know rough start locations.
- They need a fair, convenient, and scenario-appropriate place.
- They want the answer quickly on a phone.

Initial target users:

- Friends deciding where to meet.
- Coworkers choosing a casual meeting point.
- Visitors unfamiliar with the city.

Example input:

> 我在杭州东站，朋友在杭州西站，我们想找个适合聊天的地方见面。

## 3. Product Goals

- Convert a vague meeting request into structured meeting context.
- Ask follow-up questions when required information is missing.
- Recommend multiple candidate places instead of a single hard-coded result.
- Explain the recommendation in human terms: fair distance, transit convenience, scene fit, and tradeoffs.
- Let the user adjust the result through natural language.
- Preserve the existing demo capabilities as fallback: voice input, ASR, location extraction, Amap lookup, map result, and voice reply.

## 4. Non-Goals For V1

- No restaurant reservation.
- No payment or ticketing.
- No full navigation workflow.
- No account system.
- No real-time location sharing.
- No group chat or social invitation system.
- No complex multi-person scheduling.

## 5. V1 User Flow

1. User opens the app and speaks or types a meetup request.
2. The assistant extracts meeting context: participant locations, city, scene, preferences, and constraints.
3. If required information is missing, the assistant asks one focused follow-up question.
4. The assistant geocodes known locations and searches candidate POIs.
5. The assistant compares candidates by distance fairness, transport convenience, scene fit, quality signals, and uncertainty.
6. The app shows three ranked recommendations on the map and in a bottom sheet.
7. User can confirm, play voice reply, or ask for adjustment.
8. The session is saved into history.

## 6. Required Context Slots

Required:

- User location.
- Other participant location.
- City or inferable city.

Recommended:

- Meeting scene: coffee, meal, shopping, work chat, transfer, general meetup.
- Transport mode: subway, driving, walking, unknown.
- Preference: quiet, close to both, close to one side, cheap, high quality, near station.

Optional:

- Time of day.
- Budget.
- Number of people.
- Indoor or outdoor preference.
- Accessibility needs.

## 7. Agent Behavior Policy

The assistant should behave like a careful decision partner, not a one-shot answer generator.

- If both participant locations are missing, ask for both.
- If one participant location is missing, ask only for the missing one.
- If locations are ambiguous, show the interpreted place and ask for confirmation.
- Do not invent coordinates, route time, or business status.
- If map/tool data is incomplete, explain uncertainty instead of pretending confidence.
- Recommend three options when possible.
- Include one clear reason and one possible tradeoff for each option.
- Keep follow-up questions short and answerable.
- Prefer continuing the current session instead of restarting the flow.

## 8. Recommendation Strategy

V1 should move from fixed-rule recommendation to candidate scoring.

Candidate sources:

- Amap geocoding for participant locations.
- Amap POI search around an estimated middle area.
- Existing Amap recommendation endpoint or MCP service where available.

Suggested score dimensions:

- Fairness: travel burden between participants is balanced.
- Accessibility: subway, station, road, or walking convenience.
- Scene fit: candidate category matches user intent.
- Quality: rating, popularity, or available metadata if provided.
- Simplicity: easy to explain and easy to find.
- Uncertainty penalty: missing or low-confidence map data lowers rank.

Each candidate should produce:

- Name.
- Address.
- Coordinates.
- Category.
- Distance or rough travel burden from each side when available.
- Recommendation reason.
- Tradeoff.
- Confidence level.

## 9. Functional Requirements

### 9.1 Input

- Support voice recording as the primary entry.
- Support text input as fallback and for quick correction.
- Show example input in the empty state.
- Allow user to restart the session.

### 9.2 Context Understanding

- Extract user location, other participant location, city, scene, and preferences.
- Display extracted context before recommendation when confidence is not high.
- Allow inline correction of extracted fields.

### 9.3 Clarification

- Ask one question at a time.
- Prefer chips for common answers.
- Preserve already extracted information.
- Continue recommendation immediately after required slots are complete.

### 9.4 Recommendation Result

- Show map markers for both participants and candidate places.
- Show a ranked list of three candidates.
- Make the top recommendation visually clear.
- Explain why each candidate fits.
- Expose tradeoffs so the result feels trustworthy.

### 9.5 Adjustment

- Support natural-language refinements:
  - 换安静点
  - 离朋友近一点
  - 适合吃饭
  - 预算低一点
  - 靠近地铁
- Re-rank candidates based on the new preference.
- Keep the conversation history visible enough to avoid confusion.

### 9.6 History

- Save completed sessions.
- Show time, original request, selected recommendation, and city.
- Allow reopening a previous result.

### 9.7 Failure Recovery

- If ASR fails, ask user to retry or type.
- If LLM extraction fails, use local fallback extraction where possible.
- If map lookup fails, show which location could not be resolved.
- If no candidate is found, suggest broadening the area or changing scene.

## 10. Mobile Prototype States

The V1 mobile prototype should cover these states:

| State | Purpose | Key UI |
| --- | --- | --- |
| Intent Input | Start the session | Map, voice button, text fallback, example |
| Context Confirmation | Make extraction visible | Slot cards for both locations, scene, preferences |
| Clarification | Fill missing info | Assistant question, answer chips, text input |
| Preferences | Improve result quality | Scene and preference chips |
| Planning | Build trust during processing | Step list for extraction, geocoding, POI search, ranking |
| Result Compare | Decide between options | Map markers, top 3 cards, reasons and tradeoffs |
| Result Detail | Confirm or adjust | Detail sheet, voice reply, adjustment actions |
| History | Reuse previous sessions | Session list and restore action |

## 11. Success Metrics

Product metrics:

- First successful recommendation rate.
- Average turns to recommendation.
- Result accepted rate.
- Adjustment rate after first result.
- Missing-location clarification success rate.

Technical metrics:

- ASR success rate.
- Location extraction success rate.
- Amap geocoding success rate.
- Candidate generation success rate.
- Tool-call failure recovery rate.

Experience metrics:

- Time from first input to first recommendation.
- Percentage of results with at least three candidates.
- Percentage of recommendations with reason and tradeoff.

## 12. V1 Acceptance Criteria

- User can complete a two-person meetup recommendation on mobile.
- App can recover when the first utterance lacks one required location.
- Result page shows at least one top recommendation and ideally three candidates.
- User can refine the recommendation without starting over.
- App never sends empty location strings to Amap.
- App does not present hard-coded recommendation as if it were computed.
- Demo v0 behavior remains available during transition.

## 13. Suggested Build Phases

Phase 1: Product and prototype

- Finalize this PRD.
- Review the mobile visual prototype.
- Freeze V1 core flow and non-goals.

Phase 2: Conversation state

- Add session-based state model.
- Support slot filling and clarification.
- Keep current one-shot API as compatibility fallback.

Phase 3: Candidate recommendation

- Add POI candidate search.
- Add scoring and ranking.
- Add explainable recommendation payload.

Phase 4: Mobile UI implementation

- Implement V1 mobile screens.
- Add adjustment flow.
- Add result history improvements.

Phase 5: Reliability and evaluation

- Add test cases for common city/location utterances.
- Add map failure diagnostics.
- Add recommendation quality checks.

