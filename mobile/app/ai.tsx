import { useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, StyleSheet, Text, TextInput } from 'react-native';
import { Screen } from '@/components/Screen';
import { Card, PrimaryButton, Subtitle, Title } from '@/components/UI';
import { api } from '@/lib/api';
import { colors } from '@/theme';

type AssistantResponse = { answer: string; mode: string; ai_configured: boolean };

export default function AIScreen() {
  const [message, setMessage] = useState('');
  const [answer, setAnswer] = useState('Ask about cricket or how to use CrickAnalysis.');
  const [busy, setBusy] = useState(false);

  async function ask() {
    const q = message.trim();
    if (!q) return;
    setBusy(true);
    try {
      const response = await api<AssistantResponse>('/api/assistant', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          message: q,
          context: { platform: Platform.OS, client: 'CrickAnalysis Mobile' },
        }),
      });
      setAnswer(response.answer);
      setMessage('');
    } catch (e) {
      setAnswer(e instanceof Error ? e.message : 'Crick AI could not answer.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
      <Screen>
        <Title>✦ Crick AI</Title>
        <Subtitle>Cricket knowledge, coaching questions, and CrickAnalysis help.</Subtitle>

        <Card>
          <Text style={styles.answer}>{answer}</Text>
        </Card>

        <Card>
          <TextInput
            value={message}
            onChangeText={setMessage}
            placeholder="Ask about cricket or this app…"
            placeholderTextColor="#9AA3B4"
            style={styles.input}
            multiline
          />
          {busy ? <ActivityIndicator /> : null}
          <PrimaryButton label="Ask Crick AI" onPress={ask} disabled={busy || !message.trim()} />
        </Card>
      </Screen>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  answer: { color: colors.ink, fontSize: 14, lineHeight: 21 },
  input: { minHeight: 110, borderRadius: 10, borderWidth: 1, borderColor: colors.line, padding: 12, textAlignVertical: 'top', color: colors.ink },
});
