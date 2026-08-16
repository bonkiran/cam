import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, Alert, Image, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useLocalSearchParams } from 'expo-router';
import { useEvent } from 'expo';
import { VideoView, useVideoPlayer } from 'expo-video';
import { Card, Pill, PrimaryButton, SecondaryButton, Subtitle, Title } from '@/components/UI';
import { api, apiUrl, FrameRecord, VideoRecord } from '@/lib/api';
import { colors } from '@/theme';

type SequenceResponse = {
  frames: { image_url: string; offset: number; frame_number: number; timestamp: number }[];
};

export default function AnalysisScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const videoId = Number(id);
  const [video, setVideo] = useState<VideoRecord | null>(null);
  const [frames, setFrames] = useState<FrameRecord[]>([]);
  const [sequence, setSequence] = useState<SequenceResponse['frames']>([]);
  const [error, setError] = useState('');
  const [extracting, setExtracting] = useState(false);

  const source = useMemo(() => video ? apiUrl(video.video_url) : null, [video]);
  const player = useVideoPlayer(source, p => {
    p.timeUpdateEventInterval = 0.1;
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
        const [v, f] = await Promise.all([
          api<VideoRecord>(`/api/videos/${videoId}`),
          api<FrameRecord[]>(`/api/videos/${videoId}/frames`),
        ]);
        setVideo(v);
        setFrames(f);
        setError('');
        if (v.status === 'uploaded' || v.status === 'processing') {
          timer = setTimeout(load, 1200);
        }
      } catch (e) {
        setError(e instanceof Error ? e.message : 'Could not load video.');
      }
    }
    load();
    return () => { if (timer) clearTimeout(timer); };
  }, [videoId]);

  function setRate(rate: number) {
    player.playbackRate = rate;
  }

  function step(framesCount: number) {
    if (!video?.fps) return;
    player.pause();
    player.currentTime = Math.max(0, Math.min(video.duration || player.duration || 0, player.currentTime + framesCount / video.fps));
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

  if (!video && !error) {
    return <View style={styles.center}><ActivityIndicator /></View>;
  }

  if (error) {
    return <View style={styles.center}><Text style={{ color: colors.danger }}>{error}</Text></View>;
  }

  if (!video) return null;

  if (video.status !== 'complete') {
    return (
      <View style={styles.center}>
        <ActivityIndicator />
        <Text style={styles.processingTitle}>{video.progress_stage || 'Preparing video'}</Text>
        <Text style={styles.processingPct}>{video.progress_percent || 0}%</Text>
        <Subtitle>{video.analysis_mode === 'full' ? 'Full Video Scan can take longer.' : 'Lightweight preparation is running.'}</Subtitle>
      </View>
    );
  }

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
          player={player}
          style={styles.video}
          nativeControls
          contentFit="contain"
          fullscreenOptions={{ enable: true }}
        />
        <Text style={styles.time}>{currentTime.toFixed(2)}s / {(video.duration || 0).toFixed(2)}s</Text>

        <View style={styles.controls}>
          {[0.1, 0.25, 0.5, 1].map(rate => (
            <SecondaryButton key={rate} label={`${rate}×`} active={player.playbackRate === rate} onPress={() => setRate(rate)} />
          ))}
        </View>

        <View style={styles.controls}>
          <SecondaryButton label="−10f" onPress={() => step(-10)} />
          <SecondaryButton label="−1f" onPress={() => step(-1)} />
          <SecondaryButton label={isPlaying ? 'Pause' : 'Play'} onPress={() => isPlaying ? player.pause() : player.play()} />
          <SecondaryButton label="+1f" onPress={() => step(1)} />
          <SecondaryButton label="+10f" onPress={() => step(10)} />
        </View>

        <PrimaryButton label={extracting ? 'Extracting…' : 'Extract evidence sequence'} onPress={extractSequence} disabled={extracting} />
      </Card>

      <Card>
        <Text style={styles.sectionTitle}>Video metadata</Text>
        <View style={styles.metaGrid}>
          <Meta label="FPS" value={video.fps?.toFixed(3) || '—'} />
          <Meta label="Duration" value={`${(video.duration || 0).toFixed(1)}s`} />
          <Meta label="Resolution" value={`${video.width || 0}×${video.height || 0}`} />
          <Meta label="Frames" value={`${video.frame_count || 0}`} />
        </View>
      </Card>

      <Card>
        <Text style={styles.sectionTitle}>Preview frames</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
          {frames.map(frame => (
            <SecondaryButton key={frame.id} label={`${frame.timestamp.toFixed(1)}s`} onPress={() => { player.pause(); player.currentTime = frame.timestamp; }} />
          ))}
        </ScrollView>
      </Card>

      {sequence.length ? (
        <Card>
          <Text style={styles.sectionTitle}>Evidence sequence</Text>
          <View style={styles.sequenceGrid}>
            {sequence.map((frame, index) => (
              <View key={`${frame.frame_number}-${index}`} style={styles.sequenceItem}>
                <Image source={{ uri: apiUrl(frame.image_url) }} style={styles.sequenceImage} />
                <Text style={styles.caption}>{frame.offset >= 0 ? '+' : ''}{frame.offset.toFixed(2)}s · f{frame.frame_number}</Text>
              </View>
            ))}
          </View>
        </Card>
      ) : null}
    </ScrollView>
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
  content: { padding: 14, gap: 14, paddingBottom: 40 },
  center: { flex: 1, backgroundColor: colors.bg, alignItems: 'center', justifyContent: 'center', padding: 24, gap: 10 },
  heading: { flexDirection: 'row', gap: 12, alignItems: 'center' },
  video: { width: '100%', aspectRatio: 16 / 9, backgroundColor: '#000', borderRadius: 10 },
  time: { color: colors.muted, fontSize: 12, textAlign: 'right' },
  controls: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  processingTitle: { color: colors.ink, fontWeight: '800', fontSize: 16 },
  processingPct: { color: colors.purple, fontWeight: '900', fontSize: 28 },
  sectionTitle: { fontWeight: '800', color: colors.ink, fontSize: 16 },
  metaGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  meta: { minWidth: '45%', flexGrow: 1, backgroundColor: '#F8FAFD', padding: 10, borderRadius: 9, borderWidth: 1, borderColor: colors.line },
  metaLabel: { color: colors.muted, fontSize: 10 },
  metaValue: { color: colors.ink, fontSize: 15, fontWeight: '800', marginTop: 3 },
  sequenceGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  sequenceItem: { width: '48%', gap: 4 },
  sequenceImage: { width: '100%', aspectRatio: 16 / 9, borderRadius: 8, backgroundColor: '#E7EBF2' },
  caption: { color: colors.muted, fontSize: 10 },
});
