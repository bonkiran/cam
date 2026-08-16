import { useEffect, useState } from 'react';
import { Linking, StyleSheet, Text, TextInput, View } from 'react-native';
import { Screen } from '@/components/Screen';
import { Card, PrimaryButton, Subtitle, Title } from '@/components/UI';
import { api, PlayerRecord } from '@/lib/api';
import { colors } from '@/theme';

export default function PlayersScreen() {
  const [players, setPlayers] = useState<PlayerRecord[]>([]);
  const [query, setQuery] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    api<PlayerRecord[]>('/api/players').then(setPlayers).catch(e => setError(e instanceof Error ? e.message : 'Could not load players.'));
  }, []);

  function openCricClubs() {
    const q = query.trim();
    if (!q) return;
    const url = `https://www.google.com/search?q=${encodeURIComponent(`site:cricclubs.com "${q}" cricket player`)}`;
    Linking.openURL(url);
  }

  return (
    <Screen>
      <Title>Players</Title>
      <Subtitle>CrickAnalysis player profiles plus a public CricClubs lookup bridge.</Subtitle>

      <Card>
        <Text style={styles.section}>CricClubs player lookup</Text>
        <Subtitle>Enter a full player name or CC Player ID. This opens a CricClubs-focused public lookup until official API access is connected.</Subtitle>
        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder="Full name or CC Player ID"
          placeholderTextColor="#9AA3B4"
          style={styles.input}
        />
        <PrimaryButton label="Find on CricClubs" onPress={openCricClubs} disabled={!query.trim()} />
      </Card>

      <Text style={styles.section}>CrickAnalysis players</Text>
      {error ? <Card><Text style={styles.error}>{error}</Text></Card> : null}
      {players.length === 0 && !error ? <Card><Subtitle>No local player profiles yet.</Subtitle></Card> : null}
      {players.map(player => (
        <Card key={player.id}>
          <View style={styles.row}>
            <View style={{ flex: 1 }}>
              <Text style={styles.name}>{player.name}</Text>
              <Subtitle>{player.video_count} video(s) · {player.completed_analyses || 0} completed</Subtitle>
            </View>
          </View>
        </Card>
      ))}
    </Screen>
  );
}

const styles = StyleSheet.create({
  section: { color: colors.ink, fontWeight: '800', fontSize: 16 },
  input: { minHeight: 46, borderWidth: 1, borderColor: colors.line, borderRadius: 10, paddingHorizontal: 12, color: colors.ink, backgroundColor: '#fff' },
  row: { flexDirection: 'row', alignItems: 'center' },
  name: { fontWeight: '800', fontSize: 15, color: colors.ink, marginBottom: 4 },
  error: { color: colors.danger },
});
