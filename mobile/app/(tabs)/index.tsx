import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { router } from 'expo-router';
import { Screen } from '@/components/Screen';
import { Card, Pill, Subtitle, Title } from '@/components/UI';
import { api, Dashboard } from '@/lib/api';
import { colors } from '@/theme';

export default function HomeScreen() {
  const [data, setData] = useState<Dashboard | null>(null);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    try {
      setError('');
      setData(await api<Dashboard>('/api/dashboard'));
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Could not load dashboard.');
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  return (
    <Screen>
      <View style={styles.hero}>
        <View style={{ flex: 1 }}>
          <Title>CrickAnalysis</Title>
          <Subtitle>Mobile coaching and player review connected to the same CrickAnalysis backend.</Subtitle>
        </View>
        <Pill tone="purple">MVP 0.1</Pill>
      </View>

      {!data && !error ? <ActivityIndicator /> : null}
      {error ? <Card><Text style={styles.error}>{error}</Text></Card> : null}

      {data ? (
        <>
          <View style={styles.statGrid}>
            <Stat label="Videos" value={data.video_count} />
            <Stat label="Players" value={data.player_count} />
            <Stat label="Boundaries" value={data.boundaries} />
            <Stat label="Sixes" value={data.sixes} />
          </View>

          <View style={styles.sectionHead}>
            <Text style={styles.sectionTitle}>Recent analyses</Text>
            <Pressable onPress={() => router.push('/(tabs)/analyses')}><Text style={styles.link}>View all</Text></Pressable>
          </View>

          {data.recent.length === 0 ? (
            <Card><Subtitle>No videos yet. Upload a cricket video to begin.</Subtitle></Card>
          ) : data.recent.map(v => (
            <Pressable key={v.id} onPress={() => router.push(`/analysis/${v.id}`)}>
              <Card>
                <View style={styles.row}>
                  <View style={{ flex: 1, gap: 4 }}>
                    <Text numberOfLines={1} style={styles.videoTitle}>{v.original_name}</Text>
                    <Subtitle>{v.player_name || 'Unknown player'}</Subtitle>
                  </View>
                  <Pill tone={v.status === 'complete' ? 'good' : 'warn'}>{v.status}</Pill>
                </View>
              </Card>
            </Pressable>
          ))}
        </>
      ) : null}
    </Screen>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <View style={styles.stat}>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  hero: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },
  statGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  stat: { width: '47%', backgroundColor: '#fff', borderWidth: 1, borderColor: colors.line, borderRadius: 13, padding: 14 },
  statValue: { fontSize: 24, fontWeight: '900', color: colors.ink },
  statLabel: { fontSize: 12, color: colors.muted },
  sectionHead: { marginTop: 4, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  sectionTitle: { fontSize: 17, fontWeight: '800', color: colors.ink },
  link: { color: colors.purple, fontWeight: '700' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  videoTitle: { fontWeight: '800', color: colors.ink, fontSize: 14 },
  error: { color: colors.danger },
});
