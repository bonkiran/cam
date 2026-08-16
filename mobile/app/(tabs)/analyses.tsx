import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { router } from 'expo-router';
import { Screen } from '@/components/Screen';
import { Card, Pill, Subtitle, Title } from '@/components/UI';
import { api, VideoRecord } from '@/lib/api';
import { colors } from '@/theme';

export default function AnalysesScreen() {
  const [videos, setVideos] = useState<VideoRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setError('');
      setVideos(await api<VideoRecord[]>('/api/videos'));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load analyses.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <Screen>
      <Title>My analyses</Title>
      <Subtitle>Uploaded cricket footage and its current processing state.</Subtitle>
      {loading ? <ActivityIndicator /> : null}
      {error ? <Card><Text style={styles.error}>{error}</Text></Card> : null}
      {!loading && videos.length === 0 ? <Card><Subtitle>No analyses yet.</Subtitle></Card> : null}
      {videos.map(video => (
        <Pressable key={video.id} onPress={() => router.push(`/analysis/${video.id}`)}>
          <Card>
            <View style={styles.row}>
              <View style={{ flex: 1, gap: 5 }}>
                <Text numberOfLines={2} style={styles.name}>{video.original_name}</Text>
                <Subtitle>{video.player_name || 'Unknown player'} · {video.analysis_mode || 'quick'}</Subtitle>
                {video.status === 'processing' || video.status === 'uploaded' ? (
                  <Subtitle>{video.progress_stage || 'Processing'} · {video.progress_percent || 0}%</Subtitle>
                ) : null}
              </View>
              <Pill tone={video.status === 'complete' ? 'good' : video.status === 'failed' ? 'warn' : 'purple'}>{video.status}</Pill>
            </View>
          </Card>
        </Pressable>
      ))}
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: 10, alignItems: 'center' },
  name: { color: colors.ink, fontWeight: '800', fontSize: 14 },
  error: { color: colors.danger },
});
