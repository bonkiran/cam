import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { colors } from '@/theme';

export default function RootLayout() {
  return (
    <>
      <StatusBar style="auto" />
      <Stack
        screenOptions={{
          headerStyle: { backgroundColor: colors.card },
          headerTintColor: colors.ink,
          headerTitleStyle: { fontWeight: '800' },
          contentStyle: { backgroundColor: colors.bg },
        }}
      >
        <Stack.Screen name="(tabs)" options={{ headerShown: false }} />
        <Stack.Screen name="analysis/[id]" options={{ title: 'Video Review' }} />
        <Stack.Screen name="ai" options={{ title: 'Crick AI', presentation: 'modal' }} />
      </Stack>
    </>
  );
}
