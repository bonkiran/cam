import { Tabs, router } from 'expo-router';
import { Pressable, Text } from 'react-native';
import { colors } from '@/theme';

function AIButton() {
  return (
    <Pressable onPress={() => router.push('/ai')} style={{ paddingHorizontal: 12, paddingVertical: 6 }}>
      <Text style={{ color: colors.purple, fontWeight: '800' }}>✦ AI</Text>
    </Pressable>
  );
}

export default function TabsLayout() {
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: colors.card },
        headerTitleStyle: { fontWeight: '800', color: colors.ink },
        headerRight: () => <AIButton />,
        tabBarActiveTintColor: colors.purple,
        tabBarInactiveTintColor: colors.muted,
        tabBarStyle: { borderTopColor: colors.line, backgroundColor: colors.card },
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Home', tabBarLabel: 'Home', tabBarIcon: () => <Text>⌂</Text> }} />
      <Tabs.Screen name="upload" options={{ title: 'Upload', tabBarLabel: 'Upload', tabBarIcon: () => <Text>⇧</Text> }} />
      <Tabs.Screen name="analyses" options={{ title: 'Analyses', tabBarLabel: 'Analyses', tabBarIcon: () => <Text>▣</Text> }} />
      <Tabs.Screen name="players" options={{ title: 'Players', tabBarLabel: 'Players', tabBarIcon: () => <Text>♙</Text> }} />
      <Tabs.Screen name="more" options={{ title: 'More', tabBarLabel: 'More', tabBarIcon: () => <Text>•••</Text> }} />
    </Tabs>
  );
}
