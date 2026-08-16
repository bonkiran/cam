import { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Alert, Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { useEvent } from 'expo';
import { VideoView, useVideoPlayer } from 'expo-video';
import * as ScreenOrientation from 'expo-screen-orientation';
import { Card, Pill, PrimaryButton, SecondaryButton, Subtitle, Title } from '@/components/UI';
import { api, apiUrl, EventRecord, FrameRecord, VideoRecord } from '@/lib/api';
import { colors } from '@/theme';

type SequenceResponse = {
  frames: { image_url: string; offset: number; frame_number: number; timestamp: number }[];
};

type LoopRange = { start: number; end: number };

const EVENT_TYPES: EventRecord['event_type'][] = ['four', 'six', 'dot', 'single', 'two', 'three', 'wicket', 'other'];
const EVENT_LABELS: Record<EventRecord['event_type'], string> = {
  four: 'FOUR', six: 'SIX', dot: 'DOT', single: '1', two: '2', three: '3', wicket: 'WICKET', other: 'OTHER',
};

export default function AnalysisScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const videoId = Number(id);
  const [video, setVideo] = useState<VideoRecord | null>(null);
  const [frames, setFrames] = useState<FrameRecord[]>([]);
  const [events, setEvents] = useState<EventRecord[]>([]);
  const [sequence, setSequence] = useState<SequenceResponse['frames']>([]);
  const [error, setError] = useState('');
  const [extracting, setExtracting] = useState(false);
  const [tagging, setTagging] = useState(false);
  const [loopRange, setLoopRange] = useState<LoopRange | null>(null);
  const videoViewRef = useRef<any>(null);

  const source = useMemo(() => video ? apiUrl(video.video_url) : null, [video]);
  const player = useVideoPlayer(source, p => {
    p.timeUpdateEventInterval = 0.05;
    p.preservesPitch = true;
  });
  const { currentTime = 0 } = useEvent(player, 'timeUpdate', {
    currentTime: 0,
    bufferedPosition: 0,
    currentLiveTimestamp: null,
    currentOffsetFromLive: null,
  });
  const { isPlaying = false } = useEvent(player, 'playingChange', { isPlaying: player.playing });

  useEffect(() => {
    if (!videoId) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function load() {
      try {
        const [v, f, e] = await Promise.all([
          api<VideoRecord>(`/api/videos/${videoId}`),
          api<FrameRecord[]>(`/api/videos/${videoId}/frames`),
          api<EventRecord[]>(`/api/videos/${videoId}/events`),
        ]);
        setVideo(v);
        setFrames(f);
        setEvents(e);
        setError('');
        if (v.status === 'uploaded' || v.status === 'processing') {
          timer = setTimeout(load, 1000);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Could not load video.');
      }
    }
    load();
    return () => { if (timer) clearTimeout(timer); };
  }, [videoId]);

  useEffect(() => {
    if (!loopRange || !isPlaying) return;
    if (currentTime >= loopRange.end) {
      player.currentTime = loopRange.start;
      player.play();
    }
  }, [currentTime, isPlaying, loopRange, player]);

  useEffect(() => () => {
    ScreenOrientation.unlockAsync().catch(() => {});
  }, []);

  function setRate(rate: number) {
    player.playbackRate = rate;
  }

  function seekTo(timestamp: number) {
    setLoopRange(null);
    player.pause();
    player.currentTime = Math.max(0, Math.min(video?.duration || player.duration || 0, timestamp));
  }

  function step(framesCount: number) {
    if (!video?.fps) return;
    player.pause();
    player.currentTime = Math.max(0, Math.min(video.duration || player.duration || 0, player.currentTime + framesCount / video.fps));
  }

  function toggleLoop() {
    if (loopRange) {
      setLoopRange(null);
      return;
    }
    const duration = video?.duration || player.duration || 0;
    const center = player.currentTime;
    const range = { start: Math.max(0, center - 2), end: Math.min(duration, center + 2) };
    setLoopRange(range);
    player.currentTime = range.start;
    player.play();
  }

  async function coachingFullscreen() {
    try {
      await ScreenOrientation.lockAsync(ScreenOrientation.OrientationLock.LANDSCAPE);
    } catch {}
    try {
      await videoViewRef.current?.enterFullscreen();
    } catch (e) {
      Alert.alert('Fullscreen unavailable', e instanceof Error ? e.message : 'Could not enter fullscreen.');
    }
  }

  async function extractSequence() {
    setExtracting(true);
    try {
      const result = await api<SequenceResponse>(`/api/videos/${videoId}/extract-sequence`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ center_timestamp: player.currentTime }),
      });
      setSequence(result.frames);
    } catch (e) {
      Alert.alert('Could not extract evidence', e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setExtracting(false);
    }
  }

  async function tagEvent(eventType: EventRecord['event_type']) {
    setTagging(true);
    try {
      await api<EventRecord>(`/api/videos/${videoId}/events`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ timestamp: player.currentTime, event_type: eventType }),
      });
      setEvents(await api<EventRecord[]>(`/api/videos/${videoId}/events`));
    } catch (e) {
      Alert.alert('Could not tag event', e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setTagging(false);
    }
  }

  async function deleteEvent(eventId: number) {
    try {
      await api<void>(`/api/events/${eventId}`, { method: 'DELETE' });
      setEvents(current => current.filter(event => event.id !== eventId));
    } catch (e) {
      Alert.alert('Could not delete event', e instanceof Error ? e.message : 'Unknown error');
    }
  }

  async function cancelAnalysis() {
    try {
      await api(`/api/videos/${videoId}/cancel`, { method: 'POST' });
      setVideo(current => current ? { ...current, status: 'cancelled', progress_stage: 'Analysis cancelled' } : current);
    } catch (e) {
      Alert.alert('Could not cancel analysis', e instanceof Error ? e.message : 'Unknown error');
    }
  }

  if (!video && !error) {
    return <View style={styles.center}><ActivityIndicator /></View>;
  }

  if (error) {
    return <View style={styles.center}><Text style={{ color: colors.danger }}>{error}</Text></View>;
  }

  if (!video) return null;

  if (video.status !== 'complete') {
    const active = video.status === 'uploaded' || video.status === 'processing';
    const failed = video.status === 'failed';
    return (
      <ScrollView style={styles.root} contentContainerStyle={styles.processingContent}>
        <Card>
          {active ? <ActivityIndicator /> : null}
          <Text style={styles.processingTitle}>
            {failed ? 'Analysis failed' : video.status === 'cancelled' ? 'Analysis cancelled' : (video.progress_stage || 'Preparing video')}
          </Text>
          {active ? <Text style={styles.processingPct}>{video.progress_percent || 0}%</Text> : null}
          <Subtitle>
            {failed ? (video.error || 'The analysis could not be completed.') :
             video.status === 'cancelled' ? 'You can return to Upload and start another review.' :
             video.analysis_mode === 'full' ? 'Full Video Scan can take longer.' : 'Lightweight preparation is running.'}
          </Subtitle>
          {active ? <SecondaryButton label="Cancel analysis" onPress={cancelAnalysis} /> : null}
        </Card>

        {frames.length ? (
          <Card>
            <Text style={styles.sectionTitle}>Previews arriving</Text>
            <Subtitle>Frames appear here as the server prepares the video.</Subtitle>
            <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.previewRow}>
              {frames.map(frame => <FrameThumb key={frame.id} frame={frame} onPress={() => {}} disabled />)}
            </ScrollView>
          </Card>
        ) : null}
      </ScrollView>
    );
  }

  const sourceAspect = video.width && video.height ? video.width / video.height : 16 / 9;
  const reviewAspect = Math.max(0.72, Math.min(16 / 9, sourceAspect));

  return (
    <ScrollView style={styles.root} contentContainerStyle={styles.content}>
      <View style={styles.heading}>
        <View style={{ flex: 1 }}>
          <Title>{video.player_name || 'Player'}</Title>
          <Subtitle>{video.original_name}</Subtitle>
        </View>
        <Pill tone="good">ready</Pill>
      </View>

      <Card>
        <VideoView
          ref={videoViewRef}
          player={player}
          style={[styles.video, { aspectRatio: reviewAspect }]}
          nativeControls
          contentFit="contain"
          fullscreenOptions={{ enable: true }}
          onFullscreenEnter={() => { ScreenOrientation.lockAsync(ScreenOrientation.OrientationLock.LANDSCAPE).catch(() => {}); }}
          onFullscreenExit={() => { ScreenOrientation.unlockAsync().catch(() => {}); }}
        />
        <View style={styles.timeRow}>
          <Text style={styles.time}>{currentTime.toFixed(2)}s / {(video.duration || 0).toFixed(2)}s</Text>
          {loopRange ? <Pill tone="purple">Loop {loopRange.start.toFixed(1)}–{loopRange.end.toFixed(1)}s</Pill> : null}
        </View>

        <Text style={styles.controlLabel}>Playback speed</Text>
        <View style={styles.controls}>
          {[0.1, 0.25, 0.5, 1].map(rate => (
            <SecondaryButton key={rate} label={`${rate}×`} active={Math.abs(player.playbackRate - rate) < 0.001} onPress={() => setRate(rate)} />
          ))}
        </View>

        <Text style={styles.controlLabel}>Frame coaching</Text>
        <View style={styles.controls}>
          <SecondaryButton label="−10f" onPress={() => step(-10)} />
          <SecondaryButton label="−1f" onPress={() => step(-1)} />
          <SecondaryButton label={isPlaying ? 'Pause' : 'Play'} onPress={() => isPlaying ? player.pause() : player.play()} />
          <SecondaryButton label="+1f" onPress={() => step(1)} />
          <SecondaryButton label="+10f" onPress={() => step(10)} />
        </View>

        <View style={styles.controls}>
          <SecondaryButton label={loopRange ? 'Stop 4s loop' : 'Loop ±2s'} active={!!loopRange} onPress={toggleLoop} />
          <SecondaryButton label="Coaching Full Screen" onPress={coachingFullscreen} />
        </View>

        <PrimaryButton label={extracting ? 'Extracting…' : 'Extract evidence sequence'} onPress={extractSequence} disabled={extracting} />
      </Card>

      <Card>
        <Text style={styles.sectionTitle}>Tag cricket event</Text>
        <Subtitle>Tag the exact current timestamp to create ground truth for later cricket-specific AI.</Subtitle>
        <View style={styles.eventGrid}>
          {EVENT_TYPES.map(type => (
            <Pressable
              key={type}
              disabled={tagging}
              onPress={() => tagEvent(type)}
              style={({ pressed }) => [styles.eventButton, pressed && styles.pressed, tagging && styles.disabled]}
            >
              <Text style={styles.eventButtonText}>{EVENT_LABELS[type]}</Text>
            </Pressable>
          ))}
        </View>
        {events.length ? (
          <View style={styles.eventList}>
            {events.map(event => (
              <View key={event.id} style={styles.eventRow}>
                <View style={{ flex: 1 }}>
                  <Text style={styles.eventTitle}>{EVENT_LABELS[event.event_type]} · {event.timestamp.toFixed(2)}s</Text>
                  <Text style={styles.eventSub}>Ground-truth tag</Text>
                </View>
                <Pressable onPress={() => deleteEvent(event.id)} style={styles.deleteButton}><Text style={styles.deleteText}>×</Text></Pressable>
              </View>
            ))}
          </View>
        ) : null}
      </Card>

      <Card>
        <Text style={styles.sectionTitle}>Preview frames</Text>
        <Subtitle>Tap a frame to jump directly to that moment.</Subtitle>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.previewRow}>
          {frames.map(frame => <FrameThumb key={frame.id} frame={frame} onPress={() => seekTo(frame.timestamp)} />)}
        </ScrollView>
      </Card>

      {sequence.length ? (
        <Card>
          <Text style={styles.sectionTitle}>Evidence sequence</Text>
          <Subtitle>Frames around the selected coaching moment.</Subtitle>
          <View style={styles.sequenceGrid}>
            {sequence.map((frame, index) => (
              <Pressable key={`${frame.frame_number}-${index}`} style={styles.sequenceItem} onPress={() => seekTo(frame.timestamp)}>
                <Image source={{ uri: apiUrl(frame.image_url) }} style={styles.sequenceImage} resizeMode="contain" />
                <Text style={styles.caption}>{frame.offset >= 0 ? '+' : ''}{frame.offset.toFixed(2)}s · f{frame.frame_number}</Text>
              </Pressable>
            ))}
          </View>
        </Card>
      ) : null}

      <Card>
        <Text style={styles.sectionTitle}>Video metadata</Text>
        <View style={styles.metaGrid}>
          <Meta label="FPS" value={video.fps?.toFixed(3) || '—'} />
          <Meta label="Duration" value={`${(video.duration || 0).toFixed(1)}s`} />
          <Meta label="Resolution" value={`${video.width || 0}×${video.height || 0}`} />
          <Meta label="Frames" value={`${video.frame_count || 0}`} />
        </View>
      </Card>
    </ScrollView>
  );
}

