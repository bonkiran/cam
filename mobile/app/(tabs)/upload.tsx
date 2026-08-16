import { useEffect, useMemo, useState } from 'react';
import { Alert, StyleSheet, Text, TextInput, View } from 'react-native';
import * as ImagePicker from 'expo-image-picker';
import { VideoView, useVideoPlayer } from 'expo-video';
import { router } from 'expo-router';
import { Screen } from '@/components/Screen';
import { Card, PrimaryButton, SecondaryButton, Subtitle, Title } from '@/components/UI';
import { api, apiUrl } from '@/lib/api';
import { colors } from '@/theme';

type Mode = 'quick' | 'shot' | 'full';
type Config = { max_upload_bytes: number; max_upload_label: string };

export default function UploadScreen() {
  const [playerName, setPlayerName] = useState('');
  const [mode, setMode] = useState<Mode>('quick');
  const [asset, setAsset] = useState<ImagePicker.ImagePickerAsset | null>(null);
  const [config, setConfig] = useState<Config | null>(null);
  const [uploadPct, setUploadPct] = useState(0);
  const [status, setStatus] = useState('');
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    api<Config>('/api/config').then(setConfig).catch(() => {});
  }, []);

  const previewSource = useMemo(() => asset?.uri || null, [asset]);
  const player = useVideoPlayer(previewSource, p => { p.loop = true; });

  async function chooseVideo() {
    const permission = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      Alert.alert('Permission required', 'Allow CrickAnalysis to access your video library.');
      return;
    }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ['videos'],
      allowsEditing: false,
      quality: 1,
    });
    if (!result.canceled) {
      setAsset(result.assets[0]);
      setUploadPct(0);
      setStatus('');
    }
  }

  function upload() {
    const cleanName = playerName.trim();
    if (!cleanName) {
      Alert.alert('Player name required', 'Enter the player name before uploading.');
      return;
    }
    if (!asset) {
      Alert.alert('Select a video', 'Choose a cricket video from your device.');
      return;
    }
    if (config && asset.fileSize && asset.fileSize > config.max_upload_bytes) {
      Alert.alert('Video too large', `The server limit is currently ${config.max_upload_label}.`);
      return;
    }

    setBusy(true);
    setStatus('Starting upload…');
    const form = new FormData();
    form.append('player_name', cleanName);
    form.append('analysis_mode', mode);
    form.append('file', {
      uri: asset.uri,
      name: asset.fileName || `cricket-${Date.now()}.mp4`,
      type: asset.mimeType || 'video/mp4',
    } as any);

    const xhr = new XMLHttpRequest();
    xhr.open('POST', apiUrl('/api/videos'));
    xhr.upload.onprogress = event => {
      if (!event.lengthComputable) return;
      const pct = Math.round((event.loaded / event.total) * 100);
      setUploadPct(pct);
      setStatus(`Uploading… ${pct}%`);
    };
    xhr.onerror = () => {
      setBusy(false);
      setStatus('Upload failed. Check your connection and try again.');
    };
    xhr.onload = () => {
      setBusy(false);
      if (xhr.status >= 200 && xhr.status < 300) {
        const video = JSON.parse(xhr.responseText);
        setStatus('Upload accepted. Opening review…');
        router.push(`/analysis/${video.id}`);
        return;
      }
      let detail = `Upload failed (${xhr.status}).`;
      try { detail = JSON.parse(xhr.responseText).detail || detail; } catch {}
      setStatus(detail);
      Alert.alert('Upload failed', detail);
    };
    xhr.send(form);
  }

  return (
    <Screen>
      <Title>Upload video</Title>
      <Subtitle>Quick Review is the default. It avoids the heavy whole-video scan and gets you into the coaching player faster.</Subtitle>

      <Card>
        <Text style={styles.label}>Player name</Text>
        <TextInput
          value={playerName}
          onChangeText={setPlayerName}
          placeholder="Enter player name"
          placeholderTextColor="#9AA3B4"
          style={styles.input}
          autoCapitalize="words"
        />

        <Text style={styles.label}>What do you want to do?</Text>
        <View style={styles.modeRow}>
          <SecondaryButton label="Quick Review" active={mode === 'quick'} onPress={() => setMode('quick')} />
          <SecondaryButton label="Specific Shot" active={mode === 'shot'} onPress={() => setMode('shot')} />
          <SecondaryButton label="Full Scan" active={mode === 'full'} onPress={() => setMode('full')} />
        </View>
        <Subtitle>
          {mode === 'quick' ? 'Metadata + a small preview set. Recommended.' :
           mode === 'shot' ? 'Prepare quickly, then seek to the exact shot for slow-motion review.' :
           'Scans the whole video for motion candidates and can take much longer.'}
        </Subtitle>
      </Card>

      <Card>
        {asset ? (
          <>
            <VideoView player={player} style={styles.video} nativeControls contentFit="contain" />
            <Text numberOfLines={1} style={styles.fileName}>{asset.fileName || 'Selected video'}</Text>
            <Subtitle>
              {asset.fileSize ? `${(asset.fileSize / 1024 / 1024).toFixed(1)} MB` : 'Video selected'}
              {config ? ` · server limit ${config.max_upload_label}` : ''}
            </Subtitle>
          </>
        ) : (
          <View style={styles.placeholder}>
            <Text style={styles.placeholderIcon}>🏏</Text>
            <Text style={styles.placeholderTitle}>Select cricket footage</Text>
            <Subtitle>The selected video will preview here before upload.</Subtitle>
          </View>
        )}
        <SecondaryButton label={asset ? 'Choose another video' : 'Choose video'} onPress={chooseVideo} disabled={busy} />
      </Card>

      {busy || status ? (
        <Card>
          <View style={styles.progressTrack}><View style={[styles.progressFill, { width: `${uploadPct}%` }]} /></View>
          <Text style={styles.status}>{status}</Text>
        </Card>
      ) : null}

      <PrimaryButton label={busy ? 'Uploading…' : 'Upload & Open Review'} onPress={upload} disabled={busy} />
    </Screen>
  );
}

const styles = StyleSheet.create({
  label: { fontWeight: '800', color: colors.ink, fontSize: 12 },
  input: { minHeight: 46, borderRadius: 10, borderWidth: 1, borderColor: colors.line, paddingHorizontal: 12, color: colors.ink, backgroundColor: '#fff' },
  modeRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  video: { width: '100%', aspectRatio: 16 / 9, backgroundColor: '#000', borderRadius: 10 },
  placeholder: { aspectRatio: 16 / 9, borderRadius: 10, backgroundColor: '#F1F4F9', alignItems: 'center', justifyContent: 'center', gap: 7, padding: 16 },
  placeholderIcon: { fontSize: 28 },
  placeholderTitle: { fontWeight: '800', color: colors.ink },
  fileName: { fontWeight: '800', color: colors.ink },
  progressTrack: { height: 9, borderRadius: 999, backgroundColor: '#E9EDF4', overflow: 'hidden' },
  progressFill: { height: '100%', backgroundColor: colors.blue },
  status: { color: colors.muted, fontSize: 12 },
});
