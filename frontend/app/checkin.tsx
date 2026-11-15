import { useQuery } from "@tanstack/react-query";
import { useRouter } from "expo-router";
import { CameraView, useCameraPermissions } from "expo-camera";
import { useRef, useState } from "react";
import {
  KeyboardAvoidingView,
  Linking,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from "react-native";
import { useSafeAreaInsets } from "react-native-safe-area-context";
import FeatherIcon from "@react-native-vector-icons/feather";

import { api } from "@/src/api";
import { useAuth } from "@/src/auth-context";
import { colors, radius, spacing } from "@/src/theme";
import { LuxButton } from "@/src/ui";

export default function CheckIn() {
  const router = useRouter();
  const insets = useSafeAreaInsets();
  const { user } = useAuth();
  const [ticketId, setTicketId] = useState("");
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; msg: string } | null>(null);

  const isHostRole = user?.role === "promoter" || user?.role === "venue_owner" || user?.role === "admin";
  const { data: duty } = useQuery({ queryKey: ["door-duty"], queryFn: api.doorDuty, enabled: !!user && !isHostRole });
  const canScan = isHostRole || !!duty?.venues.length;
  const [permission, requestPermission] = useCameraPermissions();
  const [scanning, setScanning] = useState(false);
  const [explain, setExplain] = useState(false);
  const lock = useRef(false);

  async function openCamera() {
    if (permission?.granted) return setScanning(true);
    if (permission && !permission.canAskAgain) return setExplain(true);
    if (!explain) return setExplain(true);
    const res = await requestPermission();
    if (res.granted) {
      setExplain(false);
      setScanning(true);
    }
  }

  async function onScanned(data: string) {
    if (lock.current) return;
    lock.current = true;
    setScanning(false);
    setTicketId(data);
    await submit(data);
    setTimeout(() => (lock.current = false), 1500);
  }

  async function submit(value = ticketId) {
    if (!value.trim()) return;
    setBusy(true);
    setResult(null);
    try {
      const t = await api.checkInTicket(value.trim());
      setResult({ ok: true, msg: `${t.event_title} · qty ${t.quantity}` });
    } catch (e) {
      setResult({ ok: false, msg: e instanceof Error ? e.message : "Failed" });
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView behavior={Platform.OS === "ios" ? "padding" : "height"} style={styles.root}>
      <View style={[styles.header, { paddingTop: insets.top + spacing.md }]}>
        <Pressable testID="checkin-close" onPress={() => router.back()} style={styles.closeBtn}>
          <FeatherIcon name="x" size={22} color={colors.onSurface} />
        </Pressable>
        <Text style={styles.title}>Check-in</Text>
        <View style={{ width: 40 }} />
      </View>

      <View style={styles.body}>
        {!canScan ? (
          <View style={styles.restricted}>
            <FeatherIcon name="lock" size={32} color={colors.brandPrimary} />
            <Text style={styles.restrictedTitle}>Staff only</Text>
            <Text style={styles.restrictedText}>Only promoters, venues, admins and door staff can scan guests.</Text>
          </View>
        ) : (
          <>
            {scanning ? (
              <View style={styles.cameraBox} testID="camera-view">
                <CameraView
                  style={StyleSheet.absoluteFill}
                  facing="back"
                  barcodeScannerSettings={{ barcodeTypes: ["qr"] }}
                  onBarcodeScanned={({ data }) => onScanned(data)}
                />
                <View style={styles.frame} />
                <Pressable testID="camera-close" onPress={() => setScanning(false)} style={styles.camClose}>
                  <FeatherIcon name="x" size={20} color={colors.onSurface} />
                </Pressable>
              </View>
            ) : explain ? (
              <View style={styles.explain} testID="camera-explain">
                <FeatherIcon name="camera" size={28} color={colors.brandPrimary} />
                <Text style={styles.explainTitle}>Scan tickets at the door</Text>
                <Text style={styles.hint}>
                  {permission && !permission.canAskAgain
                    ? "Camera access is turned off. Enable it in Settings to scan guest QR codes, or type the code below."
                    : "Nocturne uses the camera only to read guest QR codes for instant check-in."}
                </Text>
                {permission && !permission.canAskAgain ? (
                  <LuxButton testID="camera-open-settings" label="Open Settings" onPress={() => Linking.openSettings()} />
                ) : (
                  <LuxButton testID="camera-allow" label="Allow camera" onPress={openCamera} />
                )}
                <Pressable testID="camera-not-now" onPress={() => setExplain(false)} style={{ paddingVertical: spacing.md }}>
                  <Text style={styles.hint}>Not now</Text>
                </Pressable>
              </View>
            ) : (
              <LuxButton
                testID="camera-scan-btn"
                label="Scan QR with camera"
                onPress={openCamera}
                icon={<FeatherIcon name="camera" size={16} color={colors.onBrandPrimary} />}
              />
            )}
            <Text style={styles.hint}>{"Or type the code under the guest's QR (e.g. #32993EB1)."}</Text>
            <TextInput
              testID="checkin-input"
              value={ticketId}
              onChangeText={setTicketId}
              placeholder="ticket id"
              placeholderTextColor={colors.muted}
              autoCapitalize="none"
              autoCorrect={false}
              style={styles.input}
            />
            <LuxButton
              testID="checkin-submit"
              label={busy ? "Checking…" : "Check in guest"}
              onPress={() => submit()}
              loading={busy}
            />
            {result && (
              <View style={[styles.result, { borderColor: result.ok ? colors.success : colors.error }]} testID="checkin-result">
                <FeatherIcon
                  name={result.ok ? "check-circle" : "x-circle"}
                  size={24}
                  color={result.ok ? colors.success : colors.error}
                />
                <Text style={styles.resultText}>{result.msg}</Text>
              </View>
            )}
          </>
        )}
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  cameraBox: { height: 320, borderRadius: radius.lg, overflow: "hidden", backgroundColor: colors.surfaceSecondary, alignItems: "center", justifyContent: "center" },
  frame: { width: 200, height: 200, borderRadius: radius.lg, borderWidth: 3, borderColor: colors.brandPrimary },
  camClose: {
    position: "absolute", top: spacing.md, right: spacing.md, width: 44, height: 44, borderRadius: 22,
    backgroundColor: "rgba(9,9,11,0.6)", alignItems: "center", justifyContent: "center",
  },
  explain: { backgroundColor: colors.surfaceSecondary, borderRadius: radius.lg, padding: spacing.lg, gap: spacing.md, alignItems: "center", borderWidth: 1, borderColor: colors.border },
  explainTitle: { color: colors.onSurface, fontSize: 18, fontWeight: "800" },
  root: { flex: 1, backgroundColor: colors.surface },
  header: {
    flexDirection: "row", alignItems: "center", justifyContent: "space-between",
    paddingHorizontal: spacing.lg, paddingBottom: spacing.md,
  },
  closeBtn: {
    width: 44, height: 44, borderRadius: 22, backgroundColor: colors.surfaceSecondary,
    borderWidth: 1, borderColor: colors.border, alignItems: "center", justifyContent: "center",
  },
  title: { color: colors.onSurface, fontSize: 17, fontWeight: "700" },
  body: { flex: 1, padding: spacing.lg, gap: spacing.lg },
  hint: { color: colors.muted, fontSize: 14 },
  input: {
    backgroundColor: colors.surfaceSecondary, borderWidth: 1, borderColor: colors.border,
    borderRadius: radius.md, paddingHorizontal: spacing.lg, paddingVertical: 14,
    color: colors.onSurface, fontSize: 16, fontFamily: Platform.OS === "ios" ? "Menlo" : "monospace",
  },
  result: {
    flexDirection: "row", alignItems: "center", gap: spacing.md,
    backgroundColor: colors.surfaceSecondary, borderRadius: radius.md,
    padding: spacing.lg, borderWidth: 1.5,
  },
  resultText: { color: colors.onSurface, fontSize: 14, flex: 1 },
  restricted: { alignItems: "center", gap: spacing.md, paddingTop: spacing["3xl"] },
  restrictedTitle: { color: colors.onSurface, fontSize: 22, fontWeight: "800" },
  restrictedText: { color: colors.muted, fontSize: 14, textAlign: "center", paddingHorizontal: spacing.xl },
});
