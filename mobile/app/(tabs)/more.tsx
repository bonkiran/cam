import { Linking, StyleSheet, Text, View } from 'react-native';
import { Screen } from '@/components/Screen';
import { Card, PrimaryButton, Subtitle, Title } from '@/components/UI';
import { colors } from '@/theme';

const references = [
  ['CricVision', 'https://cricvision.ai'],
  ['CrickCoach AI', 'https://crickcoach.ai'],
  ['PoseForge', 'https://github.com/roboflow/sports'],
  ['Fulltrack AI', 'https://www.fulltrack.ai'],
  ['StanceBeam', 'https://stancebeam.com'],
  ['Crickzy AI Coach', 'https://crickzy.com'],
  ['Onform', 'https://onform.com'],
  ['Dartfish', 'https://www.dartfish.com'],
  ['Kinovea', 'https://www.kinovea.org'],
  ['Hudl Sportscode', 'https://www.hudl.com/products/sportscode'],
  ['Nacsport', 'https://www.nacsport.com'],
  ['LongoMatch', 'https://longomatch.com'],
  ['Sportsbox 3D Golf', 'https://www.sportsbox.ai'],
  ['b4-app', 'https://b4-app.com'],
  ['Skillest', 'https://skillest.com'],
  ['VisualEyes', 'https://visualeyes.com'],
];

export default function MoreScreen() {
  return (
    <Screen>
      <Title>References & more</Title>
      <Subtitle>Handy external references while CrickAnalysis develops its full product capabilities.</Subtitle>
      {references.map(([name, url]) => (
        <Card key={name}>
          <View style={styles.row}>
            <View style={{ flex: 1 }}>
              <Text style={styles.name}>{name}</Text>
              <Subtitle>External reference</Subtitle>
            </View>
            <PrimaryButton label="Open" onPress={() => Linking.openURL(url)} />
          </View>
        </Card>
      ))}
    </Screen>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: 12, alignItems: 'center' },
  name: { fontWeight: '800', color: colors.ink, fontSize: 15 },
});