function FrameThumb({ frame, onPress, disabled = false }: { frame: FrameRecord; onPress: () => void; disabled?: boolean }) {
  return (
    <Pressable disabled={disabled} onPress={onPress} style={({ pressed }) => [styles.frameThumb, pressed && styles.pressed]}>
      <Image source={{ uri: apiUrl(frame.image_path) }} style={styles.frameImage} resizeMode="contain" />
      <Text style={styles.frameTime}>{frame.timestamp.toFixed(1)}s</Text>
    </Pressable>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <View style={styles.meta}>
      <Text style={styles.metaLabel}>{label}</Text>
      <Text style={styles.metaValue}>{value}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  content: { padding: 12, gap: 12, paddingBottom: 40 },
  processingContent: { padding: 16, gap: 14, paddingBottom: 40 },
  center: { flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center', padding: 24, gap: 10 },
  heading: { flexDirection: 'row', gap: 12, alignItems: 'center' },
  video: { width: '100%', maxHeight: 470, backgroundColor: '#000', borderRadius: 10 },
  timeRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 8 },
  time: { color: colors.muted, fontSize: 12 },
  controls: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  controlLabel: { color: colors.ink, fontSize: 11, fontWeight: '800', marginTop: 2 },
  processingTitle: { color: colors.ink, fontWeight: '800', fontSize: 16, textAlign: 'center' },
  processingPct: { color: colors.purple, fontWeight: '900', fontSize: 30, textAlign: 'center' },
  sectionTitle: { fontWeight: '800', color: colors.ink, fontSize: 16 },
  previewRow: { gap: 9, paddingVertical: 2 },
  frameThumb: { width: 122, borderRadius: 10, overflow: 'hidden', backgroundColor: '#F5F7FB', borderWidth: 1, borderColor: colors.line },
  frameImage: { width: '100%', height: 132, backgroundColor: '#111827' },
  frameTime: { color: colors.ink, fontSize: 11, fontWeight: '800', paddingHorizontal: 8, paddingVertical: 7 },
  eventGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  eventButton: { minWidth: 66, minHeight: 42, paddingHorizontal: 12, borderRadius: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: '#F7F5FF', borderWidth: 1, borderColor: '#D9D3FF' },
  eventButtonText: { color: colors.purple, fontSize: 12, fontWeight: '900' },
  eventList: { gap: 7, marginTop: 2 },
  eventRow: { flexDirection: 'row', alignItems: 'center', gap: 10, borderTopWidth: 1, borderTopColor: colors.line, paddingTop: 8 },
  eventTitle: { color: colors.ink, fontWeight: '800', fontSize: 12 },
  eventSub: { color: colors.muted, fontSize: 10, marginTop: 2 },
  deleteButton: { width: 32, height: 32, borderRadius: 9, borderWidth: 1, borderColor: colors.line, alignItems: 'center', justifyContent: 'center' },
  deleteText: { color: colors.danger, fontSize: 20, lineHeight: 22 },
  metaGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  meta: { minWidth: '45%', flexGrow: 1, backgroundColor: '#F8FAFD', padding: 10, borderRadius: 9, borderWidth: 1, borderColor: colors.line },
  metaLabel: { color: colors.muted, fontSize: 10 },
  metaValue: { color: colors.ink, fontSize: 15, fontWeight: '800', marginTop: 3 },
  sequenceGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  sequenceItem: { width: '48%', gap: 4 },
  sequenceImage: { width: '100%', aspectRatio: 1, borderRadius: 8, backgroundColor: '#111827' },
  caption: { color: colors.muted, fontSize: 10 },
  pressed: { opacity: 0.72 },
  disabled: { opacity: 0.5 },
});
