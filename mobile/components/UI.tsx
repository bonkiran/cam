import { PropsWithChildren } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { colors, shadow } from '@/theme';

export function Card({ children }: PropsWithChildren) {
  return <View style={styles.card}>{children}</View>;
}

export function Title({ children }: PropsWithChildren) {
  return <Text style={styles.title}>{children}</Text>;
}

export function Subtitle({ children }: PropsWithChildren) {
  return <Text style={styles.subtitle}>{children}</Text>;
}

export function Pill({ children, tone = 'neutral' }: PropsWithChildren<{ tone?: 'neutral' | 'good' | 'warn' | 'purple' }>) {
  return (
    <View style={[styles.pill, tone === 'good' && styles.good, tone === 'warn' && styles.warn, tone === 'purple' && styles.purple]}>
      <Text style={[styles.pillText, tone === 'good' && styles.goodText, tone === 'warn' && styles.warnText, tone === 'purple' && styles.purpleText]}>
        {children}
      </Text>
    </View>
  );
}

export function PrimaryButton({
  label,
  onPress,
  disabled,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable onPress={onPress} disabled={disabled} style={({ pressed }) => [styles.primary, pressed && styles.pressed, disabled && styles.disabled]}>
      <Text style={styles.primaryText}>{label}</Text>
    </Pressable>
  );
}

export function SecondaryButton({
  label,
  onPress,
  active,
  disabled,
}: {
  label: string;
  onPress: () => void;
  active?: boolean;
  disabled?: boolean;
}) {
  return (
    <Pressable onPress={onPress} disabled={disabled} style={({ pressed }) => [styles.secondary, active && styles.secondaryActive, pressed && styles.pressed, disabled && styles.disabled]}>
      <Text style={[styles.secondaryText, active && styles.secondaryActiveText]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.line,
    padding: 14,
    gap: 10,
    ...shadow,
  },
  title: { fontSize: 26, lineHeight: 31, fontWeight: '800', color: colors.ink },
  subtitle: { color: colors.muted, fontSize: 13, lineHeight: 18 },
  pill: { alignSelf: 'flex-start', backgroundColor: '#EEF1F6', paddingHorizontal: 8, paddingVertical: 5, borderRadius: 999 },
  pillText: { color: '#536078', fontSize: 11, fontWeight: '700' },
  good: { backgroundColor: '#E9F8F0' },
  goodText: { color: colors.green },
  warn: { backgroundColor: '#FFF4DC' },
  warnText: { color: '#946200' },
  purple: { backgroundColor: '#EEEAFF' },
  purpleText: { color: colors.purple },
  primary: { minHeight: 46, borderRadius: 11, paddingHorizontal: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.blue },
  primaryText: { color: '#fff', fontWeight: '800', fontSize: 14 },
  secondary: { minHeight: 40, borderRadius: 10, paddingHorizontal: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: '#fff', borderWidth: 1, borderColor: colors.line },
  secondaryActive: { backgroundColor: '#EFEDFF', borderColor: colors.purple },
  secondaryText: { color: colors.ink, fontWeight: '700', fontSize: 12 },
  secondaryActiveText: { color: colors.purple },
  pressed: { opacity: 0.78 },
  disabled: { opacity: 0.5 },
});
